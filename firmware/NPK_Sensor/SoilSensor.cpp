#include "SoilSensor.h"
#include "Config.h"

#if NPK_USE_SOFTWARE_SERIAL
  #include <SoftwareSerial.h>
  static SoftwareSerial g_port(RS485_RX_PIN, RS485_TX_PIN);
  static inline void portBegin(uint32_t baud) { g_port.begin(baud); }
#else
  static HardwareSerial& g_port = Serial1;
  static inline void portBegin(uint32_t baud) {
    g_port.begin(baud, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
  }
#endif

// ---------------------------------------------------------------------------
// Register profile
// ---------------------------------------------------------------------------
// Each entry is one Modbus function-0x03 transaction. `dest` maps the n-th
// returned register onto a channel; -1 discards it.
struct ReadOp {
  uint16_t addr;
  uint8_t  count;
  int8_t   dest[7];
};

#if SENSOR_REGISTER_PROFILE == PROFILE_DATASHEET
// Section 4.3 of the manual. The map is sparse, so this is four transactions
// rather than one. At a five second sample interval that costs nothing, and
// each frame is one the manual documents verbatim in section 4.4.
static const ReadOp kReadOps[] = {
  { 0x0006, 1, { CH_PH,        -1, -1, -1, -1, -1, -1 } },
  { 0x0012, 2, { CH_MOISTURE,  CH_TEMPERATURE, -1, -1, -1, -1, -1 } },
  { 0x0015, 1, { CH_CONDUCTIVITY, -1, -1, -1, -1, -1, -1 } },
  { 0x001E, 3, { CH_NITROGEN, CH_PHOSPHORUS, CH_POTASSIUM, -1, -1, -1, -1 } },
};
#else
// The contiguous block the original sketch assumed.
static const ReadOp kReadOps[] = {
  { 0x0000, 7, { CH_MOISTURE, CH_TEMPERATURE, CH_CONDUCTIVITY, CH_PH,
                 CH_NITROGEN, CH_PHOSPHORUS, CH_POTASSIUM } },
};
#endif

static const uint8_t kReadOpCount = sizeof(kReadOps) / sizeof(kReadOps[0]);

// ---------------------------------------------------------------------------
// CRC-16/MODBUS, low byte transmitted first (manual section 4.2).
// ---------------------------------------------------------------------------
uint16_t modbusCrc(const uint8_t* data, uint8_t len) {
  uint16_t crc = 0xFFFF;
  for (uint8_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x0001) ? (crc >> 1) ^ 0xA001 : (crc >> 1);
    }
  }
  return crc;
}

// ---------------------------------------------------------------------------

void SoilSensor::begin() {
  pinMode(RS485_DE_RE_PIN, OUTPUT);
  driveTransmit(false);
  setBaud(SENSOR_BAUD_DEFAULT);
}

void SoilSensor::setBaud(uint32_t baud) {
  baud_ = baud;
  g_port.end();
  portBegin(baud);
  delay(20);
}

void SoilSensor::driveTransmit(bool enable) {
  digitalWrite(RS485_DE_RE_PIN, enable ? HIGH : LOW);
  delayMicroseconds(50);
}

bool SoilSensor::sendFrame(const uint8_t* frame, uint8_t len) {
  while (g_port.available()) g_port.read();   // discard stale bytes

  driveTransmit(true);
  size_t written = g_port.write(frame, len);
  g_port.flush();                             // wait for the shift register

  // Hold DE for one extra character time so the last stop bit leaves the
  // transceiver before the driver is disabled.
  delayMicroseconds((10UL * 1000000UL) / baud_ + 100);
  driveTransmit(false);

  return written == len;
}

int SoilSensor::readFrame(uint8_t* buf, uint8_t expected, uint32_t timeoutMs) {
  uint32_t deadline = millis() + timeoutMs;
  uint8_t n = 0;
  while (n < expected && (int32_t)(millis() - deadline) < 0) {
    if (g_port.available()) {
      buf[n++] = (uint8_t)g_port.read();
      deadline = millis() + MODBUS_INTERFRAME_MS + 20;  // inter-byte gap
    }
  }
  return n;
}

bool SoilSensor::transaction(uint16_t addr, uint8_t count, uint16_t* regs) {
  uint8_t frame[8] = {
    SENSOR_SLAVE_ID, 0x03,
    (uint8_t)(addr >> 8), (uint8_t)(addr & 0xFF),
    (uint8_t)(count >> 8), (uint8_t)(count & 0xFF),
    0, 0
  };
  uint16_t crc = modbusCrc(frame, 6);
  frame[6] = (uint8_t)(crc & 0xFF);   // CRC_L first
  frame[7] = (uint8_t)(crc >> 8);

  if (count == 0 || count > 8) { lastError_ = "register count out of range"; return false; }

  const uint8_t expected = 5 + 2 * count;   // id, fn, bytecount, data, crc
  uint8_t rx[5 + 2 * 8];

  for (uint8_t attempt = 0; attempt < MODBUS_RETRIES; ++attempt) {
    if (attempt) delay(MODBUS_INTERFRAME_MS * 2);
    if (!sendFrame(frame, sizeof(frame))) { lastError_ = "uart write failed"; continue; }

    int n = readFrame(rx, expected, MODBUS_RESPONSE_TIMEOUT_MS);
    if (n == 0) { lastError_ = "no reply"; continue; }

    if (n == 5 && (rx[1] & 0x80)) { lastError_ = "modbus exception"; continue; }
    if (n < expected)             { lastError_ = "short reply"; continue; }
    if (rx[0] != SENSOR_SLAVE_ID) { lastError_ = "wrong slave id"; continue; }
    if (rx[1] != 0x03)            { lastError_ = "wrong function code"; continue; }
    if (rx[2] != 2 * count)       { lastError_ = "bad byte count"; continue; }

    uint16_t want = modbusCrc(rx, expected - 2);
    uint16_t got  = (uint16_t)rx[expected - 1] << 8 | rx[expected - 2];
    if (want != got)              { lastError_ = "crc mismatch"; continue; }

    for (uint8_t i = 0; i < count; ++i) {
      regs[i] = (uint16_t)rx[3 + 2 * i] << 8 | rx[4 + 2 * i];  // high byte first
    }
    lastError_ = "";
    return true;
  }
  return false;
}

bool SoilSensor::read(Reading& out) {
  for (uint8_t c = 0; c < CH_COUNT; ++c) {
    out.raw[c] = 0;
    out.scaled[c] = 0.0f;
    out.valid[c] = false;
  }
  out.failedOps = 0;

  for (uint8_t op = 0; op < kReadOpCount; ++op) {
    uint16_t regs[7] = { 0 };
    if (!transaction(kReadOps[op].addr, kReadOps[op].count, regs)) {
      out.failedOps++;
      continue;
    }
    for (uint8_t i = 0; i < kReadOps[op].count; ++i) {
      int8_t ch = kReadOps[op].dest[i];
      if (ch < 0) continue;
      out.raw[ch] = regs[i];
      // Temperature is the only two's complement value (manual 4.4.1).
      float counts = CHANNELS[ch].isSigned ? (float)(int16_t)regs[i]
                                           : (float)regs[i];
      out.scaled[ch] = counts / CHANNELS[ch].scale;
      out.valid[ch] = true;
    }
    if (op + 1 < kReadOpCount) delay(MODBUS_INTERFRAME_MS);
  }

  out.complete = true;
  for (uint8_t c = 0; c < CH_COUNT; ++c) {
    if (!out.valid[c]) { out.complete = false; break; }
  }
  return out.complete;
}

bool SoilSensor::readAveraged(Reading& out, uint8_t samples) {
  if (samples == 0) samples = 1;

  double sum[CH_COUNT] = { 0 };
  uint16_t hits[CH_COUNT] = { 0 };
  Reading sample;
  uint8_t good = 0;

  for (uint8_t s = 0; s < samples; ++s) {
    if (read(sample)) good++;
    for (uint8_t c = 0; c < CH_COUNT; ++c) {
      if (sample.valid[c]) { sum[c] += sample.scaled[c]; hits[c]++; }
    }
    if (s + 1 < samples) delay(120);
  }

  out = sample;   // keep the last raw words for reference
  out.complete = true;
  for (uint8_t c = 0; c < CH_COUNT; ++c) {
    out.valid[c] = hits[c] > 0;
    out.scaled[c] = out.valid[c] ? (float)(sum[c] / hits[c]) : 0.0f;
    if (!out.valid[c]) out.complete = false;
  }
  return good > 0;
}

bool SoilSensor::detectBaud() {
  const uint8_t n = sizeof(kSensorBaudCandidates) / sizeof(kSensorBaudCandidates[0]);
  uint16_t probe = 0;
  for (uint8_t i = 0; i < n; ++i) {
    setBaud(kSensorBaudCandidates[i]);
    // Any register the profile actually uses will do as a liveness probe.
    if (transaction(kReadOps[0].addr, 1, &probe)) return true;
  }
  setBaud(SENSOR_BAUD_DEFAULT);
  return false;
}

void SoilSensor::scanRegisters(uint16_t first, uint16_t last, Print& out) {
  out.printf("Scanning 0x%04X..0x%04X at %lu baud, slave 0x%02X\r\n",
             first, last, (unsigned long)baud_, SENSOR_SLAVE_ID);
  uint16_t found = 0;
  for (uint32_t a = first; a <= last; ++a) {
    uint16_t v = 0;
    if (transaction((uint16_t)a, 1, &v)) {
      out.printf("  0x%04X = %5u  (0x%04X)  signed %6d   /10 %.1f  /100 %.2f\r\n",
                 (unsigned)a, v, v, (int)(int16_t)v, v / 10.0f, v / 100.0f);
      found++;
    }
    delay(MODBUS_INTERFRAME_MS);
  }
  out.printf("Scan finished: %u register(s) answered.\r\n", found);
}

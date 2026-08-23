#include "NpkSensor.h"
#include "NpkConfig.h"

// ---------------------------------------------------------------------------
// Serial port
// ---------------------------------------------------------------------------
#if NPK_USE_SOFTWARE_SERIAL
  #include <SoftwareSerial.h>
  static SoftwareSerial g_port(NPK_RS485_RX_PIN, NPK_RS485_TX_PIN);
  static inline void npkPortBegin(uint32_t baud) { g_port.begin(baud); }
  static inline void npkPortDrain(uint32_t baud) {
    // EspSoftwareSerial bit-bangs synchronously, so write() has already put
    // every bit on the wire. Only the final stop bit needs waiting out.
    delayMicroseconds(10UL * 1000000UL / baud + 100);
  }
#else
  static HardwareSerial& g_port = Serial1;
  static inline void npkPortBegin(uint32_t baud) {
    g_port.begin(baud, SERIAL_8N1, NPK_RS485_RX_PIN, NPK_RS485_TX_PIN);
  }
  static inline void npkPortDrain(uint32_t baud) {
    g_port.flush();                                    // drain the FIFO
    delayMicroseconds(10UL * 1000000UL / baud + 100);  // and the shift register
  }
#endif

// ---------------------------------------------------------------------------
// Channel table
// ---------------------------------------------------------------------------
/*
 * Two layouts, because this product family has variants that do not agree
 * with each other or with the manual.
 *
 * CONTIGUOUS (default, and what the probe on this project speaks):
 *   0x0000 moisture, 0x0001 temperature, 0x0002 conductivity, 0x0003 pH,
 *   0x0004 N, 0x0005 P, 0x0006 K - every one scaled by 0.1.
 *   Established from 83,883 samples logged by the original firmware, which
 *   read exactly this block: humidity 0-75.9 %, temperature 17.7-29.9 C,
 *   pH 3.9-9.0 against a datasheet spec of 3-9 pH, NPK 0-45 mg/kg. All
 *   physically sensible, and the pH range in particular is hard to get by
 *   accident.
 *
 * SPARSE (section 4.3 of the manual):
 *   0x0006 pH             unit 0.01 pH   -> 100 counts per pH
 *   0x0012 soil moisture  unit 0.1 %RH   ->  10 counts per %
 *   0x0013 soil temp      unit 0.1 degC  ->  10 counts per degC
 *   0x0015 conductivity   unit 1 us/cm   ->   1 count  per us/cm
 *   0x001E N, 0x001F P, 0x0020 K, unit 1 mg/kg
 *
 * Temperature is the only signed value: section 4.4.1 reads FF9BH back as
 * -10.1 degC.
 *
 * Reading this probe with the SPARSE map does not fail cleanly. It answers
 * with a valid CRC at addresses it does not implement, aliasing them onto the
 * low block: 0x0015 returns the temperature register and 0x0006 returns
 * potassium. The result is well-formed nonsense - 152.4 %RH, 4090 mg/kg - so
 * the range check below, not the CRC, is what catches a wrong profile.
 *
 * If a unit disagrees with both profiles the calibration A coefficient
 * absorbs the difference: a probe reporting pH in 0.01 steps where this
 * expects 0.1 is corrected with A = 0.1, no code change needed.
 */
// Limits are the measurement ranges in section 1.3, widened a little where the
// datasheet quotes a narrower spec than the register can express: pH is
// specced 3-9 but 0-14 is allowed so a miscalibrated probe still reports
// rather than silently dropping out.
#if NPK_REGISTER_PROFILE == NPK_PROFILE_CONTIGUOUS
const NpkChannel NPK_CHANNELS[NPK_CHANNEL_COUNT] = {
  // key             jsonKey         unit     scale  signed dec     lo       hi
  { "moisture",     "Humidity",     "%RH",    10.0f, false, 1,     0.0f,   100.0f },
  { "temperature",  "Temperature",  "degC",   10.0f, true,  1,   -40.0f,    80.0f },
  { "conductivity", "Conductivity", "us/cm",  10.0f, false, 1,     0.0f, 10000.0f },
  { "ph",           "PH",           "pH",     10.0f, false, 2,     0.0f,    14.0f },
  { "nitrogen",     "Nitrogen",     "mg/kg",  10.0f, false, 1,     0.0f,  1999.0f },
  { "phosphorus",   "Phosphorus",   "mg/kg",  10.0f, false, 1,     0.0f,  1999.0f },
  { "potassium",    "Potassium",    "mg/kg",  10.0f, false, 1,     0.0f,  1999.0f },
};
#else
const NpkChannel NPK_CHANNELS[NPK_CHANNEL_COUNT] = {
  { "moisture",     "Humidity",     "%RH",    10.0f, false, 1,     0.0f,   100.0f },
  { "temperature",  "Temperature",  "degC",   10.0f, true,  1,   -40.0f,    80.0f },
  { "conductivity", "Conductivity", "us/cm",   1.0f, false, 0,     0.0f, 10000.0f },
  { "ph",           "PH",           "pH",    100.0f, false, 2,     0.0f,    14.0f },
  { "nitrogen",     "Nitrogen",     "mg/kg",   1.0f, false, 0,     0.0f,  1999.0f },
  { "phosphorus",   "Phosphorus",   "mg/kg",   1.0f, false, 0,     0.0f,  1999.0f },
  { "potassium",    "Potassium",    "mg/kg",   1.0f, false, 0,     0.0f,  1999.0f },
};
#endif

int npkChannelFromKey(const char* key) {
  if (key == nullptr) return -1;
  for (uint8_t i = 0; i < NPK_CHANNEL_COUNT; ++i) {
    if (strcasecmp(key, NPK_CHANNELS[i].key) == 0) return i;
    if (strcasecmp(key, NPK_CHANNELS[i].jsonKey) == 0) return i;
  }
  if (strcasecmp(key, "humidity") == 0) return NPK_MOISTURE;
  if (strcasecmp(key, "temp") == 0)     return NPK_TEMPERATURE;
  if (strcasecmp(key, "ec") == 0)       return NPK_CONDUCTIVITY;
  if (strcasecmp(key, "n") == 0)        return NPK_NITROGEN;
  if (strcasecmp(key, "p") == 0)        return NPK_PHOSPHORUS;
  if (strcasecmp(key, "k") == 0)        return NPK_POTASSIUM;
  return -1;
}

// ---------------------------------------------------------------------------
// Register profile
// ---------------------------------------------------------------------------
// Each entry is one Modbus function-0x03 transaction. dest maps the n-th
// returned register onto a channel; -1 discards it.
struct NpkReadOp {
  uint16_t addr;
  uint8_t  count;
  int8_t   dest[7];
};

#if NPK_REGISTER_PROFILE == NPK_PROFILE_CONTIGUOUS
// One transaction for all seven registers. This is the frame the original
// sketch sent, and the 83,883 samples it logged confirm the layout.
static const NpkReadOp kOps[] = {
  { 0x0000, 7, { NPK_MOISTURE, NPK_TEMPERATURE, NPK_CONDUCTIVITY, NPK_PH,
                 NPK_NITROGEN, NPK_PHOSPHORUS, NPK_POTASSIUM } },
};
#else
// Section 4.3 of the manual. That map is scattered, so this is four
// transactions rather than one; each frame is one the manual prints verbatim
// in section 4.4.
static const NpkReadOp kOps[] = {
  { 0x0006, 1, { NPK_PH, -1, -1, -1, -1, -1, -1 } },
  { 0x0012, 2, { NPK_MOISTURE, NPK_TEMPERATURE, -1, -1, -1, -1, -1 } },
  { 0x0015, 1, { NPK_CONDUCTIVITY, -1, -1, -1, -1, -1, -1 } },
  { 0x001E, 3, { NPK_NITROGEN, NPK_PHOSPHORUS, NPK_POTASSIUM, -1, -1, -1, -1 } },
};
#endif

static const uint8_t kOpCount = sizeof(kOps) / sizeof(kOps[0]);

// ---------------------------------------------------------------------------
// CRC-16/MODBUS, low byte transmitted first (manual section 4.2).
// ---------------------------------------------------------------------------
uint16_t npkModbusCrc(const uint8_t* data, uint8_t len) {
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

void NpkSensor::begin() {
  pinMode(NPK_DE_RE_PIN, OUTPUT);
  driveTransmit(false);
  setBaud(NPK_BAUD_DEFAULT);
}

void NpkSensor::setBaud(uint32_t baud) {
  // Only tear the port down if it was actually opened. Calling end() on a
  // SoftwareSerial that was never begun touches buffers it has not allocated.
  static bool started = false;
  baud_ = baud;
  if (started) g_port.end();
  npkPortBegin(baud);
  started = true;
  delay(20);
}

void NpkSensor::driveTransmit(bool enable) {
  digitalWrite(NPK_DE_RE_PIN, enable ? HIGH : LOW);
  delayMicroseconds(50);
}

bool NpkSensor::sendFrame(const uint8_t* frame, uint8_t len) {
  while (g_port.available()) g_port.read();   // discard stale bytes

  driveTransmit(true);
  size_t written = g_port.write(frame, len);
  npkPortDrain(baud_);
  driveTransmit(false);

  return written == len;
}

int NpkSensor::readFrame(uint8_t* buf, uint8_t expected, uint32_t timeoutMs) {
  uint32_t deadline = millis() + timeoutMs;
  uint8_t n = 0;
  while (n < expected && (int32_t)(millis() - deadline) < 0) {
    if (g_port.available()) {
      buf[n++] = (uint8_t)g_port.read();
      deadline = millis() + NPK_INTERFRAME_MS + 20;   // inter-byte gap
    }
  }
  return n;
}

bool NpkSensor::transaction(uint16_t addr, uint8_t count, uint16_t* regs) {
  if (count == 0 || count > 8) { lastError_ = "register count out of range"; return false; }

  uint8_t frame[8] = {
    NPK_SLAVE_ID, 0x03,
    (uint8_t)(addr >> 8), (uint8_t)(addr & 0xFF),
    (uint8_t)(count >> 8), (uint8_t)(count & 0xFF),
    0, 0
  };
  uint16_t crc = npkModbusCrc(frame, 6);
  frame[6] = (uint8_t)(crc & 0xFF);   // CRC_L first
  frame[7] = (uint8_t)(crc >> 8);

  const uint8_t expected = 5 + 2 * count;   // id, fn, bytecount, data, crc
  uint8_t rx[5 + 2 * 8];

  for (uint8_t attempt = 0; attempt < NPK_RETRIES; ++attempt) {
    if (attempt) delay(NPK_INTERFRAME_MS * 2);
    if (!sendFrame(frame, sizeof(frame))) { lastError_ = "uart write failed"; continue; }

    int n = readFrame(rx, expected, NPK_RESPONSE_TIMEOUT_MS);
    if (n == 0) { lastError_ = "no reply"; continue; }

    if (n == 5 && (rx[1] & 0x80))  { lastError_ = "modbus exception"; continue; }
    if (n < expected)              { lastError_ = "short reply"; continue; }
    if (rx[0] != NPK_SLAVE_ID)     { lastError_ = "wrong slave id"; continue; }
    if (rx[1] != 0x03)             { lastError_ = "wrong function code"; continue; }
    if (rx[2] != 2 * count)        { lastError_ = "bad byte count"; continue; }

    uint16_t want = npkModbusCrc(rx, expected - 2);
    uint16_t got  = (uint16_t)rx[expected - 1] << 8 | rx[expected - 2];
    if (want != got)               { lastError_ = "crc mismatch"; continue; }

    for (uint8_t i = 0; i < count; ++i) {
      regs[i] = (uint16_t)rx[3 + 2 * i] << 8 | rx[4 + 2 * i];   // high byte first
    }
    lastError_ = "";
    return true;
  }
  return false;
}

bool NpkSensor::read(NpkReading& out) {
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    out.raw[c] = 0;
    out.scaled[c] = 0.0f;
    out.valid[c] = false;
    out.outOfRange[c] = false;
  }
  out.failedOps = 0;

  for (uint8_t op = 0; op < kOpCount; ++op) {
    uint16_t regs[7] = { 0 };
    if (!transaction(kOps[op].addr, kOps[op].count, regs)) {
      out.failedOps++;
      continue;
    }
    for (uint8_t i = 0; i < kOps[op].count; ++i) {
      int8_t ch = kOps[op].dest[i];
      if (ch < 0) continue;
      out.raw[ch] = regs[i];
      // Temperature is the only two's complement value (manual 4.4.1).
      float counts = NPK_CHANNELS[ch].isSigned ? (float)(int16_t)regs[i]
                                               : (float)regs[i];
      const float v = counts / NPK_CHANNELS[ch].scale;
      out.scaled[ch] = v;
      out.valid[ch] = true;

#if NPK_RANGE_CHECK
      // The probe answers with a valid CRC at addresses it does not
      // implement, aliasing them onto the low block, so a wrong register
      // profile produces well-formed nonsense rather than a timeout. The
      // physical limits are the only thing that catches it.
      if (v < NPK_CHANNELS[ch].lo || v > NPK_CHANNELS[ch].hi) {
        out.valid[ch] = false;
        out.outOfRange[ch] = true;
        lastError_ = "reading outside the physical range - wrong register profile?";
      }
#endif
    }
    if (op + 1 < kOpCount) delay(NPK_INTERFRAME_MS);
  }

  out.complete = true;
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    if (!out.valid[c]) { out.complete = false; break; }
  }
  return out.complete;
}

bool NpkSensor::readAveraged(NpkReading& out, uint8_t samples) {
  if (samples == 0) samples = 1;

  double   sum[NPK_CHANNEL_COUNT]  = { 0 };
  uint16_t hits[NPK_CHANNEL_COUNT] = { 0 };
  NpkReading sample;
  uint8_t good = 0;

  for (uint8_t s = 0; s < samples; ++s) {
    if (read(sample)) good++;
    for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
      if (sample.valid[c]) { sum[c] += sample.scaled[c]; hits[c]++; }
    }
    if (s + 1 < samples) delay(120);
  }

  out = sample;   // keep the last raw words for reference
  out.complete = true;
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    out.valid[c] = hits[c] > 0;
    out.scaled[c] = out.valid[c] ? (float)(sum[c] / hits[c]) : 0.0f;
    if (!out.valid[c]) out.complete = false;
  }
  return good > 0;
}

bool NpkSensor::detectBaud() {
  const uint8_t n = sizeof(NPK_BAUD_CANDIDATES) / sizeof(NPK_BAUD_CANDIDATES[0]);
  uint16_t probe = 0;
  for (uint8_t i = 0; i < n; ++i) {
    setBaud(NPK_BAUD_CANDIDATES[i]);
    // Any register the profile actually uses works as a liveness probe.
    if (transaction(kOps[0].addr, 1, &probe)) return true;
  }
  setBaud(NPK_BAUD_DEFAULT);
  return false;
}

void NpkSensor::scanRegisters(uint16_t first, uint16_t last, Print& out) {
  out.printf("Scanning 0x%04X..0x%04X at %lu baud, slave 0x%02X\r\n",
             first, last, (unsigned long)baud_, NPK_SLAVE_ID);
  uint16_t found = 0;
  for (uint32_t a = first; a <= last; ++a) {
    uint16_t v = 0;
    if (transaction((uint16_t)a, 1, &v)) {
      out.printf("  0x%04X = %5u  (0x%04X)  signed %6d   /10 %.1f  /100 %.2f\r\n",
                 (unsigned)a, v, v, (int)(int16_t)v, v / 10.0f, v / 100.0f);
      found++;
    }
    delay(NPK_INTERFRAME_MS);
  }
  out.printf("Scan finished: %u register(s) answered.\r\n", found);
}

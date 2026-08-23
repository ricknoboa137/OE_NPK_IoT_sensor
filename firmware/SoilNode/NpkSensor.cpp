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
 * Scale factors come from section 5.3 of the VMS-3001-TR manual, and are
 * confirmed by the worked example in section 5.4. That example reads
 *
 *     01 03 00 00 00 04 44 09
 *  -> 01 03 08 02 92 FF 9B 03 E8 00 38 57 B6
 *
 * and both CRCs verify. Decoding it:
 *
 *   0x0000 moisture     0x0292 =  658  /10 -> 65.8 %     as documented
 *   0x0001 temperature  0xFF9B = -101  /10 -> -10.1 degC as documented
 *   0x0002 conductivity 0x03E8 = 1000  /1  -> 1000 us/cm as documented
 *   0x0003 pH           0x0038 =   56  /10 -> 5.6 pH     as documented
 *
 * Temperature is the only signed value; below zero it is sent as a two's
 * complement.
 *
 * Note that conductivity is NOT scaled - the manual gives it in whole us/cm,
 * and the resolution line in section 1.3 agrees at 1 us/cm. The original
 * sketch divided it by ten. It is moot here because this unit does not
 * return conductivity at all, but it matters if the channel is restored.
 *
 * N, P and K have no registers in this manual. This is a four-parameter
 * probe - moisture, temperature, conductivity, pH - and the model-selection
 * table in section 1.5 offers only THPH, ECPH and ECTHPH variants. Slots 4,
 * 5 and 6 of the block read here are undocumented. They are kept because the
 * original decoder used them and the logged dataset carries them, but
 * whatever they hold is not soil nitrogen, phosphorus or potassium.
 *
 * A pure scale mismatch needs no code change: the calibration A coefficient
 * absorbs it.
 */
// Limits are the measurement ranges in section 1.3, widened where the manual
// quotes a narrower spec than the register can express: pH is specced 3-9 but
// 0-14 is allowed so a badly calibrated probe still reports rather than
// silently dropping out. The undocumented slots get a permissive 0-1999,
// enough to catch a gross misread without pretending to know the range.
const NpkChannel NPK_CHANNELS[NPK_CHANNEL_COUNT] = {
  // key            jsonKey        unit     scale  signed dec     lo       hi
  { "moisture",    "Humidity",    "%RH",    10.0f, false, 1,     0.0f,  100.0f },
  { "temperature", "Temperature", "degC",   10.0f, true,  1,   -40.0f,   80.0f },
  { "ph",          "PH",          "pH",     10.0f, false, 1,     0.0f,   14.0f },
  { "nitrogen",    "Nitrogen",    "mg/kg",  10.0f, false, 1,     0.0f, 1999.0f },
  { "phosphorus",  "Phosphorus",  "mg/kg",  10.0f, false, 1,     0.0f, 1999.0f },
  { "potassium",   "Potassium",   "mg/kg",  10.0f, false, 1,     0.0f, 1999.0f },
};

int npkChannelFromKey(const char* key) {
  if (key == nullptr) return -1;
  for (uint8_t i = 0; i < NPK_CHANNEL_COUNT; ++i) {
    if (strcasecmp(key, NPK_CHANNELS[i].key) == 0) return i;
    if (strcasecmp(key, NPK_CHANNELS[i].jsonKey) == 0) return i;
  }
  if (strcasecmp(key, "humidity") == 0) return NPK_MOISTURE;
  if (strcasecmp(key, "temp") == 0)     return NPK_TEMPERATURE;
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

// One transaction, seven registers from 0x0000 - byte for byte the request
// the original sketch sent (01 03 00 00 00 07, CRC 04 08), and the slots are
// mapped in the order the original decoder used, so logged data stays
// comparable. Slot 2 is conductivity, which this unit does not return, so it
// is discarded rather than published.
static const NpkReadOp kOps[] = {
  { NPK_REGISTER_START, NPK_REGISTER_COUNT,
    { NPK_MOISTURE,     // slot 0  0x0000  moisture
      NPK_TEMPERATURE,  // slot 1  0x0001  temperature
      -1,               // slot 2  0x0002  conductivity, not fitted
      NPK_PH,           // slot 3  0x0003  pH
      NPK_NITROGEN,     // slot 4  0x0004  undocumented
      NPK_PHOSPHORUS,   // slot 5  0x0005  undocumented
      NPK_POTASSIUM }   // slot 6  0x0006  undocumented
  },
};

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

#include "NpkConsole.h"
#include "NpkConfig.h"
#include "NpkJson.h"

static const int    kMaxArgs     = 8;
static const size_t kReplyCap    = NPK_MQTT_BUFFER - 64;
static const size_t kMaxLineHeld = 192;   // longest line kept back across a split

// Publish everything up to the last complete line, mark it as continuing, and
// keep the partial trailing line for the next part.
void NpkChunkedPrint::flushPart() {
  if (len_ == 0) return;

  size_t split = (lastNewline_ > 0) ? lastNewline_ : len_;
  size_t tailLen = len_ - split;

  // A single line longer than the hold buffer cannot be carried over, so it
  // is cut here instead. Nothing this firmware prints comes close.
  char tail[kMaxLineHeld];
  if (tailLen >= sizeof(tail)) {
    split = len_;
    tailLen = 0;
  }
  memcpy(tail, buf_ + split, tailLen);

  memcpy(buf_ + split, NPK_REPLY_CONTINUES, sizeof(NPK_REPLY_CONTINUES) - 1);
  buf_[split + sizeof(NPK_REPLY_CONTINUES) - 1] = '\0';
  if (net_) net_->publish(topic_, buf_);
  parts_++;

  memcpy(buf_, tail, tailLen);
  len_ = tailLen;
  buf_[len_] = '\0';
  lastNewline_ = 0;
  for (size_t i = 0; i < len_; ++i) {
    if (buf_[i] == '\n') lastNewline_ = i + 1;
  }
}

void NpkConsole::begin(NpkSensor* sensor, NpkCal* cal, NpkNet* net) {
  sensor_ = sensor;
  cal_ = cal;
  net_ = net;
  serialLen_ = 0;
  serialBuf_[0] = '\0';
}

// ---------------------------------------------------------------------------
// Transports
// ---------------------------------------------------------------------------

void NpkConsole::pollSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (serialLen_ > 0) {
        serialBuf_[serialLen_] = '\0';
        execute(serialBuf_, Serial);
        serialLen_ = 0;
      }
      continue;
    }
    if (serialLen_ + 1 < sizeof(serialBuf_)) serialBuf_[serialLen_++] = c;
  }
}

void NpkConsole::handleMqtt(const uint8_t* payload, unsigned int length) {
  char line[160];

  if (length > 0 && payload[0] == '{') {
    if (!jsonToLine(payload, length, line, sizeof(line))) {
      net_->publish(NPK_TOPIC_REPLY, "error: could not parse JSON command");
      return;
    }
  } else {
    unsigned int n = min(length, (unsigned int)(sizeof(line) - 1));
    memcpy(line, payload, n);
    line[n] = '\0';
  }

  Serial.printf("[cmd] via mqtt: %s\r\n", line);

  // Output streams out as it is produced, split across as many NPKreply
  // messages as it takes, so nothing is ever truncated however long it runs.
  // The serial echo happens inside the sink and is not chunked.
  char buf[kReplyCap];
  NpkChunkedPrint reply(net_, NPK_TOPIC_REPLY, buf, sizeof(buf), true);
  execute(line, reply);
  reply.finish();

  if (reply.parts() > 1) {
    Serial.printf("[cmd] reply sent as %u parts\r\n", (unsigned)reply.parts());
  }
}

// Normalise a JSON command object into the text form.
bool NpkConsole::jsonToLine(const uint8_t* payload, unsigned int length,
                            char* out, size_t cap) {
  NPK_JSON_DOC(doc, 512);
  if (deserializeJson(doc, payload, length) != DeserializationError::Ok) return false;

  // Read the string fields defensively: chaining operator| across two
  // JsonVariants behaves differently between ArduinoJson 6 and 7.
  const char* cmd = doc["cmd"].as<const char*>();
  if (cmd == nullptr) cmd = doc["command"].as<const char*>();
  if (cmd == nullptr) cmd = "";
  if (*cmd == '\0') return false;

  const char* ch = doc["ch"].as<const char*>();
  if (ch == nullptr) ch = doc["channel"].as<const char*>();
  if (ch == nullptr) ch = "";

  if (!strcmp(cmd, "cal_set")) {
    snprintf(out, cap, "cal set %s %.6g %.6g", ch,
             (double)(doc["a"] | 1.0f), (double)(doc["b"] | 0.0f));
  } else if (!strcmp(cmd, "cal_1p") || !strcmp(cmd, "cal_onepoint")) {
    snprintf(out, cap, "cal 1p %s %.6g", ch, (double)(doc["ref"] | 0.0f));
  } else if (!strcmp(cmd, "cal_low")) {
    snprintf(out, cap, "cal low %s %.6g", ch, (double)(doc["ref"] | 0.0f));
  } else if (!strcmp(cmd, "cal_high")) {
    snprintf(out, cap, "cal high %s %.6g", ch, (double)(doc["ref"] | 0.0f));
  } else if (!strcmp(cmd, "cal_clear") || !strcmp(cmd, "cal_reset")) {
    snprintf(out, cap, "cal clear %s", *ch ? ch : "all");
  } else if (!strcmp(cmd, "cal_get") || !strcmp(cmd, "cal_list")) {
    snprintf(out, cap, "cal list");
  } else if (!strcmp(cmd, "scan")) {
    snprintf(out, cap, "scan %u %u",
             (unsigned)(doc["first"] | 0), (unsigned)(doc["last"] | 0x30));
  } else if (!strcmp(cmd, "mqtt")) {
    snprintf(out, cap, "mqtt %s %u", (const char*)(doc["host"] | ""),
             (unsigned)(doc["port"] | 1883));
  } else if (!strcmp(cmd, "mqttauth") || !strcmp(cmd, "mqtt_auth")) {
    const char* u = doc["user"].as<const char*>();
    const char* w = doc["pass"].as<const char*>();
    if (u == nullptr || *u == '\0') snprintf(out, cap, "mqttauth clear");
    else snprintf(out, cap, "mqttauth %s %s", u, (w && *w) ? w : "");
  } else if (!strcmp(cmd, "wifi_portal")) {
    snprintf(out, cap, "wifi portal");
  } else if (!strcmp(cmd, "wifi_reset")) {
    snprintf(out, cap, "wifi reset");
  } else {
    // Deliberate passthrough, not a gap in the mapping.
    //
    // Anything without a structured form above is handed to the text parser
    // verbatim, so every console command is reachable over MQTT without a
    // second grammar to keep in step. This is what carries the bare commands
    // (help, status, read, reboot) and the whole "sensor" family, including
    // arguments: {"cmd":"sensor cal n low 50"} arrives at the same parser as
    // typing that line.
    //
    // The parser splits on spaces and tabs only, so the one thing that must
    // not get through is an embedded newline or control character - those
    // would let a single JSON field inject what looks like a second command.
    for (const char* p = cmd; *p; ++p) {
      if ((unsigned char)*p < 0x20 || *p == 0x7F) return false;
    }
    snprintf(out, cap, "%s", cmd);
  }
  return true;
}

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

void NpkConsole::execute(const char* line, Print& out) {
  char work[160];
  strncpy(work, line, sizeof(work) - 1);
  work[sizeof(work) - 1] = '\0';

  char* argv[kMaxArgs];
  int argc = 0;
  char* save = nullptr;
  for (char* tok = strtok_r(work, " \t", &save);
       tok != nullptr && argc < kMaxArgs;
       tok = strtok_r(nullptr, " \t", &save)) {
    argv[argc++] = tok;
  }
  if (argc == 0) return;
  dispatch(argv, argc, out);
}

void NpkConsole::dispatch(char** argv, int argc, Print& out) {
  const char* cmd = argv[0];

  if (!strcasecmp(cmd, "help") || !strcmp(cmd, "?")) {
    cmdHelp(out);
  } else if (!strcasecmp(cmd, "status")) {
    cmdStatus(out);
  } else if (!strcasecmp(cmd, "read")) {
    cmdRead(out);
  } else if (!strcasecmp(cmd, "scan")) {
    cmdScan(argv, argc, out);
  } else if (!strcasecmp(cmd, "cal")) {
    cmdCal(argv, argc, out);
  } else if (!strcasecmp(cmd, "sensor")) {
    cmdSensor(argv, argc, out);
  } else if (!strcasecmp(cmd, "mqtt")) {
    if (argc < 2) { out.println("usage: mqtt <host> [port]"); return; }
    uint16_t port = (argc >= 3) ? (uint16_t)strtol(argv[2], nullptr, 10) : net_->port();
    if (net_->setBroker(argv[1], port)) out.printf("broker set to %s:%u\r\n", argv[1], port);
    else out.println("error: invalid broker");
  } else if (!strcasecmp(cmd, "mqttauth")) {
    if (argc < 2) {
      out.println("usage: mqttauth <user> [password]   |   mqttauth clear");
      return;
    }
    if (!strcasecmp(argv[1], "clear") || !strcasecmp(argv[1], "none")) {
      net_->setAuth("", "");
      out.println("MQTT auth cleared - connecting anonymously");
      return;
    }
    net_->setAuth(argv[1], argc >= 3 ? argv[2] : "");
    out.printf("MQTT auth set: user %s%s\r\n", argv[1],
               argc >= 3 ? "" : " (password unchanged)");
  } else if (!strcasecmp(cmd, "wifi")) {
    if (argc >= 2 && !strcasecmp(argv[1], "reset")) {
      out.println("clearing WiFi credentials, rebooting");
      out.flush();
      net_->forgetWiFi();
    } else if (argc >= 2 && !strcasecmp(argv[1], "portal")) {
      out.println("opening config portal");
      out.flush();
      net_->startPortal();
    } else {
      out.println("usage: wifi portal | wifi reset");
    }
  } else if (!strcasecmp(cmd, "reboot") || !strcasecmp(cmd, "restart")) {
    out.println("rebooting");
    out.flush();
    delay(200);
    ESP.restart();
  } else {
    out.printf("unknown command \"%s\" - type help\r\n", cmd);
  }
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

void NpkConsole::cmdHelp(Print& out) {
  out.println();
  out.println(F("Commands ------------------------------------------------------"));
  out.println(F("  read                      take a reading, raw + calibrated"));
  out.println(F("  status                    firmware, link and sensor state"));
  out.println(F("  scan [first] [last]       probe Modbus registers"));
  out.println(F("  scan nz [first] [last]    ... skipping the zeros. This probe"));
  out.println(F("                            answers at every address, so a plain"));
  out.println(F("                            sweep is mostly meaningless lines."));
  out.println(F("  mqtt <host> [port]        change broker, stored in NVS"));
  out.println(F("  mqttauth <user> [pass]    broker credentials, stored in NVS"));
  out.println(F("  mqttauth clear            connect anonymously"));
  out.println(F("  wifi portal               open the config portal now"));
  out.println(F("  wifi reset                forget WiFi and reboot"));
  out.println(F("  reboot"));
  out.println();
  out.println(F("Calibration ---------------------------------------------------"));
  out.println(F("  Reported value = A * raw + B, per channel, stored in NVS."));
  out.println();
  out.println(F("  cal                       list A and B for every channel"));
  out.println(F("  cal set  <ch> <A> <B>     write both coefficients directly"));
  out.println(F("  cal 1p   <ch> <ref>       offset trim: keep A, solve B"));
  out.println(F("  cal low  <ch> <ref>       two-point step 1: low reference"));
  out.println(F("  cal high <ch> <ref>       two-point step 2: solve A and B"));
  out.println(F("  cal clear <ch|all>        back to A=1, B=0"));
  out.println(F("  cal json                  the same table, machine readable"));
  out.println(F("  cal export                replayable \"cal set\" lines - this"));
  out.println(F("                            is the backup, since calibration"));
  out.println(F("                            lives in this board's NVS"));
  out.println();
  out.println(F("The probe has its own calibration registers, separate from"));
  out.println(F("the above. Those change what it reports; \"cal\" changes how"));
  out.println(F("this firmware interprets what it reports."));
  out.println();
  out.println(F("  sensor                    read the probe's own registers"));
  out.println(F("  sensor cal <n|p|k> low  <ref>     two-point solve, written"));
  out.println(F("  sensor cal <n|p|k> high <ref>     into the probe itself"));
  out.println(F("  sensor offset <temp|hum|ec|ph> <raw>"));
  out.println(F("  sensor factor <n|p|k> <value>     gain, IEEE-754 float"));
  out.println(F("  sensor npk    <n|p|k> <mg/kg>     write a lab-measured value"));
  out.println();
  out.println(F("  Channels: moisture temperature conductivity ph"));
  out.println(F("            nitrogen phosphorus potassium"));
  out.println();
  out.println(F("  Example, pH against 4.00 and 7.00 buffers:"));
  out.println(F("    (probe in the 4.00 buffer, wait for a stable reading)"));
  out.println(F("    cal low  ph 4.00"));
  out.println(F("    (rinse, move to the 7.00 buffer, wait again)"));
  out.println(F("    cal high ph 7.00"));
  out.println();
  out.println(F("  Each capture averages several sweeps, so give the probe"));
  out.println(F("  time to settle before typing the command."));
  out.println();
}

void NpkConsole::cmdStatus(Print& out) {
  out.println();
  out.printf("Firmware : %s %s\r\n", NPK_FW_NAME, NPK_FW_VERSION);
  out.printf("Sensor   : CWT soil NPK 5-pin, %u registers from 0x%04X%s\r\n",
             (unsigned)NPK_REG_COUNT, (unsigned)NPK_REG_MEASUREMENTS,
             NPK_ENABLE_CONDUCTIVITY ? "" : ", conductivity not published");
  out.printf("Port     : %s\r\n",
             NPK_USE_SOFTWARE_SERIAL ? "SoftwareSerial" : "hardware UART1");
  out.printf("RS-485   : %lu baud 8N1, slave 0x%02X, DE/RE on GPIO%d\r\n",
             (unsigned long)sensor_->baud(), NPK_SLAVE_ID, NPK_DE_RE_PIN);
  out.printf("Last err : %s\r\n",
             *sensor_->lastError() ? sensor_->lastError() : "none");
  out.printf("Uptime   : %lu s   free heap %u B\r\n",
             (unsigned long)(millis() / 1000), (unsigned)ESP.getFreeHeap());
  net_->printStatus(out);
  listCalibration(out);
}

void NpkConsole::cmdRead(Print& out) {
  NpkReading r;
  sensor_->read(r);

  out.println();
  out.printf("%-14s %8s  %10s  %10s   %s\r\n",
             "channel", "raw", "scaled", "calibrated", "unit");
  bool anyOutOfRange = false;
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    if (r.outOfRange[c]) {
      // The register answered, so this is not a comms fault - the value is
      // simply impossible, which means the map or the scale is wrong.
      anyOutOfRange = true;
      out.printf("%-14s %8u  %10.*f  %10s   %s  (limit %.4g..%.4g)\r\n",
                 NPK_CHANNELS[c].key, (unsigned)r.raw[c],
                 NPK_CHANNELS[c].decimals, r.scaled[c], "OUT OF RANGE",
                 NPK_CHANNELS[c].unit, NPK_CHANNELS[c].lo, NPK_CHANNELS[c].hi);
      continue;
    }
    if (!r.valid[c]) {
      out.printf("%-14s %8s  %10s  %10s   %s\r\n",
                 NPK_CHANNELS[c].key, "-", "-", "no reply", NPK_CHANNELS[c].unit);
      continue;
    }
    const int d = NPK_CHANNELS[c].decimals;
    out.printf("%-14s %8u  %10.*f  %10.*f   %s\r\n",
               NPK_CHANNELS[c].key, (unsigned)r.raw[c],
               d, r.scaled[c],
               d, cal_->apply(c, r.scaled[c]),
               NPK_CHANNELS[c].unit);
  }
  if (r.failedOps) {
    out.printf("%u transaction(s) got no usable reply: %s\r\n",
               r.failedOps, sensor_->lastError());
  }
  if (anyOutOfRange) {
    out.println();
    out.println(F("Those registers answered with a valid CRC, so the wiring"));
    out.println(F("is fine - the value itself is impossible, which means the"));
    out.println(F("scale or the slot mapping is wrong. Run \"scan\" and check"));
    out.println(F("the read op in NpkSensor.cpp against the manual."));
  }
  out.println();
}

void NpkConsole::cmdScan(char** argv, int argc, Print& out) {
  int argi = 1;
  bool nonZeroOnly = false;
  if (argc > argi && (!strcasecmp(argv[argi], "nz") ||
                      !strcasecmp(argv[argi], "nonzero"))) {
    nonZeroOnly = true;
    argi++;
  }

  uint16_t first = 0x0000;
  uint16_t last  = 0x0030;
  if (argc > argi)     first = (uint16_t)strtol(argv[argi], nullptr, 0);
  if (argc > argi + 1) last  = (uint16_t)strtol(argv[argi + 1], nullptr, 0);
  if (last < first) { out.println("error: last register is below first"); return; }

  // A verbose sweep prints a line per address, and this probe answers at all
  // of them, so the useful range is small. A filtered sweep is mostly silent
  // and can cover far more ground.
  const uint32_t span = (uint32_t)last - first + 1;
  const uint32_t cap = nonZeroOnly ? 8192UL : 512UL;
  if (span > cap) {
    out.printf("error: %lu registers exceeds the %lu limit for this mode\r\n",
               (unsigned long)span, (unsigned long)cap);
    if (!nonZeroOnly) {
      out.println("       use \"scan nz <first> <last>\" for a wider sweep");
    }
    return;
  }
  sensor_->scanRegisters(first, last, out, nonZeroOnly);
}

int NpkConsole::resolveChannel(const char* name, Print& out) {
  int ch = npkChannelFromKey(name);
  if (ch < 0) {
    out.printf("error: unknown channel \"%s\". Try:", name ? name : "");
    for (uint8_t i = 0; i < NPK_CHANNEL_COUNT; ++i) out.printf(" %s", NPK_CHANNELS[i].key);
    out.println();
  }
  return ch;
}

// Average several sweeps so a single noisy frame cannot skew the coefficients.
bool NpkConsole::captureRaw(uint8_t ch, float& rawOut, Print& out) {
  out.printf("sampling %s (%u sweeps) ...\r\n", NPK_CHANNELS[ch].key, NPK_CAL_SAMPLES);
  NpkReading r;
  sensor_->readAveraged(r, NPK_CAL_SAMPLES);
  if (!r.valid[ch]) {
    out.printf("error: no valid reading for %s (%s)\r\n",
               NPK_CHANNELS[ch].key, sensor_->lastError());
    return false;
  }
  rawOut = r.scaled[ch];
  out.printf("  raw average = %.*f %s\r\n", NPK_CHANNELS[ch].decimals, rawOut,
             NPK_CHANNELS[ch].unit);

  // A hard zero is a poor thing to anchor a calibration on. Nitrogen reads
  // exactly 0 in some soils, and the firmware cannot tell that apart from the
  // probe bottoming out - the register answered, with a good CRC, saying zero.
  // Not refused, because a genuine zero reference is legitimate, but a
  // two-point fit anchored here inherits whatever the floor is doing.
  if (rawOut == 0.0f) {
    out.printf("note: %s is reading exactly 0. That may be real, or the probe\r\n",
               NPK_CHANNELS[ch].key);
    out.println("      bottoming out - the two are indistinguishable from here.");
    out.println("      Prefer a point where the channel is actually responding.");
  }
  return true;
}

void NpkConsole::listCalibration(Print& out) {
  out.println();
  out.printf("%-14s %12s %12s   %s\r\n", "channel", "A (gain)", "B (offset)", "state");
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    NpkCoeff k = cal_->get(c);
    // No attempt is made to judge a coefficient pair in the abstract. Testing
    // the transform across the channel's physical range sounds appealing but
    // is wrong in both directions: every channel except temperature has a low
    // limit of 0, so a pure gain always maps 0 to 0 and looks fine however
    // absurd it is, while a legitimate scale correction operates on raw values
    // that are nowhere near the output range and would be flagged wrongly.
    // The honest signal is what the coefficients do to an actual reading, and
    // that is checked at publish time and reported by "read".
    const char* state = cal_->isDefault(c) ? "default" : "calibrated";
    if (cal_->hasPendingLow(c)) state = "low point captured";
    out.printf("%-14s %12.5f %12.5f   %s\r\n", NPK_CHANNELS[c].key, k.a, k.b, state);
  }
  out.println();
}

// ---------------------------------------------------------------------------
// The sensor's own calibration registers
// ---------------------------------------------------------------------------
// Distinct from "cal", which corrects readings inside the ESP32. These write
// into the probe itself and persist there, independent of this firmware.

struct NpkNutrientReg {
  const char* key;
  uint16_t    measurement;   // the writable N/P/K reading register
  uint16_t    factorHigh;    // factor float, high word; +1 low, +2 offset
  uint8_t     channel;       // the matching NpkChannelId, for taking readings
};
static const NpkNutrientReg kNutrients[] = {
  { "n", NPK_REG_NITROGEN,   NPK_REG_N_FACTOR, NPK_NITROGEN   },
  { "p", NPK_REG_PHOSPHORUS, NPK_REG_P_FACTOR, NPK_PHOSPHORUS },
  { "k", NPK_REG_POTASSIUM,  NPK_REG_K_FACTOR, NPK_POTASSIUM  },
};

// Two-point capture for the probe-side coefficients. Held in RAM only, like
// the firmware-side equivalent, so a reboot mid-procedure starts over.
struct NpkSensorPoint {
  bool  held;
  float reference;   // what the standard actually is
  float reported;    // what the probe said, with its current A and B applied
};
static NpkSensorPoint g_sensorLow[3];

// Read the probe's current gain and offset for one nutrient.
static bool npkReadAB(NpkSensor* s, const NpkNutrientReg* nr,
                      float& a, float& b, const char** why) {
  const char* dummy = nullptr;
  if (why == nullptr) why = &dummy;
  if (!s->readFloat(nr->factorHigh, a)) { *why = s->lastError(); return false; }
  delay(NPK_INTERFRAME_MS * 2);
  uint16_t raw = 0;
  if (!s->readRegisters(nr->factorHigh + 2, 1, &raw)) { *why = s->lastError(); return false; }
  b = (float)(int16_t)raw;
  *why = "";
  return true;
}

static const NpkNutrientReg* npkNutrientFromKey(const char* s) {
  if (!s) return nullptr;
  for (uint8_t i = 0; i < 3; ++i) {
    if (!strcasecmp(s, kNutrients[i].key)) return &kNutrients[i];
  }
  if (!strcasecmp(s, "nitrogen"))   return &kNutrients[0];
  if (!strcasecmp(s, "phosphorus")) return &kNutrients[1];
  if (!strcasecmp(s, "potassium"))  return &kNutrients[2];
  return nullptr;
}

void NpkConsole::cmdSensor(char** argv, int argc, Print& out) {
  const char* sub = (argc >= 2) ? argv[1] : "show";

  if (!strcasecmp(sub, "show") || !strcasecmp(sub, "list")) {
    out.println();
    out.println(F("Sensor-side calibration (stored in the probe, not the ESP32)"));

    // These three are the only registers the manual gives factory defaults
    // for, which makes them a free end-to-end check: if 0x0023 reads 55 and
    // 0x0024 reads 50, then addressing, framing and decoding are all correct.
    struct { const char* name; uint16_t reg; int dflt; } facs[] = {
      { "conductivity factor", 0x0022,  0 },
      { "salinity factor",     0x0023, 55 },
      { "TDS factor",          0x0024, 50 },
    };
    for (uint8_t i = 0; i < 3; ++i) {
      uint16_t v = 0;
      if (sensor_->readRegisters(facs[i].reg, 1, &v)) {
        out.printf("  0x%04X  %-20s %6u   factory default %d%s\r\n",
                   facs[i].reg, facs[i].name, v, facs[i].dflt,
                   ((int)v == facs[i].dflt) ? "" : "   <-- changed");
      } else {
        out.printf("  0x%04X  %-20s no reply (%s)\r\n", facs[i].reg, facs[i].name,
                   sensor_->lastError());
      }
      delay(20);
    }
    out.println();
    struct { const char* name; uint16_t reg; float scale; } offs[] = {
      { "temperature offset", NPK_REG_TEMP_OFFSET, 10.0f },
      { "humidity offset",    NPK_REG_HUM_OFFSET,  10.0f },
      { "conductivity offset",NPK_REG_EC_OFFSET,    1.0f },
      { "pH offset",          NPK_REG_PH_OFFSET,    1.0f },
    };
    for (uint8_t i = 0; i < 4; ++i) {
      uint16_t v = 0;
      if (sensor_->readRegisters(offs[i].reg, 1, &v)) {
        out.printf("  0x%04X  %-20s raw %6d  -> %.2f\r\n", offs[i].reg, offs[i].name,
                   (int)(int16_t)v, (int)(int16_t)v / offs[i].scale);
      } else {
        out.printf("  0x%04X  %-20s no reply (%s)\r\n", offs[i].reg, offs[i].name,
                   sensor_->lastError());
      }
      delay(20);
    }
    for (uint8_t i = 0; i < 3; ++i) {
      float f = 0.0f;
      uint16_t o = 0;
      const bool fok = sensor_->readFloat(kNutrients[i].factorHigh, f);
      delay(20);
      const bool ook = sensor_->readRegisters(kNutrients[i].factorHigh + 2, 1, &o);
      out.printf("  0x%04X  %s factor %s", kNutrients[i].factorHigh,
                 kNutrients[i].key, fok ? "" : "no reply");
      if (fok) out.printf("%.5f", f);
      out.printf("   offset %s", ook ? "" : "no reply");
      if (ook) out.printf("%d", (int)(int16_t)o);
      out.println();
      delay(20);
    }
    out.println();
    out.println(F("The manual documents factory defaults only for 0x0022-0x0024."));
    out.println(F("For the offsets and the N/P/K factors it states none, so what"));
    out.println(F("they read here is whatever the unit shipped with - most likely"));
    out.println(F("0 offsets and unit gains, but that is not promised anywhere."));
    out.println();
    out.println(F("  sensor cal <n|p|k> low  <ref>          two-point solve against"));
    out.println(F("  sensor cal <n|p|k> high <ref>          the probe's own A and B"));
    out.println(F("  sensor offset <temp|hum|ec|ph> <raw>   write an offset register"));
    out.println(F("  sensor factor <n|p|k> <value>          write the gain float"));
    out.println(F("  sensor npk    <n|p|k> <mg/kg>          write a measured value"));
    out.println();
    return;
  }

  if (!strcasecmp(sub, "offset")) {
    if (argc < 4) {
      out.println("usage: sensor offset <temp|hum|ec|ph> <raw integer>");
      return;
    }
    uint16_t reg;
    if      (!strcasecmp(argv[2], "temp")) reg = NPK_REG_TEMP_OFFSET;
    else if (!strcasecmp(argv[2], "hum"))  reg = NPK_REG_HUM_OFFSET;
    else if (!strcasecmp(argv[2], "ec"))   reg = NPK_REG_EC_OFFSET;
    else if (!strcasecmp(argv[2], "ph"))   reg = NPK_REG_PH_OFFSET;
    else { out.println("error: channel must be temp, hum, ec or ph"); return; }

    const int v = (int)strtol(argv[3], nullptr, 0);
    if (v < -32768 || v > 32767) { out.println("error: value out of range"); return; }
    if (sensor_->writeRegister(reg, (uint16_t)(int16_t)v)) {
      out.printf("wrote %d to 0x%04X\r\n", v, reg);
    } else {
      out.printf("error: write failed (%s)\r\n", sensor_->lastError());
    }
    return;
  }

  if (!strcasecmp(sub, "factor")) {
    if (argc < 4) { out.println("usage: sensor factor <n|p|k> <value>"); return; }
    const NpkNutrientReg* nr = npkNutrientFromKey(argv[2]);
    if (!nr) { out.println("error: channel must be n, p or k"); return; }
    const float f = strtof(argv[3], nullptr);
    if (!isfinite(f)) { out.println("error: value must be finite"); return; }
    if (sensor_->writeFloat(nr->factorHigh, f)) {
      out.printf("wrote factor %.5f to 0x%04X/0x%04X\r\n", f,
                 nr->factorHigh, nr->factorHigh + 1);
    } else {
      out.printf("error: write failed (%s)\r\n", sensor_->lastError());
    }
    return;
  }

  if (!strcasecmp(sub, "npk")) {
    if (argc < 4) { out.println("usage: sensor npk <n|p|k> <mg/kg>"); return; }
    const NpkNutrientReg* nr = npkNutrientFromKey(argv[2]);
    if (!nr) { out.println("error: channel must be n, p or k"); return; }
    const long v = strtol(argv[3], nullptr, 10);
    if (v < 0 || v > 2999) { out.println("error: range is 0-2999 mg/kg"); return; }
    if (sensor_->writeRegister(nr->measurement, (uint16_t)v)) {
      out.printf("wrote %ld mg/kg to 0x%04X\r\n", v, nr->measurement);
      out.println("The probe now reports that value until it measures again.");
    } else {
      out.printf("error: write failed (%s)\r\n", sensor_->lastError());
    }
    return;
  }

  // -------------------------------------------------------------------------
  // Guided two-point recalculation of the probe's own A and B
  // -------------------------------------------------------------------------
  // The probe already holds a gain and an offset per nutrient. Rather than
  // overwrite them blindly, this reads the existing pair, measures against two
  // standards, and composes a correction on top.
  //
  // Assuming the probe reports  y = A*x + B  over some internal x, and two
  // standards give reported y1, y2 for true values r1, r2:
  //
  //     g  = (r2 - r1) / (y2 - y1)          the gain error, on the output
  //     A' = A * g
  //     B' = r1 - g * (y1 - B)
  //
  // x never appears, so the internal scaling does not need to be known. The
  // one thing assumed is that the probe combines them linearly in that order,
  // which the manual implies by calling them factor and offset but does not
  // state outright - so the write is followed by a verification read.
  if (!strcasecmp(sub, "cal")) {
    if (argc < 5) {
      out.println("usage: sensor cal <n|p|k> low  <reference>");
      out.println("       sensor cal <n|p|k> high <reference>");
      return;
    }
    const NpkNutrientReg* nr = npkNutrientFromKey(argv[2]);
    if (!nr) { out.println("error: channel must be n, p or k"); return; }
    const uint8_t slot = (uint8_t)(nr - kNutrients);
    const float ref = strtof(argv[4], nullptr);
    if (!isfinite(ref)) { out.println("error: reference must be a number"); return; }

    float reported;
    if (!captureRaw(nr->channel, reported, out)) return;

    if (!strcasecmp(argv[3], "low")) {
      g_sensorLow[slot] = { true, ref, reported };
      out.printf("%s: low point held (probe reports %.1f, standard is %.1f)\r\n",
                 nr->key, reported, ref);
      out.printf("Move to the high standard, then: sensor cal %s high <ref>\r\n", nr->key);
      return;
    }

    if (strcasecmp(argv[3], "high") != 0) {
      out.println("error: second argument must be low or high");
      return;
    }
    if (!g_sensorLow[slot].held) {
      out.printf("error: capture the low point first (sensor cal %s low <ref>)\r\n", nr->key);
      return;
    }

    const float r1 = g_sensorLow[slot].reference, y1 = g_sensorLow[slot].reported;
    const float r2 = ref,                          y2 = reported;

    if (fabsf(y2 - y1) < 1e-3f) {
      out.println("error: the probe reported the same value at both standards");
      out.println("       - it is not responding to the difference, so no gain");
      out.println("       can be solved. Check the standards and let it settle.");
      return;
    }

    float a = 0.0f, b = 0.0f;
    const char* why = nullptr;
    if (!npkReadAB(sensor_, nr, a, b, &why)) {
      out.printf("error: could not read the current coefficients (%s)\r\n", why);
      return;
    }
    if (!isfinite(a) || a == 0.0f) {
      out.printf("error: current gain reads %.5f, which cannot be composed on.\r\n", a);
      out.printf("       Set a sane starting point first: sensor factor %s 1.0\r\n", nr->key);
      return;
    }

    const float g  = (r2 - r1) / (y2 - y1);
    const float a2 = a * g;
    const float b2 = r1 - g * (y1 - b);

    if (!isfinite(a2) || !isfinite(b2) || a2 == 0.0f) {
      out.println("error: the solve produced an unusable pair");
      return;
    }
    if (fabsf(a2) > 1e3f || fabsf(b2) > 1e5f) {
      out.printf("error: solved A=%.5f B=%.1f, which is implausible - check that\r\n", a2, b2);
      out.println("       the two standards were not swapped");
      return;
    }

    out.printf("%s: current A=%.5f B=%.1f\r\n", nr->key, a, b);
    out.printf("%s: solved  A=%.5f B=%.1f  (from %.1f/%.1f and %.1f/%.1f)\r\n",
               nr->key, a2, b2, y1, r1, y2, r2);

    // A negative gain means the probe read *lower* at the higher standard.
    // For a nutrient concentration that is almost always the two standards
    // measured in the wrong order, and the verification below will NOT catch
    // it: the fit is self-consistent against whatever labels it was given, so
    // it reads back perfectly while being exactly backwards.
    if (a2 < 0.0f) {
      out.println("WARNING: the solved gain is negative, so the probe read lower");
      out.println("         at the higher standard. Almost certainly the two");
      out.println("         standards were measured the wrong way round. The");
      out.println("         verification below cannot detect that - it will look");
      out.println("         correct either way. Re-run if in any doubt.");
    }
    // The offset register is a single integer, so B is quantised to whole
    // units - up to half a mg/kg of error that no amount of care removes.
    if (fabsf(b2 - lroundf(b2)) > 0.01f) {
      out.printf("note: offset %.2f will be stored as %ld - the register is an\r\n",
                 b2, lroundf(b2));
      out.println("      integer, so the fraction is lost.");
    }

    if (!sensor_->writeFloat(nr->factorHigh, a2)) {
      out.printf("error: writing the gain failed (%s)\r\n", sensor_->lastError());
      return;
    }
    delay(NPK_INTERFRAME_MS * 2);
    if (!sensor_->writeRegister(nr->factorHigh + 2, (uint16_t)(int16_t)lroundf(b2))) {
      out.printf("error: writing the offset failed (%s) - the gain was already\r\n",
                 sensor_->lastError());
      out.println("       written, so the probe is now half-updated. Re-run this.");
      return;
    }
    g_sensorLow[slot].held = false;
    out.println("written to the probe.");

    // Read it back and measure. If the assumed model is wrong, this is where
    // it shows, rather than silently producing bad data for months.
    delay(300);
    float back = 0.0f, boff = 0.0f;
    if (npkReadAB(sensor_, nr, back, boff, &why)) {
      out.printf("verify: probe now holds A=%.5f B=%.1f\r\n", back, boff);
    }
    float after;
    if (captureRaw(nr->channel, after, out)) {
      const float err = after - r2;
      out.printf("verify: reads %.1f against a standard of %.1f  (error %+.1f)\r\n",
                 after, r2, err);
      if (fabsf(err) > fabsf(r2) * 0.1f + 1.0f) {
        out.println("That is further off than it should be. The probe may not");
        out.println("combine factor and offset the way this assumes - fall back");
        out.println("to correcting in the firmware with \"cal\" instead.");
      }
    }
    return;
  }

  out.printf("unknown sensor subcommand \"%s\" - try: sensor\r\n", sub);
}

void NpkConsole::cmdCal(char** argv, int argc, Print& out) {
  if (argc < 2 || !strcasecmp(argv[1], "list")) {
    listCalibration(out);
    return;
  }

  const char* sub = argv[1];

  // The calibration lives in ESP32 NVS, so this is what needs backing up.
  // Emitting it as command lines rather than a report means restoring is
  // replaying the output - no parser, no format to keep in step.
  if (!strcasecmp(sub, "export")) {
    out.println();
    out.println(F("# SoilNode calibration - paste back to restore"));
    for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
      NpkCoeff k = cal_->get(c);
      out.printf("cal set %s %.5f %.5f\r\n", NPK_CHANNELS[c].key, k.a, k.b);
    }
    out.println();
    return;
  }

  // Machine-readable form of the same table. Bounded: seven channels at about
  // 55 bytes each stays well inside one MQTT message, so it never splits and
  // arrives parseable in one piece.
  if (!strcasecmp(sub, "json")) {
    out.print('{');
    for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
      NpkCoeff k = cal_->get(c);
      const char* state = cal_->isDefault(c) ? "default" : "calibrated";
      if (cal_->hasPendingLow(c)) state = "pending_high";
      out.printf("%s\"%s\":{\"a\":%.5f,\"b\":%.5f,\"state\":\"%s\"}",
                 c ? "," : "", NPK_CHANNELS[c].key, k.a, k.b, state);
    }
    out.println('}');
    return;
  }

  if (!strcasecmp(sub, "clear") || !strcasecmp(sub, "reset")) {
    if (argc < 3) { out.println("usage: cal clear <channel|all>"); return; }
    if (!strcasecmp(argv[2], "all")) {
      cal_->resetAll();
      out.println("all channels reset to A=1, B=0");
    } else {
      int ch = resolveChannel(argv[2], out);
      if (ch < 0) return;
      cal_->resetChannel(ch);
      out.printf("%s reset to A=1, B=0\r\n", NPK_CHANNELS[ch].key);
    }
    return;
  }

  if (!strcasecmp(sub, "set")) {
    if (argc < 5) { out.println("usage: cal set <channel> <A> <B>"); return; }
    int ch = resolveChannel(argv[2], out);
    if (ch < 0) return;
    const float a = strtof(argv[3], nullptr);
    const float b = strtof(argv[4], nullptr);
    const char* why = nullptr;
    if (!cal_->setChecked(ch, a, b, &why)) {
      out.printf("error: %s\r\n", why);
      return;
    }
    out.printf("%s: A=%.5f B=%.5f saved\r\n", NPK_CHANNELS[ch].key, a, b);
    return;
  }

  if (!strcasecmp(sub, "1p") || !strcasecmp(sub, "offset")) {
    if (argc < 4) { out.println("usage: cal 1p <channel> <reference>"); return; }
    int ch = resolveChannel(argv[2], out);
    if (ch < 0) return;
    const float ref = strtof(argv[3], nullptr);
    float raw;
    if (!captureRaw(ch, raw, out)) return;
    const char* why = nullptr;
    if (!cal_->onePoint(ch, raw, ref, &why)) { out.printf("error: %s\r\n", why); return; }
    NpkCoeff k = cal_->get(ch);
    out.printf("%s: offset trimmed to reference %.*f -> A=%.5f B=%.5f saved\r\n",
               NPK_CHANNELS[ch].key, NPK_CHANNELS[ch].decimals, ref, k.a, k.b);
    return;
  }

  if (!strcasecmp(sub, "low")) {
    if (argc < 4) { out.println("usage: cal low <channel> <reference>"); return; }
    int ch = resolveChannel(argv[2], out);
    if (ch < 0) return;
    const float ref = strtof(argv[3], nullptr);
    float raw;
    if (!captureRaw(ch, raw, out)) return;
    cal_->captureLow(ch, raw, ref);
    out.printf("%s: low point held (raw %.*f -> ref %.*f).\r\n",
               NPK_CHANNELS[ch].key, NPK_CHANNELS[ch].decimals, raw,
               NPK_CHANNELS[ch].decimals, ref);
    out.printf("Now move the probe to the high reference and run: cal high %s <ref>\r\n",
               NPK_CHANNELS[ch].key);
    return;
  }

  if (!strcasecmp(sub, "high")) {
    if (argc < 4) { out.println("usage: cal high <channel> <reference>"); return; }
    int ch = resolveChannel(argv[2], out);
    if (ch < 0) return;
    if (!cal_->hasPendingLow(ch)) {
      out.printf("error: capture the low point first (cal low %s <ref>)\r\n",
                 NPK_CHANNELS[ch].key);
      return;
    }
    const float ref = strtof(argv[3], nullptr);
    float raw;
    if (!captureRaw(ch, raw, out)) return;

    const char* err = nullptr;
    if (!cal_->solveHigh(ch, raw, ref, &err)) {
      out.printf("error: %s\r\n", err);
      return;
    }
    NpkCoeff k = cal_->get(ch);
    out.printf("%s: two-point solve -> A=%.5f B=%.5f saved\r\n",
               NPK_CHANNELS[ch].key, k.a, k.b);

    // A negative gain means the probe read higher where the true value is
    // lower, which for a soil nutrient is almost always the two references
    // entered against the wrong samples. Nothing downstream can detect it:
    // the fit passes through both points exactly whichever way round they go.
    if (k.a < 0.0f) {
      out.println("WARNING: negative gain - the probe read HIGHER where the");
      out.println("         reference is LOWER. Almost certainly the two");
      out.println("         samples were entered the wrong way round. This");
      out.println("         fits both points perfectly either way, so nothing");
      out.println("         downstream will catch it. Re-check before trusting.");
    }
    // B is what the channel reports when the probe reads zero. Negative means
    // a bottomed-out reading becomes a negative concentration, which the range
    // check then drops from the payload entirely.
    if (k.b < 0.0f) {
      out.printf("note: B is negative, so a raw reading below %.1f gives a\r\n",
                 -k.b / k.a);
      out.println("      negative result, which is dropped from NPKdata rather");
      out.println("      than published. Expect gaps if this channel bottoms out.");
    }
    return;
  }

  out.printf("unknown calibration subcommand \"%s\" - type help\r\n", sub);
}

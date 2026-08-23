#include "NpkConsole.h"
#include "NpkConfig.h"
#include "NpkJson.h"

static const int    kMaxArgs     = 8;
static const size_t kReplyCap    = NPK_MQTT_BUFFER - 64;

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

  char buf[kReplyCap];
  NpkBufferPrint reply(buf, sizeof(buf));
  execute(line, reply);

  Serial.printf("[cmd] via mqtt: %s\r\n", line);
  Serial.print(reply.c_str());
  if (reply.length() > 0) net_->publish(NPK_TOPIC_REPLY, reply.c_str());
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
    snprintf(out, cap, "%s", cmd);   // help, status, read, reboot
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
  out.println(F("                            long scans are truncated over MQTT;"));
  out.println(F("                            run those on the serial console"));
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
  out.println();
  out.println(F("The probe has its own calibration registers, separate from"));
  out.println(F("the above. Those change what it reports; \"cal\" changes how"));
  out.println(F("this firmware interprets what it reports."));
  out.println();
  out.println(F("  sensor                    read the probe's own registers"));
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
  uint16_t first = 0x0000;
  uint16_t last  = 0x0030;
  if (argc >= 2) first = (uint16_t)strtol(argv[1], nullptr, 0);
  if (argc >= 3) last  = (uint16_t)strtol(argv[2], nullptr, 0);
  if (last < first) { out.println("error: last register is below first"); return; }
  if (last - first > 512) { out.println("error: range limited to 512 registers"); return; }
  sensor_->scanRegisters(first, last, out);
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
};
static const NpkNutrientReg kNutrients[] = {
  { "n", NPK_REG_NITROGEN,   NPK_REG_N_FACTOR },
  { "p", NPK_REG_PHOSPHORUS, NPK_REG_P_FACTOR },
  { "k", NPK_REG_POTASSIUM,  NPK_REG_K_FACTOR },
};

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

  out.printf("unknown sensor subcommand \"%s\" - try: sensor\r\n", sub);
}

void NpkConsole::cmdCal(char** argv, int argc, Print& out) {
  if (argc < 2 || !strcasecmp(argv[1], "list")) {
    listCalibration(out);
    return;
  }

  const char* sub = argv[1];

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
      out.printf("error: %s
", why);
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
    if (!cal_->onePoint(ch, raw, ref, &why)) { out.printf("error: %s
", why); return; }
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
    return;
  }

  out.printf("unknown calibration subcommand \"%s\" - type help\r\n", sub);
}

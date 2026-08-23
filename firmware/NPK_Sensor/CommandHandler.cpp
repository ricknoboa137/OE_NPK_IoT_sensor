#include "CommandHandler.h"
#include "Config.h"
#include "JsonCompat.h"

static const int   kMaxArgs = 8;
static const size_t kMqttReplyCap = MQTT_BUFFER_SIZE - 64;

void CommandHandler::begin(SoilSensor* sensor, Calibration* cal, NetLink* net) {
  sensor_ = sensor;
  cal_ = cal;
  net_ = net;
  serialLen_ = 0;
  serialBuf_[0] = '\0';
}

// ---------------------------------------------------------------------------
// Transports
// ---------------------------------------------------------------------------

void CommandHandler::pollSerial() {
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

void CommandHandler::handleMqtt(const uint8_t* payload, unsigned int length) {
  char line[160];

  if (length > 0 && payload[0] == '{') {
    if (!jsonToLine(payload, length, line, sizeof(line))) {
      net_->publish(TOPIC_REPLY, "error: could not parse JSON command");
      return;
    }
  } else {
    unsigned int n = min(length, (unsigned int)(sizeof(line) - 1));
    memcpy(line, payload, n);
    line[n] = '\0';
  }

  char buf[kMqttReplyCap];
  BufferedPrint reply(buf, sizeof(buf));
  execute(line, reply);

  Serial.printf("[cmd] via mqtt: %s\r\n", line);
  Serial.print(reply.c_str());
  if (reply.length() > 0) net_->publish(TOPIC_REPLY, reply.c_str());
}

// Normalise a JSON command object into the text form.
bool CommandHandler::jsonToLine(const uint8_t* payload, unsigned int length,
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

void CommandHandler::execute(const char* line, Print& out) {
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

void CommandHandler::dispatch(char** argv, int argc, Print& out) {
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
  } else if (!strcasecmp(cmd, "mqtt")) {
    if (argc < 2) { out.println("usage: mqtt <host> [port]"); return; }
    uint16_t port = (argc >= 3) ? (uint16_t)strtol(argv[2], nullptr, 10) : net_->port();
    if (net_->setBroker(argv[1], port)) out.printf("broker set to %s:%u\r\n", argv[1], port);
    else out.println("error: invalid broker");
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

void CommandHandler::cmdHelp(Print& out) {
  out.println();
  out.println(F("Commands ------------------------------------------------------"));
  out.println(F("  read                      take a reading and show raw + calibrated"));
  out.println(F("  status                    firmware, link and sensor state"));
  out.println(F("  scan [first] [last]       probe Modbus registers (hex or decimal)"));
  out.println(F("                            long scans are truncated over MQTT;"));
  out.println(F("                            run those on the serial console"));
  out.println(F("  mqtt <host> [port]        change broker, stored in NVS"));
  out.println(F("  wifi portal | wifi reset  reopen the captive portal / forget WiFi"));
  out.println(F("  reboot"));
  out.println();
  out.println(F("Calibration ---------------------------------------------------"));
  out.println(F("  Reported value = A * raw + B, per channel, stored in NVS."));
  out.println();
  out.println(F("  cal                       list A and B for every channel"));
  out.println(F("  cal set  <ch> <A> <B>     write both coefficients directly"));
  out.println(F("  cal 1p   <ch> <ref>       offset trim: keep A, solve B"));
  out.println(F("  cal low  <ch> <ref>       two-point step 1: capture low reference"));
  out.println(F("  cal high <ch> <ref>       two-point step 2: solve A and B"));
  out.println(F("  cal clear <ch|all>        back to A=1, B=0"));
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
  out.println(F("  Each capture averages several sweeps, so give the probe time"));
  out.println(F("  to settle before typing the command."));
  out.println();
}

void CommandHandler::cmdStatus(Print& out) {
  out.println();
  out.printf("Firmware : %s %s\r\n", FW_NAME, FW_VERSION);
  out.printf("Profile  : %s\r\n",
             SENSOR_REGISTER_PROFILE == PROFILE_DATASHEET
               ? "datasheet (JXBS-3001-TR section 4.3)" : "legacy contiguous 0x0000");
  out.printf("RS-485   : %lu baud 8N1, slave 0x%02X, DE/RE on GPIO%d\r\n",
             (unsigned long)sensor_->baud(), SENSOR_SLAVE_ID, RS485_DE_RE_PIN);
  out.printf("Last err : %s\r\n",
             *sensor_->lastError() ? sensor_->lastError() : "none");
  out.printf("Uptime   : %lu s   free heap %u B\r\n",
             (unsigned long)(millis() / 1000), (unsigned)ESP.getFreeHeap());
  net_->printStatus(out);
  listCalibration(out);
}

void CommandHandler::cmdRead(Print& out) {
  Reading r;
  sensor_->read(r);

  out.println();
  out.printf("%-14s %8s  %10s  %10s   %s\r\n",
             "channel", "raw", "scaled", "calibrated", "unit");
  for (uint8_t c = 0; c < CH_COUNT; ++c) {
    if (!r.valid[c]) {
      out.printf("%-14s %8s  %10s  %10s   %s\r\n",
                 CHANNELS[c].key, "-", "-", "no reply", CHANNELS[c].unit);
      continue;
    }
    const int d = CHANNELS[c].decimals;
    out.printf("%-14s %8u  %10.*f  %10.*f   %s\r\n",
               CHANNELS[c].key, (unsigned)r.raw[c],
               d, r.scaled[c],
               d, cal_->apply(c, r.scaled[c]),
               CHANNELS[c].unit);
  }
  if (!r.complete) {
    out.printf("%u transaction(s) failed: %s\r\n", r.failedOps, sensor_->lastError());
  }
  out.println();
}

void CommandHandler::cmdScan(char** argv, int argc, Print& out) {
  uint16_t first = 0x0000;
  uint16_t last  = 0x0030;
  if (argc >= 2) first = (uint16_t)strtol(argv[1], nullptr, 0);
  if (argc >= 3) last  = (uint16_t)strtol(argv[2], nullptr, 0);
  if (last < first) { out.println("error: last register is below first"); return; }
  if (last - first > 512) { out.println("error: range limited to 512 registers"); return; }
  sensor_->scanRegisters(first, last, out);
}

int CommandHandler::resolveChannel(const char* name, Print& out) {
  int ch = channelFromKey(name);
  if (ch < 0) {
    out.printf("error: unknown channel \"%s\". Try:", name ? name : "");
    for (uint8_t i = 0; i < CH_COUNT; ++i) out.printf(" %s", CHANNELS[i].key);
    out.println();
  }
  return ch;
}

// Average several sweeps so a single noisy frame cannot skew the coefficients.
bool CommandHandler::captureRaw(uint8_t ch, float& rawOut, Print& out) {
  out.printf("sampling %s (%u sweeps) ...\r\n", CHANNELS[ch].key, CAL_SAMPLE_COUNT);
  Reading r;
  sensor_->readAveraged(r, CAL_SAMPLE_COUNT);
  if (!r.valid[ch]) {
    out.printf("error: no valid reading for %s (%s)\r\n",
               CHANNELS[ch].key, sensor_->lastError());
    return false;
  }
  rawOut = r.scaled[ch];
  out.printf("  raw average = %.*f %s\r\n", CHANNELS[ch].decimals, rawOut,
             CHANNELS[ch].unit);
  return true;
}

void CommandHandler::listCalibration(Print& out) {
  out.println();
  out.printf("%-14s %12s %12s   %s\r\n", "channel", "A (gain)", "B (offset)", "state");
  for (uint8_t c = 0; c < CH_COUNT; ++c) {
    Coefficients k = cal_->get(c);
    const char* state = cal_->isDefault(c) ? "default" : "calibrated";
    if (cal_->hasPendingLow(c)) state = "low point captured";
    out.printf("%-14s %12.5f %12.5f   %s\r\n", CHANNELS[c].key, k.a, k.b, state);
  }
  out.println();
}

void CommandHandler::cmdCal(char** argv, int argc, Print& out) {
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
      out.printf("%s reset to A=1, B=0\r\n", CHANNELS[ch].key);
    }
    return;
  }

  if (!strcasecmp(sub, "set")) {
    if (argc < 5) { out.println("usage: cal set <channel> <A> <B>"); return; }
    int ch = resolveChannel(argv[2], out);
    if (ch < 0) return;
    const float a = strtof(argv[3], nullptr);
    const float b = strtof(argv[4], nullptr);
    if (!cal_->set(ch, a, b)) {
      out.println("error: A must be non-zero and both values finite");
      return;
    }
    out.printf("%s: A=%.5f B=%.5f saved\r\n", CHANNELS[ch].key, a, b);
    return;
  }

  if (!strcasecmp(sub, "1p") || !strcasecmp(sub, "offset")) {
    if (argc < 4) { out.println("usage: cal 1p <channel> <reference>"); return; }
    int ch = resolveChannel(argv[2], out);
    if (ch < 0) return;
    const float ref = strtof(argv[3], nullptr);
    float raw;
    if (!captureRaw(ch, raw, out)) return;
    if (!cal_->onePoint(ch, raw, ref)) { out.println("error: could not solve"); return; }
    Coefficients k = cal_->get(ch);
    out.printf("%s: offset trimmed to reference %.*f -> A=%.5f B=%.5f saved\r\n",
               CHANNELS[ch].key, CHANNELS[ch].decimals, ref, k.a, k.b);
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
               CHANNELS[ch].key, CHANNELS[ch].decimals, raw,
               CHANNELS[ch].decimals, ref);
    out.printf("Now move the probe to the high reference and run: cal high %s <ref>\r\n",
               CHANNELS[ch].key);
    return;
  }

  if (!strcasecmp(sub, "high")) {
    if (argc < 4) { out.println("usage: cal high <channel> <reference>"); return; }
    int ch = resolveChannel(argv[2], out);
    if (ch < 0) return;
    if (!cal_->hasPendingLow(ch)) {
      out.printf("error: capture the low point first (cal low %s <ref>)\r\n",
                 CHANNELS[ch].key);
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
    Coefficients k = cal_->get(ch);
    out.printf("%s: two-point solve -> A=%.5f B=%.5f saved\r\n",
               CHANNELS[ch].key, k.a, k.b);
    return;
  }

  out.printf("unknown calibration subcommand \"%s\" - type help\r\n", sub);
}

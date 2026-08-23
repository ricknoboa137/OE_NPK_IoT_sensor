/*
 * SoilNode - ESP32 node for the JXBS-3001-TR soil 7-in-1 probe.
 *
 *   RS-485 Modbus RTU  ->  linear per-channel calibration  ->  MQTT JSON
 *
 * Layout:
 *   NpkConfig.h    every tunable in one place
 *   NpkSensor.*    the seven channels, and the Modbus RTU master
 *   NpkCal.*       A and B per channel, held in NVS
 *   NpkNet.*       WiFiManager provisioning and the MQTT link
 *   NpkConsole.*   console shared by the serial port and MQTT
 *   NpkJson.h      ArduinoJson 6/7 compatibility
 *
 * Libraries, the same set the original sketch used:
 *   SoftwareSerial, ArduinoJson, WiFiManager (tzapu), WiFi, PubSubClient.
 *   Preferences ships with the ESP32 core and holds the calibration.
 *
 * Wiring (manual section 2.1): brown = 12-24 V +, black = 0 V,
 * yellow or grey = 485-A, blue = 485-B. The probe needs 12 V; it will not
 * answer reliably on the ESP32 3V3 rail.
 *
 * Type "help" on the serial console at 115200 baud.
 */

#include "NpkConfig.h"
#include "NpkSensor.h"
#include "NpkCal.h"
#include "NpkNet.h"
#include "NpkConsole.h"
#include "NpkJson.h"

NpkSensor  sensor;
NpkCal     calibration;
NpkNet     net;
NpkConsole console;

// Last successfully read value per channel, so a single dropped frame does
// not punch a hole in the published payload.
static float lastGood[NPK_CHANNEL_COUNT];
static bool  haveGood[NPK_CHANNEL_COUNT];

static uint32_t nextSample = 0;

static void npkOnMqttMessage(char* topic, uint8_t* payload, unsigned int length) {
  (void)topic;
  console.handleMqtt(payload, length);
}

static void publishReading(const NpkReading& r) {
  uint8_t validCount = 0;
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    if (r.valid[c]) {
      lastGood[c] = calibration.apply(c, r.scaled[c]);
      haveGood[c] = true;
      validCount++;
    }
  }

  // Nothing came back at all: say so on the status topic rather than
  // publishing zeros, which the original sketch did and which is
  // indistinguishable from genuinely dry, cold, nutrient-free soil.
  if (validCount == 0) {
    Serial.printf("[read] no channels valid (%s)\r\n", sensor.lastError());
    net.publish(NPK_TOPIC_STATUS, "sensor-unreachable", true);
    return;
  }

  NPK_JSON_DOC(doc, 512);
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    if (haveGood[c]) {
      doc[NPK_CHANNELS[c].jsonKey] = roundf(lastGood[c] * 1000.0f) / 1000.0f;
    }
  }
  doc["ok"] = r.complete;

  char payload[NPK_MQTT_BUFFER];
  serializeJson(doc, payload, sizeof(payload));

  Serial.println(payload);
  if (!net.publish(NPK_TOPIC_DATA, payload)) {
    Serial.println("[mqtt] publish skipped, link down");
  } else if (r.complete) {
    net.publish(NPK_TOPIC_STATUS, "online", true);
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(NPK_LED_PIN, OUTPUT);
  digitalWrite(NPK_LED_PIN, LOW);

  Serial.printf("\r\n%s %s\r\n", NPK_FW_NAME, NPK_FW_VERSION);
  Serial.println("JXBS-3001-TR soil 7-in-1, Modbus RTU over RS-485");

  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    lastGood[c] = 0.0f;
    haveGood[c] = false;
  }

  calibration.begin();
  sensor.begin();

#if NPK_BAUD_AUTODETECT
  Serial.print("[sensor] probing baud rate ... ");
  if (sensor.detectBaud()) {
    Serial.printf("responding at %lu\r\n", (unsigned long)sensor.baud());
  } else {
    Serial.printf("no reply, staying at %lu\r\n", (unsigned long)sensor.baud());
    Serial.println("[sensor] check 12 V supply, A/B polarity and slave address,");
    Serial.println("         then try the \"scan\" command.");
  }
#endif

  // WiFiManager only raises the AP when the stored credentials fail, so a node
  // that is already on WiFi would otherwise offer no way in. Hold the BOOT
  // button now to force the portal open.
  pinMode(NPK_PORTAL_BTN_PIN, INPUT_PULLUP);
  Serial.printf("[net] hold the BOOT button within %u s to open the config portal\r\n",
                (unsigned)(NPK_PORTAL_BTN_WINDOW_MS / 1000));
  bool forcePortal = false;
  const uint32_t windowEnd = millis() + NPK_PORTAL_BTN_WINDOW_MS;
  uint32_t heldSince = 0;
  while ((int32_t)(millis() - windowEnd) < 0) {
    if (digitalRead(NPK_PORTAL_BTN_PIN) == LOW) {
      if (heldSince == 0) heldSince = millis();
      if (millis() - heldSince >= NPK_PORTAL_BTN_HOLD_MS) { forcePortal = true; break; }
    } else {
      heldSince = 0;
    }
    delay(20);
  }
  if (forcePortal) Serial.println("[net] BOOT held - portal will open");

  // Console first: net.begin() subscribes to the command topic, and the
  // callback it installs dereferences the pointers the console holds.
  console.begin(&sensor, &calibration, &net);
  net.begin(npkOnMqttMessage, forcePortal);

  Serial.println("Console ready - type \"help\" for commands.");
  nextSample = millis();
}

void loop() {
  net.loop();
  console.pollSerial();

  digitalWrite(NPK_LED_PIN, net.connected() ? HIGH : LOW);

  const uint32_t now = millis();
  if ((int32_t)(now - nextSample) >= 0) {
    nextSample = now + NPK_SAMPLE_INTERVAL_MS;

    NpkReading r;
    sensor.read(r);
    publishReading(r);
  }
}

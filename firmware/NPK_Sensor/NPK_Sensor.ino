/*
 * NPK_Sensor - ESP32 node for the JXBS-3001-TR soil 7-in-1 probe.
 *
 *   RS-485 Modbus RTU  ->  linear per-channel calibration  ->  MQTT JSON
 *
 * Layout:
 *   Config.h          every tunable in one place
 *   Channels.h/.cpp   the seven measured quantities and their scale factors
 *   SoilSensor.*      Modbus RTU master, CRC, register map, retries
 *   Calibration.*     A and B per channel, held in NVS
 *   NetworkManager.*  WiFiManager provisioning and the MQTT link
 *   CommandHandler.*  console shared by the serial port and MQTT
 *
 * Wiring (manual section 2.1): brown = 12-24 V +, black = 0 V,
 * yellow or grey = 485-A, blue = 485-B. The probe needs 12 V; it will not
 * answer reliably on the ESP32 3V3 rail.
 *
 * Type "help" on the serial console at 115200 baud.
 */

#include "Config.h"
#include "Channels.h"
#include "SoilSensor.h"
#include "Calibration.h"
#include "NetworkManager.h"
#include "CommandHandler.h"
#include "JsonCompat.h"

SoilSensor     sensor;
Calibration    calibration;
NetworkManager net;
CommandHandler console;

// Last successfully read value per channel, so a single dropped frame does
// not punch a hole in the published payload.
static float lastGood[CH_COUNT];
static bool  haveGood[CH_COUNT];

static uint32_t nextSample = 0;

static void onMqttMessage(char* topic, uint8_t* payload, unsigned int length) {
  (void)topic;
  console.handleMqtt(payload, length);
}

static void publishReading(const Reading& r) {
  uint8_t validCount = 0;
  for (uint8_t c = 0; c < CH_COUNT; ++c) {
    if (r.valid[c]) {
      lastGood[c] = calibration.apply(c, r.scaled[c]);
      haveGood[c] = true;
      validCount++;
    }
  }

  // Nothing at all came back: say so on the status topic rather than
  // publishing zeros, which the original sketch did and which is
  // indistinguishable from genuinely dry, cold, nutrient-free soil.
  if (validCount == 0) {
    Serial.printf("[read] no channels valid (%s)\r\n", sensor.lastError());
    net.publish(TOPIC_STATUS, "sensor-unreachable", true);
    return;
  }

  NPK_JSON_DOC(doc, 512);
  for (uint8_t c = 0; c < CH_COUNT; ++c) {
    if (haveGood[c]) doc[CHANNELS[c].jsonKey] = roundf(lastGood[c] * 1000.0f) / 1000.0f;
  }
  doc["ok"] = r.complete;

  char payload[MQTT_BUFFER_SIZE];
  serializeJson(doc, payload, sizeof(payload));

  Serial.println(payload);
  if (!net.publish(TOPIC_DATA, payload)) {
    Serial.println("[mqtt] publish skipped, link down");
  } else if (r.complete) {
    net.publish(TOPIC_STATUS, "online", true);
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);

  Serial.printf("\r\n%s %s\r\n", FW_NAME, FW_VERSION);
  Serial.println("JXBS-3001-TR soil 7-in-1, Modbus RTU over RS-485");

  for (uint8_t c = 0; c < CH_COUNT; ++c) { lastGood[c] = 0.0f; haveGood[c] = false; }

  calibration.begin();
  sensor.begin();

#if SENSOR_BAUD_AUTODETECT
  Serial.print("[sensor] probing baud rate ... ");
  if (sensor.detectBaud()) {
    Serial.printf("responding at %lu\r\n", (unsigned long)sensor.baud());
  } else {
    Serial.printf("no reply, staying at %lu\r\n", (unsigned long)sensor.baud());
    Serial.println("[sensor] check 12 V supply, A/B polarity and slave address,");
    Serial.println("         then try the \"scan\" command.");
  }
#endif

  // Console first: net.begin() subscribes to the command topic, and the
  // callback it installs dereferences the pointers the console holds.
  console.begin(&sensor, &calibration, &net);
  net.begin(onMqttMessage);

  Serial.println("Console ready - type \"help\" for commands.");
  nextSample = millis();
}

void loop() {
  net.loop();
  console.pollSerial();

  digitalWrite(STATUS_LED_PIN, net.connected() ? HIGH : LOW);

  const uint32_t now = millis();
  if ((int32_t)(now - nextSample) >= 0) {
    nextSample = now + SAMPLE_INTERVAL_MS;

    Reading r;
    sensor.read(r);
    publishReading(r);
  }
}

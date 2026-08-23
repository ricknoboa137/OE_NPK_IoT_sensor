/*
 * NpkConfig.h - every tunable for the SoilNode firmware, in one place.
 *
 * Naming: every file in this sketch is prefixed Npk and every type is
 * prefixed Npk. arduino-esp32 3.x declares a class called NetworkManager in
 * libraries/Network, which WiFi.h pulls in, and an earlier revision of this
 * firmware collided with it. The prefix makes that class of clash impossible.
 */
#ifndef NPK_CONFIG_H
#define NPK_CONFIG_H

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------
#define NPK_FW_NAME     "SoilNode"
#define NPK_FW_VERSION  "2.1.0"

// ---------------------------------------------------------------------------
// RS-485 wiring (ESP32)
// ---------------------------------------------------------------------------
// Defaults match the original sketch: SoftwareSerial on GPIO18/19 with the
// transceiver DE/RE tied to GPIO4.
//
// Set NPK_USE_SOFTWARE_SERIAL to 0 to use hardware UART1 on the same pins
// instead. That is more robust under WiFi load, since a bit-banged port can
// drop bytes when the radio takes an interrupt, but SoftwareSerial is what the
// original used and it works.
#define NPK_USE_SOFTWARE_SERIAL 1

#define NPK_RS485_RX_PIN   18   // ESP32 RX  <- transceiver RO
#define NPK_RS485_TX_PIN   19   // ESP32 TX  -> transceiver DI
#define NPK_DE_RE_PIN       4   // DE and RE tied together
#define NPK_LED_PIN         2   // on-board LED

// Datasheet section 4.1: 8 data bits, no parity, 1 stop bit.
// Factory default baud is 9600; the original sketch used 4800. The node
// probes the list below at boot and keeps whichever answers.
#define NPK_BAUD_DEFAULT     4800
#define NPK_BAUD_AUTODETECT     1
static const uint32_t NPK_BAUD_CANDIDATES[] = { 4800, 9600, 2400 };

#define NPK_SLAVE_ID            0x01   // datasheet 4.2: factory default 0x01
#define NPK_RESPONSE_TIMEOUT_MS  400
#define NPK_RETRIES                3
#define NPK_INTERFRAME_MS         10   // >= 3.5 char times at 2400 baud

// ---------------------------------------------------------------------------
// Register profile
// ---------------------------------------------------------------------------
// NPK_PROFILE_DATASHEET - the sparse map printed in section 4.3 of the
//                         JXBS-3001-TR manual (pH 0x0006, moisture 0x0012...).
// NPK_PROFILE_LEGACY    - the contiguous seven-register block at 0x0000 that
//                         the original sketch assumed. Some clones really do
//                         answer there. If the datasheet profile times out,
//                         run "scan" and try this.
#define NPK_PROFILE_DATASHEET 0
#define NPK_PROFILE_LEGACY    1
#define NPK_REGISTER_PROFILE  NPK_PROFILE_DATASHEET

// ---------------------------------------------------------------------------
// Timing
// ---------------------------------------------------------------------------
#define NPK_SAMPLE_INTERVAL_MS     5000UL
#define NPK_MQTT_RETRY_MS          5000UL
#define NPK_MQTT_MAX_BACKOFF_MS   60000UL

// ---------------------------------------------------------------------------
// Networking
// ---------------------------------------------------------------------------
#define NPK_AP_NAME             "NPK_Sensor_V2"
#define NPK_AP_TIMEOUT_S        180

#define NPK_MQTT_HOST_DEFAULT   "192.168.0.174"
#define NPK_MQTT_PORT_DEFAULT   "1883"
#define NPK_MQTT_ID_PREFIX      "NPK-"

// NPK_TOPIC_DATA must stay "NPKdata": the Node-RED flow subscribes to it, and
// the JSON key names are fixed in NpkSensor.cpp.
#define NPK_TOPIC_DATA    "NPKdata"
#define NPK_TOPIC_STATUS  "NPKstatus"
#define NPK_TOPIC_CMD     "NPKcommand"
#define NPK_TOPIC_REPLY   "NPKreply"

#define NPK_MQTT_BUFFER 768   // PubSubClient defaults to 256, too small here

// ---------------------------------------------------------------------------
// Calibration
// ---------------------------------------------------------------------------
#define NPK_NVS_NAMESPACE   "npkcfg"
#define NPK_CAL_SAMPLES     8      // sweeps averaged when capturing a point
#define NPK_CAL_MIN_SPAN    0.01f  // reject a two-point solve on a flat span

#endif // NPK_CONFIG_H

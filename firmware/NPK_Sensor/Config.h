/*
 * Config.h - build-time configuration for the JXBS-3001-TR soil 7-in-1 node.
 *
 * Everything a user is likely to change lives here. Nothing in this file
 * depends on the rest of the sketch, so it can be edited without reading it.
 */
#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Firmware identity
// ---------------------------------------------------------------------------
#define FW_NAME     "NPK_Sensor"
#define FW_VERSION  "2.0.0"

// ---------------------------------------------------------------------------
// RS-485 wiring (ESP32)
// ---------------------------------------------------------------------------
// The original sketch drove the transceiver with SoftwareSerial. The ESP32 has
// three hardware UARTs and any GPIO can be routed to one, so UART1 is used
// instead: it is interrupt-driven, does not lose bytes under WiFi load, and
// costs nothing. Set NPK_USE_SOFTWARE_SERIAL to 1 only if UART1 is needed
// elsewhere.
#define NPK_USE_SOFTWARE_SERIAL 0

#define RS485_RX_PIN     18   // ESP32 RX  <- transceiver RO
#define RS485_TX_PIN     19   // ESP32 TX  -> transceiver DI
#define RS485_DE_RE_PIN   4   // DE and RE tied together
#define STATUS_LED_PIN    2   // on-board LED

// Datasheet section 4.1: 8 data bits, no parity, 1 stop bit.
// Factory default baud is 9600. Units shipped for other integrators are
// often set to 4800 or 2400, so the node probes the list below at boot.
#define SENSOR_BAUD_DEFAULT   9600
#define SENSOR_BAUD_AUTODETECT 1
static const uint32_t kSensorBaudCandidates[] = { 9600, 4800, 2400 };

#define SENSOR_SLAVE_ID        0x01   // datasheet 4.2: factory default 0x01
#define MODBUS_RESPONSE_TIMEOUT_MS  400
#define MODBUS_RETRIES              3
#define MODBUS_INTERFRAME_MS        10   // >= 3.5 char times at 2400 baud

// ---------------------------------------------------------------------------
// Register profile
// ---------------------------------------------------------------------------
// PROFILE_DATASHEET  - the sparse map printed in section 4.3 of the
//                      JXBS-3001-TR manual (pH 0x0006, moisture 0x0012, ...).
// PROFILE_LEGACY     - the contiguous seven-register block at 0x0000 that the
//                      original sketch assumed. Several clones of this sensor
//                      really do answer there. If PROFILE_DATASHEET returns
//                      timeouts, run the `scan` command and try this instead.
#define PROFILE_DATASHEET 0
#define PROFILE_LEGACY    1
#define SENSOR_REGISTER_PROFILE PROFILE_DATASHEET

// ---------------------------------------------------------------------------
// Timing
// ---------------------------------------------------------------------------
#define SAMPLE_INTERVAL_MS     5000UL
#define MQTT_RETRY_INTERVAL_MS 5000UL
#define MQTT_MAX_BACKOFF_MS    60000UL

// ---------------------------------------------------------------------------
// Networking
// ---------------------------------------------------------------------------
#define AP_NAME             "NPK_Sensor_V2"
#define AP_CONFIG_TIMEOUT_S 180

#define MQTT_SERVER_DEFAULT "192.168.0.174"
#define MQTT_PORT_DEFAULT   "1883"
#define MQTT_CLIENT_PREFIX  "NPK-"

// Topic names. TOPIC_DATA must stay "NPKdata": the Node-RED flow in this
// repository subscribes to it, and the JSON keys it expects are fixed in
// Calibration.cpp.
#define TOPIC_DATA    "NPKdata"
#define TOPIC_STATUS  "NPKstatus"
#define TOPIC_COMMAND "NPKcommand"
#define TOPIC_REPLY   "NPKreply"

#define MQTT_BUFFER_SIZE 768   // default PubSubClient buffer (256) is too small

// ---------------------------------------------------------------------------
// Calibration
// ---------------------------------------------------------------------------
#define NVS_NAMESPACE       "npkcfg"
#define CAL_SAMPLE_COUNT    8      // readings averaged when capturing a point
#define CAL_MIN_RAW_SPAN    0.01f  // reject two-point cal on a flat span

#endif // CONFIG_H

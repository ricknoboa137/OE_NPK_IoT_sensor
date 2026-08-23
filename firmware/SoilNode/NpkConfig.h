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
// The probe is a VMS-3001-TR-*-N01 (Weimengshi five-pin soil transmitter),
// and its own manual, section 5.3, is the authority:
//
//   0x0000  moisture      read-only,  value x10
//   0x0001  temperature   read-only,  value x10, signed
//   0x0002  conductivity  read-only,  us/cm, NOT scaled
//   0x0003  pH            read-only,  value x10
//   0x0007  salinity      read-only,  "for reference only"
//   0x0008  TDS           read-only,  "for reference only"
//   0x0022  EC temperature coefficient   read/write
//   0x0023  salinity coefficient         read/write
//   0x0024  TDS coefficient              read/write
//   0x0050  temperature calibration      read/write, integer x10
//   0x0051  moisture calibration         read/write, integer x10
//   0x0052  conductivity calibration     read/write, integer
//   0x0053  pH calibration               read/write, integer
//   0x07D0  device address    read/write, 1-254, factory default 1
//   0x07D1  baud rate         read/write, 0 = 2400, 1 = 4800, 2 = 9600
//
// Unlike the JXBS manual this project started from, this one is internally
// consistent: both example CRCs verify, and every worked example decodes to
// the value it claims.
//
// The node keeps sending the original sketch's single request - seven
// registers from 0x0000 - and keeps the original slot order, so existing
// decoders and logged data stay valid. See NpkSensor.cpp for the mapping.
#define NPK_REGISTER_START  0x0000
#define NPK_REGISTER_COUNT  7

// Reject readings outside the physical range in section 1.3 of the datasheet.
// A wrong register profile or scale shows up as 152 %RH or 4090 mg/kg, and
// without this those get published as though they were real.
#define NPK_RANGE_CHECK 1

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

// Broker credentials. Leave both empty for an anonymous broker - PubSubClient
// then sends no CONNECT username at all, which is what most local Mosquitto
// setups with allow_anonymous expect.
#define NPK_MQTT_USER_DEFAULT   ""
#define NPK_MQTT_PASS_DEFAULT   ""

// Hold this pin low during the first NPK_PORTAL_BTN_WINDOW_MS of boot to force
// the configuration portal open even when stored WiFi credentials work. GPIO0
// is the BOOT button on most dev boards; press it just after the board starts,
// not while resetting, because holding GPIO0 low through reset puts the ESP32
// into download mode instead.
#define NPK_PORTAL_BTN_PIN        0
#define NPK_PORTAL_BTN_WINDOW_MS  3000
#define NPK_PORTAL_BTN_HOLD_MS     300

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

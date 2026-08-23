/*
 * NpkConfig.h - every tunable for the SoilNode firmware, in one place.
 *
 * Target hardware: CWT Soil sensor (NPK type), five-pin probe, from
 * Shenzhen ComWinTop. Manual "NPK type (5Pin probe) manual V1.4" is the
 * authority for everything in this file. All nine example frames in that
 * manual have been CRC-checked and verify.
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
#define NPK_FW_VERSION  "2.2.0"

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

// Manual page 3: "Default device address is 1, RS485 Default parameters:
// 4800,n,8,1". The node probes the candidates below at boot in case the
// device has been reconfigured.
#define NPK_BAUD_DEFAULT     4800
#define NPK_BAUD_AUTODETECT     1
static const uint32_t NPK_BAUD_CANDIDATES[] = { 4800, 9600, 2400 };

#define NPK_SLAVE_ID            0x01
#define NPK_RESPONSE_TIMEOUT_MS  400
#define NPK_RETRIES                3
#define NPK_INTERFRAME_MS         10   // >= 3.5 char times at 2400 baud

// ---------------------------------------------------------------------------
// Register map (manual pages 3-4)
// ---------------------------------------------------------------------------
// Measurements, function code 0x03:
//   0x0000  Humidity       0.1 %RH        read
//   0x0001  Temperature    0.1 degC       read
//   0x0002  Conductivity   1 us/cm        read
//   0x0003  pH             0.1            read
//   0x0004  Nitrogen       1 mg/kg        read / WRITE
//   0x0005  Phosphorus     1 mg/kg        read / WRITE
//   0x0006  Potassium      1 mg/kg        read / WRITE
//   0x0007  Salinity       1 mg/L         read
//   0x0008  TDS            1 mg/L         read
//
// The sensor's own calibration, function code 0x06 to write:
//   0x0022  Conductivity factor   0-100 = 0.0-10.0 %, default 0
//   0x0023  Salinity factor       0-100 = 0.00-1.00, default 55
//   0x0024  TDS factor            0-100 = 0.00-1.00, default 50
//   0x0050  Temperature offset    0.1
//   0x0051  Humidity offset       0.1
//   0x0052  Conductivity offset   1
//   0x0053  pH offset             1
//   0x04E8  Nitrogen factor,   IEEE-754 float, high word
//   0x04E9  Nitrogen factor,   low word
//   0x04EA  Nitrogen offset
//   0x04F2  Phosphorus factor, high word
//   0x04F3  Phosphorus factor, low word
//   0x04F4  Phosphorus offset
//   0x04FC  Potassium factor,  high word
//   0x04FD  Potassium factor,  low word
//   0x04FE  Potassium offset
//   0x07D0  Slave ID    1-254
//   0x07D1  Baud rate   0 = 2400, 1 = 4800, 2 = 9600
//
// Note: the manual's prose says "read function code: 0x30, write function
// code: 0x60". Every worked example uses 0x03 and 0x06, and those are what
// verify against the printed CRCs, so 0x30/0x60 is a typo for the decimal
// function numbers 3 and 6.
#define NPK_REG_MEASUREMENTS   0x0000   // start of the measurement block
#define NPK_REG_COUNT               7   // humidity..potassium, the original read
#define NPK_REG_NITROGEN       0x0004
#define NPK_REG_PHOSPHORUS     0x0005
#define NPK_REG_POTASSIUM      0x0006
#define NPK_REG_TEMP_OFFSET    0x0050
#define NPK_REG_HUM_OFFSET     0x0051
#define NPK_REG_EC_OFFSET      0x0052
#define NPK_REG_PH_OFFSET      0x0053
#define NPK_REG_N_FACTOR       0x04E8   // + 1 = low word, + 2 = offset
#define NPK_REG_P_FACTOR       0x04F2
#define NPK_REG_K_FACTOR       0x04FC

// Conductivity is register 0x0002, slot 2 of the block already being read, so
// it costs nothing to decode and publish. Expect a constant 0 from this unit:
// the register answers, but the probe does not actually measure conductivity,
// so the value is not a fault and not a comms problem. It is published anyway
// to keep the payload shape stable for downstream consumers.
//
// Set to 0 to leave it out of the payload entirely.
#define NPK_ENABLE_CONDUCTIVITY 1

// Reject readings outside the measuring ranges on manual page 1. A wrong
// scale or slot mapping shows up as 152 %RH or 4090 mg/kg, and without this
// those get published as though they were real.
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
// Calibration held in the ESP32 (separate from the sensor's own registers)
// ---------------------------------------------------------------------------
#define NPK_NVS_NAMESPACE   "npkcfg"
#define NPK_CAL_SAMPLES     8      // sweeps averaged when capturing a point
#define NPK_CAL_MIN_SPAN    0.01f  // reject a two-point solve on a flat span

#endif // NPK_CONFIG_H

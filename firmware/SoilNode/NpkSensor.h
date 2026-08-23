/*
 * NpkSensor.h - the seven measured quantities, and the Modbus RTU master
 * that reads them from the JXBS-3001-TR probe.
 *
 * Owns the RS-485 half-duplex turnaround, CRC generation and checking, the
 * register map, and the conversion from raw register counts to engineering
 * units. Knows nothing about calibration, WiFi or MQTT.
 */
#ifndef NPK_SENSOR_H
#define NPK_SENSOR_H

#include <Arduino.h>

enum NpkChannelId : uint8_t {
  NPK_MOISTURE = 0,
  NPK_TEMPERATURE,
  NPK_CONDUCTIVITY,
  NPK_PH,
  NPK_NITROGEN,
  NPK_PHOSPHORUS,
  NPK_POTASSIUM,
  NPK_CHANNEL_COUNT
};

struct NpkChannel {
  const char* key;      // command / NVS key, e.g. "ph"
  const char* jsonKey;  // key used in the published payload, e.g. "PH"
  const char* unit;
  float       scale;    // raw register counts per engineering unit
  bool        isSigned; // register carries a 16-bit two's complement value
  uint8_t     decimals;
};

extern const NpkChannel NPK_CHANNELS[NPK_CHANNEL_COUNT];

// Resolve a channel name ("ph", "PH", "temperature", "ec", ...).
// Returns -1 if it is not recognised.
int npkChannelFromKey(const char* key);

uint16_t npkModbusCrc(const uint8_t* data, uint8_t len);

// One complete sweep of the probe.
struct NpkReading {
  uint16_t raw[NPK_CHANNEL_COUNT];     // register word exactly as received
  float    scaled[NPK_CHANNEL_COUNT];  // engineering units, uncalibrated
  bool     valid[NPK_CHANNEL_COUNT];
  bool     complete;                   // every channel is valid
  uint8_t  failedOps;                  // transactions that got no reply
};

class NpkSensor {
 public:
  void begin();

  // Run every transaction in the active register profile. Returns true when
  // all of them succeeded; partial results are still written to `out`.
  bool read(NpkReading& out);

  // Average `samples` sweeps. Used when capturing a calibration point, where
  // a single noisy reading would be baked into the coefficients.
  bool readAveraged(NpkReading& out, uint8_t samples);

  // Try each rate in NPK_BAUD_CANDIDATES until the probe answers. Returns
  // true and leaves the port there, or false and restores the default.
  bool detectBaud();

  uint32_t baud() const { return baud_; }
  void setBaud(uint32_t baud);

  // Read registers one at a time across a range and report which answer. The
  // manual for this family contains transcription errors (see README), so
  // this is how to find out what a given unit really implements.
  void scanRegisters(uint16_t first, uint16_t last, Print& out);

  const char* lastError() const { return lastError_; }

 private:
  bool transaction(uint16_t addr, uint8_t count, uint16_t* regs);
  bool sendFrame(const uint8_t* frame, uint8_t len);
  int  readFrame(uint8_t* buf, uint8_t expected, uint32_t timeoutMs);
  void driveTransmit(bool enable);

  uint32_t    baud_ = 0;
  const char* lastError_ = "";
};

#endif // NPK_SENSOR_H

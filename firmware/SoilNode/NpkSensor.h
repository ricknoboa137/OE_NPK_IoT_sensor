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
#include "NpkConfig.h"

// Conductivity is register 0x0002, decoded and published like the rest.
// This unit reports a constant 0 for it because it does not measure
// conductivity - that is expected, not a fault. NPK_ENABLE_CONDUCTIVITY
// drops it from the payload if the constant is more noise than it is worth.
enum NpkChannelId : uint8_t {
  NPK_MOISTURE = 0,
  NPK_TEMPERATURE,
#if NPK_ENABLE_CONDUCTIVITY
  NPK_CONDUCTIVITY,
#endif
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
  float       lo;       // physical limits from datasheet section 1.3;
  float       hi;       // a reading outside them means the map or scale is wrong
};

extern const NpkChannel NPK_CHANNELS[NPK_CHANNEL_COUNT];

// Resolve a channel name ("ph", "PH", "temperature", "ec", ...).
// Returns -1 if it is not recognised.
int npkChannelFromKey(const char* key);

// Is this value physically possible for the channel? Used both on the raw
// reading and again on the calibrated result, so bad coefficients cannot
// publish something the sensor could never have measured.
bool npkInRange(uint8_t ch, float value);

uint16_t npkModbusCrc(const uint8_t* data, uint8_t len);

// One complete sweep of the probe.
struct NpkReading {
  uint16_t raw[NPK_CHANNEL_COUNT];     // register word exactly as received
  float    scaled[NPK_CHANNEL_COUNT];  // engineering units, uncalibrated
  bool     valid[NPK_CHANNEL_COUNT];
  bool     outOfRange[NPK_CHANNEL_COUNT];  // answered, but physically impossible
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

  // Read registers one at a time across a range and report what they hold.
  //
  // This probe answers at EVERY address, returning zero for registers it does
  // not implement rather than a Modbus exception, so "it answered" carries no
  // information at all. nonZeroOnly skips the zeros, which is the difference
  // between a readable sweep and thousands of meaningless lines.
  void scanRegisters(uint16_t first, uint16_t last, Print& out,
                     bool nonZeroOnly = false);

  // --- direct register access, for the sensor's own calibration ------------
  // These reach registers outside the measurement block: the offsets at
  // 0x0050-0x0053, the NPK factor/offset triplets, and the writable NPK
  // measurement registers themselves.
  bool readRegisters(uint16_t addr, uint8_t count, uint16_t* out);
  bool writeRegister(uint16_t addr, uint16_t value);        // function 0x06

  // The NPK factors are IEEE-754 floats spread over two registers, high word
  // first (manual page 4).
  bool readFloat(uint16_t addrHigh, float& out);
  bool writeFloat(uint16_t addrHigh, float value);

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

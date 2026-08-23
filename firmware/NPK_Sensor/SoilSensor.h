/*
 * SoilSensor.h - Modbus RTU master for the JXBS-3001-TR soil 7-in-1 probe.
 *
 * Owns the RS-485 half-duplex turnaround, CRC generation and checking, the
 * register map, and conversion from raw register counts to engineering units.
 * It knows nothing about calibration, WiFi or MQTT.
 */
#ifndef SOIL_SENSOR_H
#define SOIL_SENSOR_H

#include <Arduino.h>
#include "Channels.h"

// One complete sweep of the probe.
struct Reading {
  uint16_t raw[CH_COUNT];     // register word exactly as received
  float    scaled[CH_COUNT];  // raw converted to engineering units, uncalibrated
  bool     valid[CH_COUNT];   // this channel was read successfully
  bool     complete;          // every channel is valid
  uint8_t  failedOps;         // transactions that did not produce a reply
};

class SoilSensor {
 public:
  void begin();

  // Run every transaction in the active register profile. Returns true when
  // all of them succeeded; partial results are still written to `out`.
  bool read(Reading& out);

  // Average `samples` sweeps. Used when capturing a calibration point, where
  // a single noisy reading would bake the noise into the coefficients.
  bool readAveraged(Reading& out, uint8_t samples);

  // Try each baud rate in kSensorBaudCandidates until the probe answers.
  // Returns true and leaves the port at the working rate, or false and
  // restores the configured default.
  bool detectBaud();

  uint32_t baud() const { return baud_; }
  void setBaud(uint32_t baud);

  // Read registers one at a time across a range and report which ones answer.
  // The manual for this family contains transcription errors (see README), so
  // this is the way to find out what a particular unit really implements.
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

uint16_t modbusCrc(const uint8_t* data, uint8_t len);

#endif // SOIL_SENSOR_H

/*
 * Calibration.h - per-channel linear correction, persisted in NVS.
 *
 * Every channel carries two coefficients and the node reports
 *
 *     value = A * raw + B
 *
 * where `raw` is the register value already divided by the datasheet scale
 * factor, so A and B are expressed in engineering units. A defaults to 1.0 and
 * B to 0.0, which reproduces the uncalibrated reading exactly.
 *
 * A is the span (gain) correction and B the offset. There are three ways to
 * arrive at them:
 *
 *   set       - type both coefficients in directly, if they came from a lab
 *               regression or a previous unit.
 *   one-point - hold A and solve B from a single known reference. This is the
 *               right move for an offset-only trim, e.g. a probe reading
 *               2 %RH in dry air.
 *   two-point - capture a low reference and a high reference and solve both:
 *                   A = (ref_hi - ref_lo) / (raw_hi - raw_lo)
 *                   B =  ref_lo - A * raw_lo
 *               This is the correct procedure for pH (buffer 4.00 and 7.00)
 *               and for EC against two standard solutions.
 */
#ifndef CALIBRATION_H
#define CALIBRATION_H

#include <Arduino.h>
#include "Channels.h"

struct Coefficients {
  float a;
  float b;
};

class Calibration {
 public:
  void begin();

  float apply(uint8_t ch, float raw) const;
  Coefficients get(uint8_t ch) const;
  bool isDefault(uint8_t ch) const;

  // Store coefficients and commit them to NVS. Rejects A == 0, which would
  // flatten the channel to a constant.
  bool set(uint8_t ch, float a, float b);

  bool resetChannel(uint8_t ch);
  void resetAll();

  // Offset-only trim: keeps the current A, solves B so the reported value
  // becomes `reference` for this raw reading.
  bool onePoint(uint8_t ch, float raw, float reference);

  // Two-point sequence. captureLow() stashes the first point in RAM; it is
  // not persisted, so a reboot between the two steps starts over.
  bool  captureLow(uint8_t ch, float raw, float reference);
  bool  solveHigh(uint8_t ch, float raw, float reference, const char** error);
  bool  hasPendingLow(uint8_t ch) const;
  float pendingRaw(uint8_t ch) const;
  float pendingRef(uint8_t ch) const;
  void  clearPending(uint8_t ch);

 private:
  void persist(uint8_t ch);

  Coefficients coef_[CH_COUNT];
  float pendingRaw_[CH_COUNT];
  float pendingRef_[CH_COUNT];
  bool  pending_[CH_COUNT];
};

#endif // CALIBRATION_H

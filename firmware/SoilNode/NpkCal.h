/*
 * NpkCal.h - per-channel linear correction, persisted in NVS.
 *
 * Every channel carries two coefficients and the node reports
 *
 *     value = A * raw + B
 *
 * where `raw` is the register value already divided by the datasheet scale
 * factor, so A and B are expressed in engineering units. A defaults to 1.0
 * and B to 0.0, which reproduces the uncalibrated reading exactly.
 *
 * A is the span (gain) correction and B the offset. Three ways to get them:
 *
 *   set       - type both in directly, from a lab regression or another unit.
 *   one-point - hold A and solve B from a single known reference. Right for
 *               an offset-only trim, e.g. a probe reading 2 %RH in dry air.
 *   two-point - capture a low and a high reference and solve both:
 *                   A = (ref_hi - ref_lo) / (raw_hi - raw_lo)
 *                   B =  ref_lo - A * raw_lo
 *               The correct procedure for pH (buffer 4.00 and 7.00) and for
 *               EC against two standard solutions.
 */
#ifndef NPK_CAL_H
#define NPK_CAL_H

#include <Arduino.h>
#include "NpkSensor.h"

struct NpkCoeff {
  float a;
  float b;
};

class NpkCal {
 public:
  void begin();

  float apply(uint8_t ch, float raw) const;
  NpkCoeff get(uint8_t ch) const;
  bool isDefault(uint8_t ch) const;

  // Store coefficients and commit to NVS. Rejects anything non-finite, an A
  // of zero, and magnitudes far outside a plausible scale or offset
  // correction - a mistyped gain is otherwise indistinguishable from a
  // deliberate one. setChecked reports why it refused.
  bool set(uint8_t ch, float a, float b);
  bool setChecked(uint8_t ch, float a, float b, const char** error);

  bool resetChannel(uint8_t ch);
  void resetAll();

  // Offset-only trim: keeps the current A, solves B so the reported value
  // becomes `reference` for this raw reading.
  bool onePoint(uint8_t ch, float raw, float reference, const char** error = nullptr);

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

  NpkCoeff coef_[NPK_CHANNEL_COUNT];
  float pendingRaw_[NPK_CHANNEL_COUNT];
  float pendingRef_[NPK_CHANNEL_COUNT];
  bool  pending_[NPK_CHANNEL_COUNT];
};

#endif // NPK_CAL_H

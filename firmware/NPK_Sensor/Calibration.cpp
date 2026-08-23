#include "Calibration.h"
#include "Config.h"
#include <Preferences.h>

static Preferences g_prefs;

// NVS keys are limited to 15 characters. The longest channel key is
// "conductivity" (12), so "a_" + key stays inside the limit.
static void keyFor(char* out, size_t n, char which, uint8_t ch) {
  snprintf(out, n, "%c_%s", which, CHANNELS[ch].key);
}

void Calibration::begin() {
  g_prefs.begin(NVS_NAMESPACE, false);
  for (uint8_t c = 0; c < CH_COUNT; ++c) {
    char ka[20], kb[20];
    keyFor(ka, sizeof(ka), 'a', c);
    keyFor(kb, sizeof(kb), 'b', c);
    coef_[c].a = g_prefs.getFloat(ka, 1.0f);
    coef_[c].b = g_prefs.getFloat(kb, 0.0f);
    if (!isfinite(coef_[c].a) || coef_[c].a == 0.0f) coef_[c].a = 1.0f;
    if (!isfinite(coef_[c].b)) coef_[c].b = 0.0f;
    pending_[c] = false;
    pendingRaw_[c] = 0.0f;
    pendingRef_[c] = 0.0f;
  }
}

void Calibration::persist(uint8_t ch) {
  char ka[20], kb[20];
  keyFor(ka, sizeof(ka), 'a', ch);
  keyFor(kb, sizeof(kb), 'b', ch);
  g_prefs.putFloat(ka, coef_[ch].a);
  g_prefs.putFloat(kb, coef_[ch].b);
}

float Calibration::apply(uint8_t ch, float raw) const {
  if (ch >= CH_COUNT) return raw;
  return coef_[ch].a * raw + coef_[ch].b;
}

Coefficients Calibration::get(uint8_t ch) const {
  if (ch >= CH_COUNT) return { 1.0f, 0.0f };
  return coef_[ch];
}

bool Calibration::isDefault(uint8_t ch) const {
  if (ch >= CH_COUNT) return true;
  return coef_[ch].a == 1.0f && coef_[ch].b == 0.0f;
}

bool Calibration::set(uint8_t ch, float a, float b) {
  if (ch >= CH_COUNT) return false;
  if (!isfinite(a) || !isfinite(b) || a == 0.0f) return false;
  coef_[ch].a = a;
  coef_[ch].b = b;
  persist(ch);
  return true;
}

bool Calibration::resetChannel(uint8_t ch) {
  if (ch >= CH_COUNT) return false;
  coef_[ch].a = 1.0f;
  coef_[ch].b = 0.0f;
  pending_[ch] = false;
  persist(ch);
  return true;
}

void Calibration::resetAll() {
  for (uint8_t c = 0; c < CH_COUNT; ++c) resetChannel(c);
}

bool Calibration::onePoint(uint8_t ch, float raw, float reference) {
  if (ch >= CH_COUNT || !isfinite(raw) || !isfinite(reference)) return false;
  // Hold the gain, move the offset so that A * raw + B == reference.
  return set(ch, coef_[ch].a, reference - coef_[ch].a * raw);
}

bool Calibration::captureLow(uint8_t ch, float raw, float reference) {
  if (ch >= CH_COUNT || !isfinite(raw) || !isfinite(reference)) return false;
  pendingRaw_[ch] = raw;
  pendingRef_[ch] = reference;
  pending_[ch] = true;
  return true;
}

bool Calibration::solveHigh(uint8_t ch, float raw, float reference,
                            const char** error) {
  const char* dummy = nullptr;
  if (error == nullptr) error = &dummy;

  if (ch >= CH_COUNT) { *error = "unknown channel"; return false; }
  if (!pending_[ch])  { *error = "no low point captured yet"; return false; }
  if (!isfinite(raw) || !isfinite(reference)) { *error = "bad value"; return false; }

  const float rawSpan = raw - pendingRaw_[ch];
  if (fabsf(rawSpan) < CAL_MIN_RAW_SPAN) {
    *error = "the two raw readings are too close together";
    return false;
  }

  const float a = (reference - pendingRef_[ch]) / rawSpan;
  const float b = pendingRef_[ch] - a * pendingRaw_[ch];
  if (!isfinite(a) || !isfinite(b) || a == 0.0f) {
    *error = "solve produced an unusable gain";
    return false;
  }

  pending_[ch] = false;
  if (!set(ch, a, b)) { *error = "could not store coefficients"; return false; }
  *error = "";
  return true;
}

bool  Calibration::hasPendingLow(uint8_t ch) const {
  return ch < CH_COUNT && pending_[ch];
}
float Calibration::pendingRaw(uint8_t ch) const {
  return ch < CH_COUNT ? pendingRaw_[ch] : 0.0f;
}
float Calibration::pendingRef(uint8_t ch) const {
  return ch < CH_COUNT ? pendingRef_[ch] : 0.0f;
}
void  Calibration::clearPending(uint8_t ch) {
  if (ch < CH_COUNT) pending_[ch] = false;
}

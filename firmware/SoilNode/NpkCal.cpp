#include "NpkCal.h"
#include "NpkConfig.h"
#include <Preferences.h>

static Preferences g_prefs;

// NVS keys are limited to 15 characters. The longest channel key is
// "conductivity" (12), so "a_" + key stays inside the limit.
static void npkKeyFor(char* out, size_t n, char which, uint8_t ch) {
  snprintf(out, n, "%c_%s", which, NPK_CHANNELS[ch].key);
}

// isfinite() and a != 0 are necessary but nowhere near sufficient. A typed
// "100" where "1.00" was meant is finite and non-zero, and so is a denormal
// that silently collapses the channel. These bounds are deliberately loose -
// the largest legitimate gain is a scale correction, and pH reported in 0.01
// steps where this expects 0.1 only needs A = 10 - so anything outside them
// is a mistake rather than an unusual calibration.
static bool npkCoeffPlausible(float a, float b, const char** why) {
  const char* dummy = nullptr;
  if (why == nullptr) why = &dummy;
  if (!isfinite(a) || !isfinite(b)) { *why = "coefficients must be finite"; return false; }
  if (a == 0.0f)         { *why = "A of zero would flatten the channel to a constant"; return false; }
  if (fabsf(a) < 1e-3f)  { *why = "A below 0.001 collapses the channel"; return false; }
  if (fabsf(a) > 1e3f)   { *why = "A above 1000 is far outside a plausible scale correction"; return false; }
  if (fabsf(b) > 1e5f)   { *why = "B above 100000 is far outside a plausible offset"; return false; }
  *why = "";
  return true;
}

void NpkCal::begin() {
  g_prefs.begin(NPK_NVS_NAMESPACE, false);
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    char ka[20], kb[20];
    npkKeyFor(ka, sizeof(ka), 'a', c);
    npkKeyFor(kb, sizeof(kb), 'b', c);
    coef_[c].a = g_prefs.getFloat(ka, 1.0f);
    coef_[c].b = g_prefs.getFloat(kb, 0.0f);
    // Hold stored values to the same bar as freshly entered ones. NVS can be
    // corrupted, and a channel silently stuck on a garbage gain is worse than
    // one that has quietly reverted to uncalibrated.
    if (!npkCoeffPlausible(coef_[c].a, coef_[c].b, nullptr)) {
      coef_[c].a = 1.0f;
      coef_[c].b = 0.0f;
    }
    pending_[c] = false;
    pendingRaw_[c] = 0.0f;
    pendingRef_[c] = 0.0f;
  }
}

void NpkCal::persist(uint8_t ch) {
  char ka[20], kb[20];
  npkKeyFor(ka, sizeof(ka), 'a', ch);
  npkKeyFor(kb, sizeof(kb), 'b', ch);
  g_prefs.putFloat(ka, coef_[ch].a);
  g_prefs.putFloat(kb, coef_[ch].b);
}

float NpkCal::apply(uint8_t ch, float raw) const {
  if (ch >= NPK_CHANNEL_COUNT) return raw;
  return coef_[ch].a * raw + coef_[ch].b;
}

NpkCoeff NpkCal::get(uint8_t ch) const {
  if (ch >= NPK_CHANNEL_COUNT) { NpkCoeff k = { 1.0f, 0.0f }; return k; }
  return coef_[ch];
}

bool NpkCal::isDefault(uint8_t ch) const {
  if (ch >= NPK_CHANNEL_COUNT) return true;
  return coef_[ch].a == 1.0f && coef_[ch].b == 0.0f;
}

bool NpkCal::set(uint8_t ch, float a, float b) {
  return setChecked(ch, a, b, nullptr);
}

bool NpkCal::setChecked(uint8_t ch, float a, float b, const char** error) {
  const char* dummy = nullptr;
  if (error == nullptr) error = &dummy;
  if (ch >= NPK_CHANNEL_COUNT) { *error = "unknown channel"; return false; }
  if (!npkCoeffPlausible(a, b, error)) return false;

  coef_[ch].a = a;
  coef_[ch].b = b;
  persist(ch);
  *error = "";
  return true;
}

bool NpkCal::resetChannel(uint8_t ch) {
  if (ch >= NPK_CHANNEL_COUNT) return false;
  coef_[ch].a = 1.0f;
  coef_[ch].b = 0.0f;
  pending_[ch] = false;
  persist(ch);
  return true;
}

void NpkCal::resetAll() {
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) resetChannel(c);
}

bool NpkCal::onePoint(uint8_t ch, float raw, float reference, const char** error) {
  const char* dummy = nullptr;
  if (error == nullptr) error = &dummy;
  if (ch >= NPK_CHANNEL_COUNT) { *error = "unknown channel"; return false; }
  if (!isfinite(raw) || !isfinite(reference)) { *error = "reading or reference not finite"; return false; }
  // Hold the gain, move the offset so that A * raw + B == reference.
  return setChecked(ch, coef_[ch].a, reference - coef_[ch].a * raw, error);
}

bool NpkCal::captureLow(uint8_t ch, float raw, float reference) {
  if (ch >= NPK_CHANNEL_COUNT || !isfinite(raw) || !isfinite(reference)) return false;
  pendingRaw_[ch] = raw;
  pendingRef_[ch] = reference;
  pending_[ch] = true;
  return true;
}

bool NpkCal::solveHigh(uint8_t ch, float raw, float reference, const char** error) {
  const char* dummy = nullptr;
  if (error == nullptr) error = &dummy;

  if (ch >= NPK_CHANNEL_COUNT) { *error = "unknown channel"; return false; }
  if (!pending_[ch])           { *error = "no low point captured yet"; return false; }
  if (!isfinite(raw) || !isfinite(reference)) { *error = "bad value"; return false; }

  const float rawSpan = raw - pendingRaw_[ch];
  if (fabsf(rawSpan) < NPK_CAL_MIN_SPAN) {
    *error = "the two raw readings are too close together";
    return false;
  }

  const float a = (reference - pendingRef_[ch]) / rawSpan;
  const float b = pendingRef_[ch] - a * pendingRaw_[ch];
  if (!isfinite(a) || !isfinite(b) || a == 0.0f) {
    *error = "solve produced an unusable gain";
    return false;
  }

  if (!setChecked(ch, a, b, error)) return false;   // *error already set
  pending_[ch] = false;
  *error = "";
  return true;
}

bool NpkCal::hasPendingLow(uint8_t ch) const {
  return ch < NPK_CHANNEL_COUNT && pending_[ch];
}
float NpkCal::pendingRaw(uint8_t ch) const {
  return ch < NPK_CHANNEL_COUNT ? pendingRaw_[ch] : 0.0f;
}
float NpkCal::pendingRef(uint8_t ch) const {
  return ch < NPK_CHANNEL_COUNT ? pendingRef_[ch] : 0.0f;
}
void NpkCal::clearPending(uint8_t ch) {
  if (ch < NPK_CHANNEL_COUNT) pending_[ch] = false;
}

#include "NpkCal.h"
#include "NpkConfig.h"
#include <Preferences.h>

static Preferences g_prefs;

// NVS keys are limited to 15 characters. The longest channel key is
// "conductivity" (12), so "a_" + key stays inside the limit.
static void npkKeyFor(char* out, size_t n, char which, uint8_t ch) {
  snprintf(out, n, "%c_%s", which, NPK_CHANNELS[ch].key);
}

void NpkCal::begin() {
  g_prefs.begin(NPK_NVS_NAMESPACE, false);
  for (uint8_t c = 0; c < NPK_CHANNEL_COUNT; ++c) {
    char ka[20], kb[20];
    npkKeyFor(ka, sizeof(ka), 'a', c);
    npkKeyFor(kb, sizeof(kb), 'b', c);
    coef_[c].a = g_prefs.getFloat(ka, 1.0f);
    coef_[c].b = g_prefs.getFloat(kb, 0.0f);
    if (!isfinite(coef_[c].a) || coef_[c].a == 0.0f) coef_[c].a = 1.0f;
    if (!isfinite(coef_[c].b)) coef_[c].b = 0.0f;
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
  if (ch >= NPK_CHANNEL_COUNT) return false;
  if (!isfinite(a) || !isfinite(b) || a == 0.0f) return false;
  coef_[ch].a = a;
  coef_[ch].b = b;
  persist(ch);
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

bool NpkCal::onePoint(uint8_t ch, float raw, float reference) {
  if (ch >= NPK_CHANNEL_COUNT || !isfinite(raw) || !isfinite(reference)) return false;
  // Hold the gain, move the offset so that A * raw + B == reference.
  return set(ch, coef_[ch].a, reference - coef_[ch].a * raw);
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

  pending_[ch] = false;
  if (!set(ch, a, b)) { *error = "could not store coefficients"; return false; }
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

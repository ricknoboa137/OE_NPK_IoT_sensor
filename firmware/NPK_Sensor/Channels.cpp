#include "Channels.h"
#include "Config.h"

/*
 * Scale factors come from the register table in section 4.3 of the
 * JXBS-3001-TR manual:
 *
 *   0x0006  pH             unit 0.01 pH     -> 100 counts per pH
 *   0x0012  soil moisture  unit 0.1 %RH     ->  10 counts per %
 *   0x0013  soil temp      unit 0.1 degC    ->  10 counts per degC, signed
 *   0x0015  conductivity   unit 1 us/cm     ->   1 count  per us/cm
 *   0x001E  nitrogen       unit 1 mg/kg     ->   1 count  per mg/kg
 *   0x001F  phosphorus     unit 1 mg/kg     ->   1 count  per mg/kg
 *   0x0020  potassium      unit 1 mg/kg     ->   1 count  per mg/kg
 *
 * Temperature is the only signed value: section 4.4.1 reads FF9BH back as
 * -10.1 degC.
 *
 * The legacy profile keeps the divide-by-ten that the original sketch applied
 * to every channel. If the unit disagrees with either profile the A
 * coefficient absorbs it - a sensor reporting pH in 0.1 steps instead of 0.01
 * is corrected with A = 10.
 */
#if SENSOR_REGISTER_PROFILE == PROFILE_DATASHEET
const ChannelDef CHANNELS[CH_COUNT] = {
  // key             jsonKey          unit       scale  signed  dec
  { "moisture",     "Humidity",      "%RH",      10.0f, false, 1 },
  { "temperature",  "Temperature",   "degC",     10.0f, true,  1 },
  { "conductivity", "Conductivity",  "us/cm",     1.0f, false, 0 },
  { "ph",           "PH",            "pH",      100.0f, false, 2 },
  { "nitrogen",     "Nitrogen",      "mg/kg",     1.0f, false, 0 },
  { "phosphorus",   "Phosphorus",    "mg/kg",     1.0f, false, 0 },
  { "potassium",    "Potassium",     "mg/kg",     1.0f, false, 0 },
};
#else
const ChannelDef CHANNELS[CH_COUNT] = {
  { "moisture",     "Humidity",      "%RH",      10.0f, false, 1 },
  { "temperature",  "Temperature",   "degC",     10.0f, true,  1 },
  { "conductivity", "Conductivity",  "us/cm",    10.0f, false, 1 },
  { "ph",           "PH",            "pH",       10.0f, false, 2 },
  { "nitrogen",     "Nitrogen",      "mg/kg",    10.0f, false, 1 },
  { "phosphorus",   "Phosphorus",    "mg/kg",    10.0f, false, 1 },
  { "potassium",    "Potassium",     "mg/kg",    10.0f, false, 1 },
};
#endif

int channelFromKey(const char* key) {
  if (key == nullptr) return -1;
  for (uint8_t i = 0; i < CH_COUNT; ++i) {
    if (strcasecmp(key, CHANNELS[i].key) == 0) return i;
    if (strcasecmp(key, CHANNELS[i].jsonKey) == 0) return i;
  }
  // Convenience aliases.
  if (strcasecmp(key, "humidity") == 0) return CH_MOISTURE;
  if (strcasecmp(key, "temp") == 0)     return CH_TEMPERATURE;
  if (strcasecmp(key, "ec") == 0)       return CH_CONDUCTIVITY;
  if (strcasecmp(key, "n") == 0)        return CH_NITROGEN;
  if (strcasecmp(key, "p") == 0)        return CH_PHOSPHORUS;
  if (strcasecmp(key, "k") == 0)        return CH_POTASSIUM;
  return -1;
}

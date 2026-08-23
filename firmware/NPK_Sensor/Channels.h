/*
 * Channels.h - the seven measured quantities, in one table.
 *
 * Both the Modbus layer and the calibration layer index off ChannelId, so the
 * definition lives here rather than in either of them.
 */
#ifndef CHANNELS_H
#define CHANNELS_H

#include <Arduino.h>

enum ChannelId : uint8_t {
  CH_MOISTURE = 0,
  CH_TEMPERATURE,
  CH_CONDUCTIVITY,
  CH_PH,
  CH_NITROGEN,
  CH_PHOSPHORUS,
  CH_POTASSIUM,
  CH_COUNT
};

struct ChannelDef {
  const char* key;      // command / NVS key, e.g. "ph"
  const char* jsonKey;  // key used in the published payload, e.g. "PH"
  const char* unit;
  float       scale;    // raw register counts per engineering unit
  bool        isSigned; // register carries a 16-bit two's complement value
  uint8_t     decimals; // digits to print
};

extern const ChannelDef CHANNELS[CH_COUNT];

// Resolve a channel key ("ph", "PH", "temperature", ...). Returns -1 if the
// name is not recognised.
int channelFromKey(const char* key);

#endif // CHANNELS_H

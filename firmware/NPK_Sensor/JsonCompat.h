/*
 * JsonCompat.h - one macro so the sketch builds against ArduinoJson 6 and 7.
 *
 * v7 removed the fixed-capacity documents and made JsonDocument elastic;
 * v6 still needs a capacity. Declaring documents through this macro keeps the
 * rest of the code free of version checks.
 */
#ifndef JSON_COMPAT_H
#define JSON_COMPAT_H

#include <ArduinoJson.h>

#if ARDUINOJSON_VERSION_MAJOR >= 7
  #define NPK_JSON_DOC(name, capacity) JsonDocument name
#else
  #define NPK_JSON_DOC(name, capacity) StaticJsonDocument<capacity> name
#endif

#endif // JSON_COMPAT_H

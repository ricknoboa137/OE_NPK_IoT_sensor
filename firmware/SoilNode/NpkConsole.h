/*
 * NpkConsole.h - the console, shared by the serial port and MQTT.
 *
 * Accepts either a plain text line ("cal low ph 4.00") or a JSON object
 * ({"cmd":"cal_low","ch":"ph","ref":4.0}). JSON is normalised into the text
 * form and then run through the same parser, so the two interfaces cannot
 * drift apart.
 *
 * Serial replies go to the console. MQTT replies are published to
 * NPK_TOPIC_REPLY, which lets a dashboard drive a calibration wizard without
 * a USB cable.
 */
#ifndef NPK_CONSOLE_H
#define NPK_CONSOLE_H

#include <Arduino.h>
#include "NpkSensor.h"
#include "NpkCal.h"
#include "NpkNet.h"

// A Print sink that accumulates into a caller-supplied buffer.
class NpkBufferPrint : public Print {
 public:
  NpkBufferPrint(char* buf, size_t capacity) : buf_(buf), cap_(capacity) {
    if (cap_) buf_[0] = '\0';
  }
  size_t write(uint8_t c) override {
    if (len_ + 1 >= cap_) { overflowed_ = true; return 0; }
    buf_[len_++] = (char)c;
    buf_[len_] = '\0';
    return 1;
  }
  size_t write(const uint8_t* data, size_t n) override {
    size_t w = 0;
    while (w < n && write(data[w])) ++w;
    return w;
  }
  const char* c_str() const { return buf_; }
  size_t length() const { return len_; }
  // Silent truncation is worse than none: a reply cut in half reads as though
  // it were the whole answer. Callers check this and say so.
  bool overflowed() const { return overflowed_; }
  void clear() { len_ = 0; overflowed_ = false; if (cap_) buf_[0] = '\0'; }

 private:
  char*  buf_;
  size_t cap_;
  size_t len_ = 0;
  bool   overflowed_ = false;
};

class NpkConsole {
 public:
  void begin(NpkSensor* sensor, NpkCal* cal, NpkNet* net);

  // Non-blocking; assembles one line at a time from the USB console.
  void pollSerial();

  // Called from the MQTT receive callback.
  void handleMqtt(const uint8_t* payload, unsigned int length);

  // Run one command and write the reply to `out`.
  void execute(const char* line, Print& out);

 private:
  void dispatch(char** argv, int argc, Print& out);
  void cmdHelp(Print& out);
  void cmdStatus(Print& out);
  void cmdRead(Print& out);
  void cmdScan(char** argv, int argc, Print& out);
  void cmdCal(char** argv, int argc, Print& out);
  void cmdSensor(char** argv, int argc, Print& out);
  void listCalibration(Print& out);
  int  resolveChannel(const char* name, Print& out);
  bool captureRaw(uint8_t ch, float& rawOut, Print& out);
  bool jsonToLine(const uint8_t* payload, unsigned int length,
                  char* out, size_t cap);

  NpkSensor* sensor_ = nullptr;
  NpkCal*    cal_    = nullptr;
  NpkNet*    net_    = nullptr;

  char   serialBuf_[160];
  size_t serialLen_ = 0;
};

#endif // NPK_CONSOLE_H

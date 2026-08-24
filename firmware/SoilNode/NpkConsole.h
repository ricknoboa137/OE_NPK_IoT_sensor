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

// Appended as the last line of every part except the last one. A reply that
// fits in a single message carries no marker at all, so short replies look
// exactly as they always did. The dashboard accumulates parts until it
// receives one that does NOT end in this.
#define NPK_REPLY_CONTINUES "[continues]"

// A Print sink that publishes console output to MQTT, splitting it across as
// many messages as it takes.
//
// Raising the buffer alone cannot solve this: "scan" over a wide range
// produces unbounded output, and this probe answers at every address, so a
// full sweep is tens of kilobytes. Chunking keeps RAM constant however long
// the reply is. Splits happen only at line boundaries, so no register line is
// ever cut in half.
//
// Everything written is also echoed to the serial console, which is never
// chunked and never truncated.
class NpkChunkedPrint : public Print {
 public:
  NpkChunkedPrint(NpkNet* net, const char* topic, char* buf, size_t capacity,
                  bool echoSerial)
      : net_(net), topic_(topic), buf_(buf), cap_(capacity), echo_(echoSerial) {
    // Reserve room for the continuation marker so a split can always carry
    // one. Without this a chunk could fill exactly and be published unmarked,
    // which reads as the end of the reply.
    usable_ = (cap_ > sizeof(NPK_REPLY_CONTINUES) + 1)
                  ? cap_ - sizeof(NPK_REPLY_CONTINUES) - 1
                  : cap_;
    if (cap_) buf_[0] = '\0';
  }

  size_t write(uint8_t c) override {
    if (echo_) Serial.write(c);
    if (len_ + 1 >= usable_) flushPart();
    if (len_ + 1 >= usable_) return 0;      // pathological: buffer far too small
    buf_[len_++] = (char)c;
    buf_[len_] = '\0';
    if (c == '\n') lastNewline_ = len_;
    return 1;
  }
  size_t write(const uint8_t* data, size_t n) override {
    size_t w = 0;
    while (w < n && write(data[w])) ++w;
    return w;
  }

  // Publish whatever is left, without a continuation marker.
  void finish() {
    if (len_ == 0) return;
    if (net_) net_->publish(topic_, buf_);
    parts_++;
    len_ = 0;
    lastNewline_ = 0;
    if (cap_) buf_[0] = '\0';
  }

  uint16_t parts() const { return parts_; }

 private:
  void flushPart();

  NpkNet*     net_;
  const char* topic_;
  char*       buf_;
  size_t      cap_;
  size_t      usable_ = 0;
  size_t      len_ = 0;
  size_t      lastNewline_ = 0;   // index just past the most recent '\n'
  uint16_t    parts_ = 0;
  bool        echo_;
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

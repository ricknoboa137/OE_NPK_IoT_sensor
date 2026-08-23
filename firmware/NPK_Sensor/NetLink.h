/*
 * NetLink.h - WiFi provisioning and the MQTT link.
 *
 * Named NetLink, not NetworkManager: arduino-esp32 3.x ships its own
 * NetworkManager class in libraries/Network, which WiFi.h pulls in, and the
 * two collide. Do not rename this back.
 *
 * Differences from the original sketch that matter in the field:
 *
 *  - The broker address and port entered in the captive portal are written to
 *    NVS and reloaded at boot. Previously they were captured into RAM after
 *    setServer() had already been called with the compile-time defaults, so
 *    the portal fields never took effect.
 *  - A broker outage no longer erases the WiFi credentials. The original
 *    reconnect() called wm.resetSettings() after five failed MQTT attempts,
 *    which meant a broker reboot could strand the node in AP mode.
 *  - Reconnection is non-blocking with backoff, so sampling continues while
 *    the broker is unreachable.
 */
#ifndef NET_LINK_H
#define NET_LINK_H

#include <Arduino.h>

class NetLink {
 public:
  typedef void (*MessageHandler)(char* topic, uint8_t* payload, unsigned int length);

  bool begin(MessageHandler handler);

  // Pumps the MQTT client and retries the connection when it is down.
  // Never blocks for longer than one connection attempt.
  void loop();

  bool connected();
  bool publish(const char* topic, const char* payload, bool retain = false);

  const char* host() const { return host_; }
  uint16_t    port() const { return port_; }
  const char* clientId() const { return clientId_; }

  // Store a new broker and drop the current connection so loop() picks it up.
  bool setBroker(const char* host, uint16_t port);

  void startPortal();   // open the config portal on demand
  void forgetWiFi();    // clear stored credentials, then reboot

  void printStatus(Print& out);

 private:
  bool connectBroker();
  void loadSettings();

  char     host_[40] = { 0 };
  uint16_t port_ = 1883;
  char     clientId_[24] = { 0 };
  uint32_t nextAttempt_ = 0;
  uint32_t backoff_ = 0;
};

#endif // NET_LINK_H

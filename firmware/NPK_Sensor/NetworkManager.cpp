#include "NetworkManager.h"
#include "Config.h"

#include <WiFi.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <Preferences.h>

static WiFiManager   g_wm;
static WiFiClient    g_wifiClient;
static PubSubClient  g_mqtt(g_wifiClient);
static Preferences   g_net;

static char g_portalHost[40] = MQTT_SERVER_DEFAULT;
static char g_portalPort[6]  = MQTT_PORT_DEFAULT;

static WiFiManagerParameter g_pHost("server", "MQTT broker", g_portalHost, sizeof(g_portalHost) - 1);
static WiFiManagerParameter g_pPort("port",   "MQTT port",   g_portalPort, sizeof(g_portalPort) - 1);

static NetworkManager* g_self = nullptr;

// Fires when the captive portal form is submitted.
static void onSaveParams() {
  const char* h = g_pHost.getValue();
  const char* p = g_pPort.getValue();
  if (g_self && h && *h) {
    long port = (p && *p) ? strtol(p, nullptr, 10) : 0;
    if (port <= 0 || port > 65535) port = 1883;
    g_self->setBroker(h, (uint16_t)port);
    Serial.printf("[net] portal saved broker %s:%ld\r\n", h, port);
  }
}

void NetworkManager::loadSettings() {
  g_net.begin("npknet", false);
  String h = g_net.getString("host", MQTT_SERVER_DEFAULT);
  port_ = g_net.getUShort("port", (uint16_t)strtol(MQTT_PORT_DEFAULT, nullptr, 10));
  if (port_ == 0) port_ = 1883;
  strncpy(host_, h.c_str(), sizeof(host_) - 1);
  host_[sizeof(host_) - 1] = '\0';

  // Seed the portal fields with whatever is currently in force.
  strncpy(g_portalHost, host_, sizeof(g_portalHost) - 1);
  snprintf(g_portalPort, sizeof(g_portalPort), "%u", (unsigned)port_);
}

bool NetworkManager::begin(MessageHandler handler) {
  g_self = this;
  loadSettings();

  uint8_t mac[6];
  WiFi.macAddress(mac);
  snprintf(clientId_, sizeof(clientId_), MQTT_CLIENT_PREFIX "%02X%02X%02X",
           mac[3], mac[4], mac[5]);

  g_pHost.setValue(g_portalHost, sizeof(g_portalHost) - 1);
  g_pPort.setValue(g_portalPort, sizeof(g_portalPort) - 1);

  g_wm.addParameter(&g_pHost);
  g_wm.addParameter(&g_pPort);
  g_wm.setSaveParamsCallback(onSaveParams);
  g_wm.setConfigPortalTimeout(AP_CONFIG_TIMEOUT_S);
  g_wm.setClass("invert");   // dark mode

  Serial.printf("[net] starting WiFi, AP fallback \"%s\"\r\n", AP_NAME);
  const bool up = g_wm.autoConnect(AP_NAME);
  if (!up) {
    // Carry on regardless: the probe is still readable over the serial
    // console and loop() keeps retrying the network in the background.
    Serial.println("[net] WiFi not connected - continuing offline");
  } else {
    Serial.printf("[net] WiFi up, ip %s\r\n", WiFi.localIP().toString().c_str());
  }

  // Re-read the portal fields in case the save callback did not fire.
  const char* h = g_pHost.getValue();
  if (h && *h && strcmp(h, host_) != 0) {
    long p = strtol(g_pPort.getValue(), nullptr, 10);
    setBroker(h, (p > 0 && p <= 65535) ? (uint16_t)p : port_);
  }

  g_mqtt.setBufferSize(MQTT_BUFFER_SIZE);
  g_mqtt.setServer(host_, port_);
  g_mqtt.setCallback(handler);
  g_mqtt.setKeepAlive(30);

  connectBroker();
  return up;
}

bool NetworkManager::setBroker(const char* host, uint16_t port) {
  if (host == nullptr || *host == '\0' || port == 0) return false;
  strncpy(host_, host, sizeof(host_) - 1);
  host_[sizeof(host_) - 1] = '\0';
  port_ = port;

  g_net.putString("host", host_);
  g_net.putUShort("port", port_);

  g_mqtt.disconnect();
  g_mqtt.setServer(host_, port_);
  nextAttempt_ = 0;
  backoff_ = 0;
  return true;
}

bool NetworkManager::connectBroker() {
  if (WiFi.status() != WL_CONNECTED) return false;

  Serial.printf("[net] MQTT connect %s:%u as %s ... ", host_, port_, clientId_);

  // Last will, so the dashboard can tell a crashed node from a quiet one.
  const bool ok = g_mqtt.connect(clientId_, nullptr, nullptr,
                                 TOPIC_STATUS, 0, true, "offline");
  if (ok) {
    Serial.println("connected");
    g_mqtt.publish(TOPIC_STATUS, "online", true);
    g_mqtt.subscribe(TOPIC_COMMAND);
    backoff_ = 0;
  } else {
    Serial.printf("failed, state %d\r\n", g_mqtt.state());
  }
  return ok;
}

void NetworkManager::loop() {
  if (WiFi.status() != WL_CONNECTED) {
    // WiFi.begin() has already been issued by WiFiManager; the ESP32 keeps
    // retrying on its own. Nothing to do but wait.
    return;
  }

  if (g_mqtt.connected()) {
    g_mqtt.loop();
    return;
  }

  const uint32_t now = millis();
  if ((int32_t)(now - nextAttempt_) < 0) return;

  if (!connectBroker()) {
    backoff_ = backoff_ ? min(backoff_ * 2, (uint32_t)MQTT_MAX_BACKOFF_MS)
                        : (uint32_t)MQTT_RETRY_INTERVAL_MS;
    nextAttempt_ = now + backoff_;
    Serial.printf("[net] retrying in %lu ms\r\n", (unsigned long)backoff_);
  }
}

bool NetworkManager::connected() {
  return WiFi.status() == WL_CONNECTED && g_mqtt.connected();
}

bool NetworkManager::publish(const char* topic, const char* payload, bool retain) {
  if (!g_mqtt.connected()) return false;
  return g_mqtt.publish(topic, payload, retain);
}

void NetworkManager::startPortal() {
  Serial.println("[net] opening config portal");
  g_wm.startConfigPortal(AP_NAME);
}

void NetworkManager::forgetWiFi() {
  Serial.println("[net] clearing WiFi credentials and rebooting");
  g_wm.resetSettings();
  delay(500);
  ESP.restart();
}

void NetworkManager::printStatus(Print& out) {
  out.printf("WiFi     : %s", WiFi.status() == WL_CONNECTED ? "connected" : "down");
  if (WiFi.status() == WL_CONNECTED) {
    out.printf("  ssid %s  ip %s  rssi %d dBm",
               WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI());
  }
  out.println();
  out.printf("MQTT     : %s  %s:%u  client %s  state %d\r\n",
             g_mqtt.connected() ? "connected" : "disconnected",
             host_, port_, clientId_, g_mqtt.state());
}

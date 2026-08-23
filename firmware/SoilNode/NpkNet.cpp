#include "NpkNet.h"
#include "NpkConfig.h"

#include <WiFi.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <Preferences.h>

static WiFiManager  g_wm;
static WiFiClient   g_wifiClient;
static PubSubClient g_mqtt(g_wifiClient);
static Preferences  g_netPrefs;

static char g_portalHost[40] = NPK_MQTT_HOST_DEFAULT;
static char g_portalPort[6]  = NPK_MQTT_PORT_DEFAULT;
static char g_portalUser[33] = NPK_MQTT_USER_DEFAULT;
static char g_portalPass[65] = NPK_MQTT_PASS_DEFAULT;

static WiFiManagerParameter g_pHost("server", "MQTT broker", g_portalHost, sizeof(g_portalHost) - 1);
static WiFiManagerParameter g_pPort("port",   "MQTT port",   g_portalPort, sizeof(g_portalPort) - 1);
static WiFiManagerParameter g_pUser("user",   "MQTT username (leave empty if none)",
                                    g_portalUser, sizeof(g_portalUser) - 1);
static WiFiManagerParameter g_pPass("pass",   "MQTT password (leave empty if none)",
                                    g_portalPass, sizeof(g_portalPass) - 1,
                                    " type=\"password\"");

static NpkNet* g_self = nullptr;

// PubSubClient reports failures as a bare number, and 4 vs 5 is exactly the
// distinction you need when a broker starts asking for credentials.
static const char* npkMqttStateText(int state) {
  switch (state) {
    case -4: return "connection timeout";
    case -3: return "connection lost";
    case -2: return "connect failed (host or port unreachable)";
    case -1: return "disconnected";
    case  0: return "connected";
    case  1: return "bad protocol version";
    case  2: return "client id rejected";
    case  3: return "broker unavailable";
    case  4: return "bad username or password";
    case  5: return "not authorised";
    default: return "unknown";
  }
}

// Fires when the captive portal form is submitted.
static void npkOnSaveParams() {
  if (!g_self) return;

  const char* h = g_pHost.getValue();
  const char* p = g_pPort.getValue();
  if (h && *h) {
    long port = (p && *p) ? strtol(p, nullptr, 10) : 0;
    if (port <= 0 || port > 65535) port = 1883;
    g_self->setBroker(h, (uint16_t)port);
    Serial.printf("[net] portal saved broker %s:%ld\r\n", h, port);
  }

  // An empty username means an anonymous broker, so this is not guarded on
  // being non-empty the way the host is - clearing the field must be able to
  // switch the node back to anonymous.
  const char* u = g_pUser.getValue();
  const char* w = g_pPass.getValue();
  g_self->setAuth(u ? u : "", w ? w : "");
  Serial.printf("[net] portal saved MQTT auth: %s\r\n",
                (u && *u) ? u : "(anonymous)");
}

void NpkNet::loadSettings() {
  g_netPrefs.begin("npknet", false);
  String h = g_netPrefs.getString("host", NPK_MQTT_HOST_DEFAULT);
  port_ = g_netPrefs.getUShort("port", (uint16_t)strtol(NPK_MQTT_PORT_DEFAULT, nullptr, 10));
  if (port_ == 0) port_ = 1883;
  strncpy(host_, h.c_str(), sizeof(host_) - 1);
  host_[sizeof(host_) - 1] = '\0';

  String u = g_netPrefs.getString("user", NPK_MQTT_USER_DEFAULT);
  String w = g_netPrefs.getString("pass", NPK_MQTT_PASS_DEFAULT);
  strncpy(user_, u.c_str(), sizeof(user_) - 1);
  user_[sizeof(user_) - 1] = '\0';
  strncpy(pass_, w.c_str(), sizeof(pass_) - 1);
  pass_[sizeof(pass_) - 1] = '\0';

  // Seed the portal fields with whatever is currently in force.
  strncpy(g_portalHost, host_, sizeof(g_portalHost) - 1);
  g_portalHost[sizeof(g_portalHost) - 1] = '\0';
  snprintf(g_portalPort, sizeof(g_portalPort), "%u", (unsigned)port_);
  strncpy(g_portalUser, user_, sizeof(g_portalUser) - 1);
  g_portalUser[sizeof(g_portalUser) - 1] = '\0';
  // The password field is deliberately left blank rather than pre-filled, so
  // the stored one is not served back over an open AP. Leaving it empty on
  // submit keeps the existing password; see setAuth().
  g_portalPass[0] = '\0';
}

bool NpkNet::begin(MessageHandler handler, bool forcePortal) {
  g_self = this;
  loadSettings();

  uint8_t mac[6];
  WiFi.macAddress(mac);
  snprintf(clientId_, sizeof(clientId_), NPK_MQTT_ID_PREFIX "%02X%02X%02X",
           mac[3], mac[4], mac[5]);

  g_pHost.setValue(g_portalHost, sizeof(g_portalHost) - 1);
  g_pPort.setValue(g_portalPort, sizeof(g_portalPort) - 1);
  g_pUser.setValue(g_portalUser, sizeof(g_portalUser) - 1);
  g_pPass.setValue(g_portalPass, sizeof(g_portalPass) - 1);

  g_wm.addParameter(&g_pHost);
  g_wm.addParameter(&g_pPort);
  g_wm.addParameter(&g_pUser);
  g_wm.addParameter(&g_pPass);
  g_wm.setSaveParamsCallback(npkOnSaveParams);
  g_wm.setConfigPortalTimeout(NPK_AP_TIMEOUT_S);
  g_wm.setClass("invert");   // dark mode

  bool up;
  if (forcePortal) {
    // autoConnect() only raises the AP when the stored credentials fail, so
    // there would otherwise be no way to change the broker on a node that is
    // already on WiFi.
    Serial.printf("[net] forced: opening config portal \"%s\"\r\n", NPK_AP_NAME);
    g_wm.startConfigPortal(NPK_AP_NAME);
    up = (WiFi.status() == WL_CONNECTED);
  } else {
    Serial.printf("[net] starting WiFi, AP fallback \"%s\"\r\n", NPK_AP_NAME);
    up = g_wm.autoConnect(NPK_AP_NAME);
  }

  if (!up) {
    // Carry on regardless: the probe is still readable on the serial console
    // and loop() keeps retrying the network in the background.
    Serial.println("[net] WiFi not connected - continuing offline");
  } else {
    Serial.printf("[net] WiFi up, ssid %s, ip %s\r\n",
                  WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
  }

  // Re-read the portal fields in case the save callback did not fire.
  const char* h = g_pHost.getValue();
  if (h && *h && strcmp(h, host_) != 0) {
    long p = strtol(g_pPort.getValue(), nullptr, 10);
    setBroker(h, (p > 0 && p <= 65535) ? (uint16_t)p : port_);
  }

  g_mqtt.setBufferSize(NPK_MQTT_BUFFER);
  g_mqtt.setServer(host_, port_);
  g_mqtt.setCallback(handler);
  g_mqtt.setKeepAlive(30);

  connectBroker();
  return up;
}

bool NpkNet::setBroker(const char* host, uint16_t port) {
  if (host == nullptr || *host == '\0' || port == 0) return false;
  strncpy(host_, host, sizeof(host_) - 1);
  host_[sizeof(host_) - 1] = '\0';
  port_ = port;

  g_netPrefs.putString("host", host_);
  g_netPrefs.putUShort("port", port_);

  g_mqtt.disconnect();
  g_mqtt.setServer(host_, port_);
  nextAttempt_ = 0;
  backoff_ = 0;
  return true;
}

bool NpkNet::setAuth(const char* user, const char* pass) {
  if (user == nullptr) user = "";
  if (pass == nullptr) pass = "";

  if (*user == '\0') {
    // No username means an anonymous broker; a password alone is meaningless,
    // so clear both.
    user_[0] = '\0';
    pass_[0] = '\0';
  } else {
    strncpy(user_, user, sizeof(user_) - 1);
    user_[sizeof(user_) - 1] = '\0';
    // An empty password field keeps whatever is stored. The portal serves the
    // password box blank on purpose, so a blank submit must not wipe it.
    if (*pass != '\0') {
      strncpy(pass_, pass, sizeof(pass_) - 1);
      pass_[sizeof(pass_) - 1] = '\0';
    }
  }

  g_netPrefs.putString("user", user_);
  g_netPrefs.putString("pass", pass_);

  g_mqtt.disconnect();   // force a reconnect with the new credentials
  nextAttempt_ = 0;
  backoff_ = 0;
  return true;
}

bool NpkNet::connectBroker() {
  if (WiFi.status() != WL_CONNECTED) return false;

  Serial.printf("[net] MQTT connect %s:%u as %s, auth %s ... ",
                host_, port_, clientId_, user_[0] ? user_ : "(anonymous)");

  // PubSubClient sends no CONNECT username at all when this is NULL, which is
  // what an anonymous broker expects - passing an empty string instead makes
  // some brokers reject the connection.
  const char* u = user_[0] ? user_ : nullptr;
  const char* w = (user_[0] && pass_[0]) ? pass_ : nullptr;

  // Last will, so a dashboard can tell a crashed node from a quiet one.
  const bool ok = g_mqtt.connect(clientId_, u, w,
                                 NPK_TOPIC_STATUS, 0, true, "offline");
  if (ok) {
    Serial.println("connected");
    g_mqtt.publish(NPK_TOPIC_STATUS, "online", true);
    g_mqtt.subscribe(NPK_TOPIC_CMD);
    backoff_ = 0;
  } else {
    const int st = g_mqtt.state();
    Serial.printf("failed, state %d (%s)\r\n", st, npkMqttStateText(st));
    if (st == 4 || st == 5) {
      Serial.println("[net] the broker wants credentials - set them with");
      Serial.println("      mqttauth <user> <password>   (or via the portal)");
    }
  }
  return ok;
}

void NpkNet::loop() {
  if (WiFi.status() != WL_CONNECTED) {
    // WiFiManager has already issued WiFi.begin(); the ESP32 keeps retrying
    // on its own. Nothing to do but wait.
    return;
  }

  if (g_mqtt.connected()) {
    g_mqtt.loop();
    return;
  }

  const uint32_t now = millis();
  if ((int32_t)(now - nextAttempt_) < 0) return;

  if (!connectBroker()) {
    backoff_ = backoff_ ? min(backoff_ * 2, (uint32_t)NPK_MQTT_MAX_BACKOFF_MS)
                        : (uint32_t)NPK_MQTT_RETRY_MS;
    nextAttempt_ = now + backoff_;
    Serial.printf("[net] retrying in %lu ms\r\n", (unsigned long)backoff_);
  }
}

bool NpkNet::connected() {
  return WiFi.status() == WL_CONNECTED && g_mqtt.connected();
}

bool NpkNet::publish(const char* topic, const char* payload, bool retain) {
  if (!g_mqtt.connected()) return false;
  return g_mqtt.publish(topic, payload, retain);
}

void NpkNet::startPortal() {
  Serial.println("[net] opening config portal");
  g_wm.startConfigPortal(NPK_AP_NAME);
}

void NpkNet::forgetWiFi() {
  Serial.println("[net] clearing WiFi credentials and rebooting");
  g_wm.resetSettings();
  delay(500);
  ESP.restart();
}

void NpkNet::printStatus(Print& out) {
  out.printf("WiFi     : %s", WiFi.status() == WL_CONNECTED ? "connected" : "down");
  if (WiFi.status() == WL_CONNECTED) {
    out.printf("  ssid %s  ip %s  rssi %d dBm",
               WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI());
  }
  out.println();
  const int st = g_mqtt.state();
  out.printf("MQTT     : %s  %s:%u  client %s\r\n",
             g_mqtt.connected() ? "connected" : "disconnected",
             host_, port_, clientId_);
  out.printf("           auth %s   state %d (%s)\r\n",
             user_[0] ? user_ : "(anonymous)", st, npkMqttStateText(st));
}

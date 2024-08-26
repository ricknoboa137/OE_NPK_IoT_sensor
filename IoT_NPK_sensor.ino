#include <SoftwareSerial.h>

#include <WiFiManager.h> // https://github.com/tzapu/WiFiManager
#include <WiFi.h>
#include <PubSubClient.h>
#define TX_PIN 19
#define RX_PIN 18
#define DE_RE_PIN 4
#define LED_PIN 2

SoftwareSerial mod(RX_PIN, TX_PIN);
char mqtt_server[40]= "192.168.0.108";
char mqtt_port[6] = "1883";
WiFiManager wm;
WiFiManagerParameter custom_mqtt_server("server", "mqtt server", mqtt_server, 40);
WiFiManagerParameter custom_mqtt_port("port", "mqtt port", mqtt_port, 6);
WiFiClient espClient;
PubSubClient client(espClient);

const byte nitro[] = { 0x01, 0x03, 0x00, 0x00, 0x00, 0x07, 0x04, 0x08 };
const byte phos[] = { 0x01, 0x03, 0x00, 0x1f, 0x00, 0x01, 0xb5, 0xcc };
const byte pota[] = { 0x01, 0x03, 0x00, 0x20, 0x00, 0x01, 0x85, 0xc0 };

byte values[11];

byte incomingByte[9] = {0};
byte no_Byte = 0;

// Modbus Request Bytes
byte sendBuffer[] = {0x01, 0x03, 0x00, 0x01, 0x00, 0x01, 0xD5, 0xCA}; // Single Read for Temperature
// Modify this array to change the request

float humidity, temperature, nitrog, phospho, potass, ph;
void saveParamCallback();

/////////////////////////////////SETUP///////////////////////////////////////
void setup() {
Serial.begin(115200);
mod.begin(4800);

pinMode(DE_RE_PIN, OUTPUT); // DE/RE Control pin of RS-485
pinMode(LED_PIN, OUTPUT);
digitalWrite(LED_PIN, HIGH);
wm.addParameter(&custom_mqtt_server);
wm.addParameter(&custom_mqtt_port);
wm.setSaveParamsCallback(saveParamCallback);
wm.setClass("invert"); // use darkmode
client.setServer(mqtt_server, atoi(mqtt_port));
client.setCallback(callback);
bool res;
res = wm.autoConnect("Motor_Driver"); // password protected ap ,"password"
if(!res) {
    Serial.println("Failed to connect");}
    // ESP.restart();} 
else {
    //if you get here you have connected to the WiFi    
    Serial.println("connected...yeey :):):)");
    reconnect(); //connect MQTT    
  }
client.subscribe("inTopic");
Serial.println("\n\Swting Up Soil Sensor...\n");
}

//////////////////////////////////LOOP///////////////////////////////////////////
void loop() {
//read_Modbus();
  byte val1, val2, val3, val4, val5, val6;
  val1 = nitrogen();
  delay(250);
  Serial.print("SensorData: ");
  Serial.print(val1);
  
  if (!client.connected()) {
    reconnect();
  }
  client.publish("outTopic", "12");
  client.loop();
  delay(5000);
}

//////////////////////////////////////////////////////////////////////////////////////////

byte nitrogen() {
  digitalWrite(DE_RE_PIN, HIGH);
  //digitalWrite(RE, HIGH);
  delay(10);
  if (mod.write(nitro, sizeof(nitro)) == 8) {
    //mod.flush();  // wait for write complete
    digitalWrite(DE_RE_PIN, LOW);
    //digitalWrite(RE, LOW);
/*   for (byte i = 0; i < 19; i++) {
      //Serial.print(mod.read(),HEX);
      values[i] = mod.read();
      Serial.print(values[i], HEX);
      Serial.print("\t");
    }*/
    int in = 0;
    while(mod.available())
    {
      values[in] = mod.read();
      Serial.print(values[in], HEX);
      Serial.print("\t");
      in++;
    }
    Serial.println("");
  }
  return values[4];
}
//////////////////////////////////////////////////////////////////////
void saveParamCallback(){
  Serial.println("[CALLBACK] saveParamCallback fired");
  String server_temp = getParam("mqtt_server");
  String port_temp = getParam("mqtt_port");  
  server_temp.toCharArray(mqtt_server, server_temp.length() + 1);
  port_temp.toCharArray(mqtt_port, port_temp.length() + 1);
  Serial.print("PARAM mqtt_server = " + server_temp );
  Serial.println("PARAM mqtt_port = " +  port_temp);

}
/////////////////////////////////////////////////////////////////////////
String getParam(String name){
  //read parameter from server, for customhmtl input
  String value;
  if(name == "mqtt_server") value = custom_mqtt_server.getValue();
  else{   if(name =="mqtt_port") value = custom_mqtt_port.getValue();  }
  return value;
}
//////////////////////////////////////////////////////////////////
void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived on topic: ");
  Serial.println(topic);
  Serial.print("Message: ");
  char message[20];
  for (int i = 0; i < length; i++) {
    Serial.print((char)payload[i]);
    message[i]=(char)payload[i];
  }
  Serial.println(message);
  //byte index = 0;
  /*ptr = strtok(message, ",");  // delimiter
  while (ptr != NULL)
   {
      strings[index] = ptr;
      index++;
      ptr = strtok(NULL, ",");
   }
  for (int n = 0; n < index; n++)
   {
      Serial.print(n);
      Serial.print("  ");
      Serial.println(strings[n]);
   }*/
  
}
////////////////////////////////////////////////////////////////////////////
void reconnect() {
   int8_t ret;

  // Stop if already connected.
  if (client.connected()) {
    return;
  }

  Serial.print("Connecting to MQTT... ");

  uint8_t retries = 5;
  while (!client.connected()) { // connect will return 0 for connected
       if (client.connect("ESP32_clientID")) {
          Serial.println("connected");
          // Once connected, publish an announcement...
          client.publish("outTopic", "MotorDriver connected to MQTT");
          // ... and resubscribe
          client.subscribe("motor_velocities");
        }
        else {
          Serial.println("Retrying MQTT connection in 2 seconds...");
          delay(2000);  // wait 2 seconds
          retries--;
          if (retries == 0) {
            // basically die and wait for WDT to reset me
            //wm.resetSettings();
            break;
          }
        
        }
       
  }  
  if (!client.connected()) {
      Serial.println("Failed to connect MQTT - restarting ESP!");
      ESP.restart();
  }
  else {
      Serial.println("connected**");
  }
}
///////////////////////////////////////////////////////////////////////

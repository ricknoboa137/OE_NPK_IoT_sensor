#include <SoftwareSerial.h>
#include <ArduinoJson.h>
#include <WiFiManager.h> // https://github.com/tzapu/WiFiManager
#include <WiFi.h>
#include <PubSubClient.h>
#define TX_PIN 19
#define RX_PIN 18
#define DE_RE_PIN 4
#define LED_PIN 2


DynamicJsonDocument doc(1024); //Setup Json doc


SoftwareSerial mod(RX_PIN, TX_PIN);
char mqtt_server[40]= "192.168.0.174";
char mqtt_port[6] = "1883";
WiFiManager wm;
WiFiManagerParameter custom_mqtt_server("server", "mqtt server", mqtt_server, 40);
WiFiManagerParameter custom_mqtt_port("port", "mqtt port", mqtt_port, 6);
WiFiClient espClient;
PubSubClient client(espClient);

const byte nitro[] = { 0x01, 0x03, 0x00, 0x00, 0x00, 0x07, 0x04, 0x08 }; // Modify this array to change the request
byte values[11]; // to store reply from modbus sensor

float humidity, temperature, nitrog, phospho, potass, ph, conduct;
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
res = wm.autoConnect("NPK_Sensor_V1.1"); // password protected ap ,"password"
if(!res) {
    Serial.println("Failed to connect");}
    // ESP.restart();} 
else {
    //if you get here you have connected to the WiFi    
    Serial.println("connected...yeey :):):)");
    reconnect(); //connect MQTT    
  }
client.subscribe("inTopic");
Serial.println("\n\Setting Up Soil Sensor...\n");
}

uint16_t  val1, val2, val3, val4, val5, val6, val7, val8;
String jsonString;
char buffer[256];
//////////////////////////////////LOOP///////////////////////////////////////////
void loop() {
  
  if (GetValues()==0){
      humidity = float(val1)/10;
      temperature = float(val2)/10;
      conduct = float(val3)/10; 
      ph = float(val4)/10;
      nitrog = float(val5)/10;
      phospho = float(val6)/10;
      potass= float(val7)/10;
      doc["Humidity"] = humidity;
      doc["Temperature"] = temperature;
      doc["Conductivity"] = conduct;
      doc["PH"] = ph;
      doc["Nitrogen"] = nitrog;
      doc["Phosphorus"] = phospho;
      doc["Potassium"] = potass;
      // Serialize JSON document to a string
      
      serializeJson(doc, jsonString);
      serializeJson(doc, buffer);
  }
  // Print the JSON string to the serial monitor
  Serial.println(jsonString); 
  delay(250); 
  if (!client.connected()) {
    reconnect();
  }
  client.publish("NPKdata", buffer);
  client.loop();
  delay(5000);
}

//////////////////////////////////////////////////////////////////////////////////////////

int GetValues() {
  int error;
  digitalWrite(DE_RE_PIN, HIGH);
  //digitalWrite(RE, HIGH);
  delay(10);
  if (mod.write(nitro, sizeof(nitro)) == 8) {
    digitalWrite(DE_RE_PIN, LOW);
    int in = 0;
    while(mod.available())
    {
      values[in] = mod.read();
      //Serial.print(values[in], HEX);
      //Serial.print("\t");
      in++;
      
    } 
    if (in > 0){ error = 0;} // flag no error
    else { error= 1;}   // flag error in modbus comm
    Serial.println("");
    if (error==0)
    {
    val1 = (values[3] << 8) | values[4]; //Humidity
    val2 = (values[5] << 8) | values[6]; //temperature
    val3 = (values[7] << 8) | values[8]; //conductivity
    val4 = (values[9] << 8) | values[10]; //PH
    val5 = (values[11] << 8) | values[12]; // nitogene
    val6 = (values[13] << 8) | values[14]; //phosphorus
    val7 = (values[15] << 8) | values[16]; //potassium 
    }
    else 
    {
    val1 = 0; //Humidity
    val2 = 0; //temperature
    val3 = 0; //conductivity
    val4 = 0; //PH
    val5 = 0; // nitogene
    val6 = 0; //phosphorus
    val7 = 0;

    }
  }
  
  return error;
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
          client.publish("outTopic", "NPK Sensor connected to MQTT");
          // ... and resubscribe
          client.subscribe("NPKcommand");
        }
        else {
          Serial.println("Retrying MQTT connection in 2 seconds...");
          delay(2000);  // wait 2 seconds
          retries--;
          if (retries == 0) {
            // basically die and wait for WDT to reset me
            wm.resetSettings();
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

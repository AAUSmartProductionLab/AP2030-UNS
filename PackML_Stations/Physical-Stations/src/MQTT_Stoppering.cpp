#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "stoppering_station.h"
#include "PackMLStateMachine.h"

// Station-specific MQTT topics
const char *topic_pub_status = "AAU/Fibigerstræde/Building14/FillingLine/Stoppering/DATA/State";
const char *topic_sub_Stoppering_Cmd = "AAU/Fibigerstræde/Building14/FillingLine/Stoppering/CMD/Plunge";
const char *topic_pub_Stoppering_Data = "AAU/Fibigerstræde/Building14/FillingLine/Stoppering/DATA/Plunge";
const char *topic_pub_cycle_time = "AAU/Fibigerstræde/Building14/FillingLine/Stoppering/DATA/CycleTime";

// Station-specific data
String commandUuid;

// WiFi and MQTT clients
WiFiClient espClient;
PubSubClient client(espClient);

void callback(char *topic, byte *payload, unsigned int length);
unsigned long cycle_time_start = 0;
unsigned long cycle_time_end = 0;

// Derived PackML State Machine for Stoppering Station
class StopperingStateMachine : public PackMLStateMachine
{
public:
  StopperingStateMachine(const String &baseTopic, PubSubClient *mqttClient, WiFiClient *wifiClient)
      : PackMLStateMachine(baseTopic, mqttClient, wifiClient) {}

protected:
  void onResetting() override
  {
    Serial.println("Initializing Stoppering Station...");
    initWiFiAndMQTT();
    InitStoppering();
    initializeTime();
    Serial.println("Stoppering Station initialized");
  }
};

// PackML State Machine instance
StopperingStateMachine *stateMachine = nullptr;

// Global reconnect wrapper for use in station functions
void reconnect()
{
  if (stateMachine)
  {
    stateMachine->reconnect();
  }
}

void setup()
{
  Serial.begin(115200);

  stateMachine = new StopperingStateMachine("NN/Nybrovej/InnoLab/Stoppering", &client, &espClient);
  client.setCallback(callback);
  stateMachine->begin();

  // Occupy command handler for stoppering
  stateMachine->registerCommandHandler(
      topic_sub_Stoppering_Cmd,
      topic_pub_Stoppering_Data,
      [](PackMLStateMachine *sm, const JsonDocument &msg)
      {
        sm->executeCommand(msg, topic_pub_Stoppering_Data, StopperingRunning);
      },
      StopperingRunning);
}

void loop()
{
  if (!client.connected())
  {
    stateMachine->reconnect();
  }
  client.loop();

  if (stateMachine)
  {
    stateMachine->loop();
  }
}

void callback(char *topic, byte *payload, unsigned int length)
{
  String message;
  for (unsigned int i = 0; i < length; i++)
  {
    message += (char)payload[i];
  }

  // Parse JSON message
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, message);
  if (error)
  {
    Serial.print("JSON parse error: ");
    Serial.println(error.c_str());
    return;
  }

  // Extract and store commandUuid globally for use in station functions
  commandUuid = doc["Uuid"].as<String>();

  // Pass message to PackML state machine
  if (stateMachine)
  {
    stateMachine->handleMessage(String(topic), doc);
  }
}
#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "filling_station.h"
#include "PackMLStateMachine.h"

// Station-specific MQTT topics
const String topic_pub_status = "/DATA/State";
const String topic_sub_Filling_Cmd = "/CMD/Dispense";
const String topic_pub_Filling_Data = "/DATA/Dispense";
const String topic_sub_Needle_Cmd = "/CMD/Needle";
const String topic_pub_Needle_Data = "/DATA/Needle";
const String topic_sub_Tare_Cmd = "/CMD/Tare";
const String topic_pub_Tare_Data = "/DATA/Tare";
const String topic_pub_cycle_time = "/DATA/CycleTime";
const String topic_pub_weight = "/DATA/Weight";

// Station-specific data
double stationPosition[] = {0.660, 0.840};
String commandUuid;

// WiFi and MQTT clients
WiFiClient espClient;
PubSubClient client(espClient);

void callback(char *topic, byte *payload, unsigned int length);
unsigned long cycle_time_start = 0;
unsigned long cycle_time_end = 0;

// Helper function to send weight data
void sendWeight(double weight, const String &topic)
{
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo))
  {
    Serial.println("Error getting time");
    return;
  }

  char timestamp[30];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", &timeinfo);
  String isoTimestamp = String(timestamp) + ".000Z";
  
  JsonDocument doc;
  doc["Weight"] = weight;
  doc["TimeStamp"] = isoTimestamp;
  doc["Uuid"] = commandUuid;

  char output[256];
  serializeJson(doc, output);

  client.publish(topic.c_str(), output, true);
}

// Derived PackML State Machine for Filling Station
class FillingStateMachine : public PackMLStateMachine
{
public:
  FillingStateMachine(const String &baseTopic, PubSubClient *mqttClient, WiFiClient *wifiClient)
      : PackMLStateMachine(baseTopic, mqttClient, wifiClient) {}

protected:
  // Override onResetting to perform station initialization
  void onResetting() override
  {
    Serial.println("Initializing Filling Station...");
    initWiFiAndMQTT();
    InitFilling();
    initializeTime();
    Serial.println("Filling Station initialized");
  }
};

// PackML State Machine instance
FillingStateMachine *stateMachine = nullptr;

void setup()
{
  Serial.begin(115200);

  stateMachine = new FillingStateMachine("NN/Nybrovej/InnoLab/Filling", &client, &espClient);
  client.setCallback(callback);

  // Add additional command handlers for device primitives BEFORE begin()
  stateMachine->registerCommandHandler(
      topic_sub_Filling_Cmd,
      topic_pub_Filling_Data,
      [](PackMLStateMachine *sm, const JsonDocument &msg)
      {
        sm->executeCommand(msg, topic_pub_Filling_Data, FillingRunning);
      },
      FillingRunning);

  stateMachine->registerCommandHandler(
      topic_sub_Needle_Cmd,
      topic_pub_Needle_Data,
      [](PackMLStateMachine *sm, const JsonDocument &msg)
      {
        sm->executeCommand(msg, topic_pub_Needle_Data, Needle_Attachment);
      },
      Needle_Attachment);

  stateMachine->registerCommandHandler(
      topic_sub_Tare_Cmd,
      topic_pub_Tare_Data,
      [](PackMLStateMachine *sm, const JsonDocument &msg)
      {
        sm->executeCommand(msg, topic_pub_Tare_Data, TareScale);
      },
      TareScale);

  // Call begin() AFTER registering handlers
  stateMachine->begin();
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

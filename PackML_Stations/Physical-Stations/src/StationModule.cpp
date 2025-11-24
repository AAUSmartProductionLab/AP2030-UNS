#include "StationModule.h"

// Static member initialization
WiFiClient StationModule::espClient;
PubSubClient StationModule::client(espClient);
PackMLStateMachine *StationModule::stateMachine = nullptr;
String StationModule::commandUuid = "";

// BaseStateMachine implementation
StationModule::BaseStateMachine::BaseStateMachine(const String &baseTopic, PubSubClient *mqttClient, WiFiClient *wifiClient)
    : PackMLStateMachine(baseTopic, mqttClient, wifiClient)
{
}

void StationModule::BaseStateMachine::onResetting()
{
    Serial.println("Initializing Station...");
    initWiFiAndMQTT();
    initStationHardware();
    initializeTime();
    Serial.println("Station initialized");
}

// Common methods
void StationModule::initializeStation(const String &baseTopic, unsigned long baudRate)
{
    Serial.begin(baudRate);
}

void StationModule::loop()
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

void StationModule::mqttCallback(char *topic, byte *payload, unsigned int length)
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

    // Extract and store commandUuid
    if (doc["Uuid"].is<String>())
    {
        commandUuid = doc["Uuid"].as<String>();
    }

    // Pass message to PackML state machine
    if (stateMachine)
    {
        stateMachine->handleMessage(String(topic), doc);
    }
}

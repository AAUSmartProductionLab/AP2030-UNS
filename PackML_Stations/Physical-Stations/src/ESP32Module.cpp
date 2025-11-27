#include "ESP32Module.h"
#include "PackMLStateMachine.h"
#include <FS.h>

// Constructor
ESP32Module::ESP32Module()
    : mqttClient(),
      stateMachine(nullptr),
      commandUuid(""),
      config(),
      baseTopic(""),
      initialized(false),
      configFilePath("/config.json")
{
}

void ESP32Module::setup(const String &topic, const String &name, unsigned long baudRate)
{
    if (initialized)
    {
        Serial.println("ESP32Module already initialized");
        return;
    }

    Serial.begin(baudRate);
    baseTopic = topic;
    moduleName = name;

    initWiFi();
    initMQTT();
    initializeTime();
    publishDescriptionFromFile();

    initialized = true;
    Serial.println("=== ESP32 Module Initialized ===\n");
}

void ESP32Module::initWiFi()
{
    Serial.print("Connecting to WiFi: ");
    Serial.println(config.ssid);

    WiFi.begin(config.ssid, config.password);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20)
    {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED)
    {
        Serial.println("\nWiFi Connected!");
        Serial.print("IP Address: ");
        Serial.println(WiFi.localIP());
    }
    else
    {
        Serial.println("\nWiFi Connection Failed!");
    }
}

void ESP32Module::initMQTT()
{
    Serial.print("Setting up MQTT broker: ");
    Serial.print(config.mqttServer);
    Serial.print(":");
    Serial.println(config.mqttPort);

    // Configure AsyncMqttClient callbacks using lambda to capture 'this'
    mqttClient.onConnect([this](bool sessionPresent)
                         { this->onMqttConnect(sessionPresent); });
    mqttClient.onDisconnect([this](AsyncMqttClientDisconnectReason reason)
                            { this->onMqttDisconnect(reason); });
    mqttClient.onMessage([this](char *topic, char *payload, AsyncMqttClientMessageProperties properties, size_t len, size_t index, size_t total)
                         { this->onMqttMessage(topic, payload, properties, len, index, total); });

    // Set server and credentials
    mqttClient.setServer(config.mqttServer, config.mqttPort);

    // Connect to MQTT broker
    mqttClient.connect();

    Serial.println("MQTT Client configured and connecting...");
}

void ESP32Module::initializeTime()
{
    Serial.print("Synchronizing time with NTP");

    // Set Danish time with automatic daylight saving
    configTzTime("CET-1CEST,M3.5.0/02,M10.5.0/03", "pool.ntp.org", "time.nist.gov");

    struct tm timeinfo;
    for (int i = 0; i < 10; i++)
    {
        if (getLocalTime(&timeinfo))
        {
            Serial.println(" → Time synchronized!");
            char buffer[64];
            strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", &timeinfo);
            Serial.print("Current time: ");
            Serial.println(buffer);
            return;
        }
        Serial.print(".");
        delay(1000);
    }

    Serial.println("\n⚠️ Could not synchronize time from NTP server");
}

void ESP32Module::publishDescriptionFromFile()
{
    String content = readConfig(configFilePath);
    if (content.length() == 0)
    {
        Serial.println("No AAS Description found to publish");
        return;
    }

    Serial.print("Publishing AAS Description (");
    Serial.print(content.length());
    Serial.println(" bytes)");

    // Wait briefly to ensure MQTT connection is stable
    delay(500);

    String fullTopic = baseTopic + "/Registration/Request";

    // AsyncMqttClient can handle large payloads without QoS issues
    uint16_t packetId = mqttClient.publish(fullTopic.c_str(), 2, false, content.c_str(), content.length());

    if (packetId > 0)
    {
        Serial.println("Published Module AAS description to " + fullTopic);
    }
    else
    {
        Serial.println("Failed to publish AAS description");
    }
}

String ESP32Module::readConfig(const char *path)
{

    // Mount LittleFS to allow storing large JSON files persistently
    if (!LittleFS.begin())
    {
        Serial.println("LittleFS mount failed - attempting to format...");
        if (LittleFS.format() && LittleFS.begin())
        {
            Serial.println("LittleFS mounted after format");
        }
        else
        {
            Serial.println("LittleFS mount failed even after format");
            return String("");
        }
    }
    else
    {
        Serial.println("LittleFS mounted");
    }

    // Find AAS Description
    if (!LittleFS.exists(path))
    {
        Serial.println("Config file does not exist: " + String(path));
        return String("");
    }

    File file = LittleFS.open(path, FILE_READ);
    if (!file)
    {
        Serial.println("Failed to open config file for reading");
        return String("");
    }

    String content;
    content.reserve(file.size());
    while (file.available())
    {
        content += (char)file.read();
    }
    file.close();
    Serial.print("📖 Read config bytes: ");
    Serial.println(content.length());
    return content;
}

void ESP32Module::onMqttConnect(bool sessionPresent)
{
    Serial.println("MQTT Connected!");

    // Let state machine subscribe to its topics
    if (stateMachine)
    {
        stateMachine->subscribeToTopics();
        stateMachine->publishState();
    }
}

void ESP32Module::onMqttDisconnect(AsyncMqttClientDisconnectReason reason)
{
    Serial.println("MQTT Disconnected");
}

void ESP32Module::onMqttMessage(char *topic, char *payload, AsyncMqttClientMessageProperties properties, size_t len, size_t index, size_t total)
{
    // Debug: Print received message info
    Serial.print("📨 MQTT Message received on topic: ");
    Serial.println(topic);
    Serial.print("   Payload length: ");
    Serial.println(len);

    // Convert topic and payload to strings
    String topicStr = String(topic);
    String message;
    message.reserve(len);
    for (size_t i = 0; i < len; i++)
    {
        message += (char)payload[i];
    }

    Serial.print("   Payload: ");
    Serial.println(message);

    // Parse JSON message
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, message);

    if (error)
    {
        Serial.print("❌ JSON parse error: ");
        Serial.println(error.c_str());
        return;
    }

    // Extract and store command UUID
    if (doc["Uuid"].is<String>())
    {
        commandUuid = doc["Uuid"].as<String>();
        Serial.print("   UUID: ");
        Serial.println(commandUuid);
    }

    // Route message to PackML state machine
    if (stateMachine)
    {
        stateMachine->handleMessage(topicStr, doc);
    }
    else
    {
        Serial.println("⚠️  No state machine to handle message");
    }
}

AsyncMqttClient &ESP32Module::getMqttClient()
{
    return mqttClient;
}

String ESP32Module::getCommandUuid()
{
    return commandUuid;
}

void ESP32Module::setStateMachine(PackMLStateMachine *sm)
{
    stateMachine = sm;
}

#include "ESP32Module.h"
#include "PackMLStateMachine.h"

// Static member initialization
WiFiClient ESP32Module::espClient;
PubSubClient ESP32Module::client(espClient);
PackMLStateMachine *ESP32Module::stateMachine = nullptr;
String ESP32Module::commandUuid = "";
ESP32Module::WiFiMQTTConfig ESP32Module::config;
String ESP32Module::baseTopic = "";
bool ESP32Module::initialized = false;

void ESP32Module::begin(const String &topic, unsigned long baudRate)
{
    if (initialized)
    {
        Serial.println("ESP32Module already initialized");
        return;
    }

    Serial.begin(baudRate);
    Serial.println("\n=== Initializing ESP32 Module ===");

    baseTopic = topic;

    initWiFi();
    initMQTT();
    initializeTime();

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

    client.setServer(config.mqttServer, config.mqttPort);
    client.setCallback(mqttCallback);

    Serial.println("MQTT Client configured");
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

void ESP32Module::reconnect()
{
    if (!initialized)
    {
        return;
    }

    while (!client.connected())
    {
        Serial.print("Attempting MQTT connection...");

        String clientId = "ESP32Client-" + String(random(0xffff), HEX);

        if (client.connect(clientId.c_str()))
        {
            Serial.println(" connected!");

            // Let state machine subscribe to its topics
            if (stateMachine)
            {
                stateMachine->subscribeToTopics();
                stateMachine->publishState();
            }
        }
        else
        {
            Serial.print(" failed, rc=");
            Serial.print(client.state());
            Serial.println(" retrying in 5 seconds...");
            delay(5000);
        }
    }
}

void ESP32Module::loop()
{
    if (!initialized)
    {
        return;
    }

    // Maintain MQTT connection
    if (!client.connected())
    {
        reconnect();
    }
    client.loop();

    // Update state machine
    if (stateMachine)
    {
        stateMachine->loop();
    }
}

void ESP32Module::mqttCallback(char *topic, byte *payload, unsigned int length)
{
    // Convert payload to string
    String message;
    message.reserve(length);
    for (unsigned int i = 0; i < length; i++)
    {
        message += (char)payload[i];
    }

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
    }

    // Route message to PackML state machine
    if (stateMachine)
    {
        stateMachine->handleMessage(String(topic), doc);
    }
}

PubSubClient *ESP32Module::getMqttClient()
{
    return &client;
}

String ESP32Module::getCommandUuid()
{
    return commandUuid;
}

void ESP32Module::setStateMachine(PackMLStateMachine *sm)
{
    stateMachine = sm;
}

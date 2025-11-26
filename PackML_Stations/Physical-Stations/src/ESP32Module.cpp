#include "ESP32Module.h"
#include "PackMLStateMachine.h"
#include <FS.h>

// Constructor
ESP32Module::ESP32Module()
    : client(nullptr),
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

    // Configure MQTT client using older API structure
    esp_mqtt_client_config_t mqtt_cfg = {};

    // Build URI string that persists beyond this function
    static String mqtt_uri = String("mqtt://") + config.mqttServer + ":" + config.mqttPort;
    mqtt_cfg.uri = mqtt_uri.c_str();

    // Buffer settings for large payloads (60KB to handle 47KB config file with overhead)
    mqtt_cfg.buffer_size = 61440;     // 60KB receive buffer
    mqtt_cfg.out_buffer_size = 61440; // 60KB transmit buffer

    // Increase task stack for QoS 2 support (outbox memory comes from task stack)
    mqtt_cfg.task_stack = 16384; // 16KB stack (default is 6KB, need more for QoS 2 with large messages)

    // Create and configure client
    client = esp_mqtt_client_init(&mqtt_cfg);

    if (client == nullptr)
    {
        Serial.println("Failed to initialize MQTT client");
        return;
    }

    // Register event handler with 'this' pointer
    esp_mqtt_client_register_event(client, (esp_mqtt_event_id_t)ESP_EVENT_ANY_ID, mqttEventHandler, this);

    // Start the client
    esp_mqtt_client_start(client);

    Serial.println("MQTT Client configured and started");
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

    esp_mqtt_client_handle_t mqttClient = client;
    String fullTopic = baseTopic + "/Registration/Request";

    // With 60KB buffer, we can send the 47KB config in one message with QoS 0
    int msg_id = esp_mqtt_client_publish(mqttClient, fullTopic.c_str(), content.c_str(),
                                         content.length(), 0, 0);

    if (msg_id >= 0)
    {
        Serial.println("Published Module AAS description" + fullTopic);
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

void ESP32Module::mqttEventHandler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    // Recover instance pointer from handler_args
    ESP32Module *instance = static_cast<ESP32Module *>(handler_args);
    if (!instance)
        return;

    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;

    switch ((esp_mqtt_event_id_t)event_id)
    {
    case MQTT_EVENT_CONNECTED:
        Serial.println("MQTT Connected!");

        // Let state machine subscribe to its topics
        if (instance->stateMachine)
        {
            instance->stateMachine->subscribeToTopics();
            instance->stateMachine->publishState();
        }
        break;

    case MQTT_EVENT_DISCONNECTED:
        Serial.println("MQTT Disconnected");
        break;

    case MQTT_EVENT_SUBSCRIBED:
        Serial.print("Subscribed to topic:");
        Serial.println(event->topic);
        break;

    case MQTT_EVENT_UNSUBSCRIBED:
        Serial.print("Unsubscribed from topic:");
        Serial.println(event->topic);
        break;

    case MQTT_EVENT_PUBLISHED:
        Serial.print("Published message, msg_id=");
        Serial.println(event->msg_id);
        break;

    case MQTT_EVENT_DATA:
    {
        // Convert topic and payload to strings
        String topic = String(event->topic).substring(0, event->topic_len);
        String message;
        message.reserve(event->data_len);
        for (int i = 0; i < event->data_len; i++)
        {
            message += (char)event->data[i];
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

        // Extract and store command UUID
        if (doc["Uuid"].is<String>())
        {
            instance->commandUuid = doc["Uuid"].as<String>();
        }

        // Route message to PackML state machine
        if (instance->stateMachine)
        {
            instance->stateMachine->handleMessage(topic, doc);
        }
        break;
    }

    case MQTT_EVENT_ERROR:
        Serial.println("MQTT Error occurred");
        if (event->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT)
        {
            Serial.println("Transport error");
        }
        break;

    default:
        break;
    }
}

esp_mqtt_client_handle_t ESP32Module::getMqttClient()
{
    return client;
}

String ESP32Module::getCommandUuid()
{
    return commandUuid;
}

void ESP32Module::setStateMachine(PackMLStateMachine *sm)
{
    stateMachine = sm;
}

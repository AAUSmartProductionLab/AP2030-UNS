#include "ESP32Module.h"
#include "PackMLStateMachine.h"
#include <FS.h>

// Static member initialization
esp_mqtt_client_handle_t ESP32Module::client = nullptr;
PackMLStateMachine *ESP32Module::stateMachine = nullptr;
String ESP32Module::commandUuid = "";
ESP32Module::WiFiMQTTConfig ESP32Module::config;
String ESP32Module::baseTopic = "";
bool ESP32Module::initialized = false;
const char *ESP32Module::configFilePath = "/config.json";

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

    // Mount LittleFS to allow storing large JSON files persistently
    if (!LittleFS.begin())
    {
        Serial.println("⚠️ LittleFS mount failed - configuration file unavailable");
    }
    else
    {
        Serial.println("✔ LittleFS mounted");
    }

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

    // Configure MQTT client using older API structure
    esp_mqtt_client_config_t mqtt_cfg = {};
    
    // Build URI string that persists beyond this function
    static String mqtt_uri = String("mqtt://") + config.mqttServer + ":" + config.mqttPort;
    mqtt_cfg.uri = mqtt_uri.c_str();
    
    // Use MQTT v3.1.1 (v5 requires newer ESP-IDF)
    // mqtt_cfg.protocol_ver = MQTT_PROTOCOL_V_3_1_1;
    
    // Buffer settings for large payloads
    mqtt_cfg.buffer_size = 40960; // 40KB buffer for large JSON files
    mqtt_cfg.out_buffer_size = 40960;
    
    // Create and configure client
    client = esp_mqtt_client_init(&mqtt_cfg);
    
    if (client == nullptr)
    {
        Serial.println("❌ Failed to initialize MQTT client");
        return;
    }
    
    // Register event handler
    esp_mqtt_client_register_event(client, (esp_mqtt_event_id_t)ESP_EVENT_ANY_ID, mqttEventHandler, nullptr);
    
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

void ESP32Module::mqttEventHandler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
    
    switch ((esp_mqtt_event_id_t)event_id)
    {
        case MQTT_EVENT_CONNECTED:
            Serial.println("✔ MQTT Connected!");
            
            // Let state machine subscribe to its topics
            if (stateMachine)
            {
                stateMachine->subscribeToTopics();
                stateMachine->publishState();
            }
            break;
            
        case MQTT_EVENT_DISCONNECTED:
            Serial.println("⚠️ MQTT Disconnected");
            break;
            
        case MQTT_EVENT_SUBSCRIBED:
            Serial.print("📥 Subscribed to topic, msg_id=");
            Serial.println(event->msg_id);
            break;
            
        case MQTT_EVENT_UNSUBSCRIBED:
            Serial.print("📤 Unsubscribed from topic, msg_id=");
            Serial.println(event->msg_id);
            break;
            
        case MQTT_EVENT_PUBLISHED:
            Serial.print("📨 Published message, msg_id=");
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
                stateMachine->handleMessage(topic, doc);
            }
            break;
        }
            
        case MQTT_EVENT_ERROR:
            Serial.println("❌ MQTT Error occurred");
            if (event->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT)
            {
                Serial.println("  Transport error");
            }
            break;
            
        default:
            break;
    }
}

void ESP32Module::loop()
{
    if (!initialized)
    {
        return;
    }

    // esp-mqtt handles connection automatically in background
    // No need to call client.loop() or reconnect()

    // Update state machine
    if (stateMachine)
    {
        stateMachine->loop();
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

void ESP32Module::publishDescription(const String &moduleDescription)
{
    esp_mqtt_client_handle_t mqttClient = ESP32Module::getMqttClient();
    String fullTopic = baseTopic + "/Registration/Request";

    // Publish the description with QoS 1 and retain flag
    int msg_id = esp_mqtt_client_publish(mqttClient, fullTopic.c_str(), moduleDescription.c_str(), 
                                          moduleDescription.length(), 1, 1);

    if (msg_id >= 0)
    {
        Serial.println("📄 Published Module AAS description to: " + fullTopic);
    }
    else
    {
        Serial.println("❌ Failed to publish Module AAS description");
    }
}

void ESP32Module::publishDescriptionFromFile()
{
    String content = readConfig(configFilePath);
    if (content.length() == 0)
    {
        Serial.println("⚠️ No configuration JSON found to publish");
        return;
    }

    Serial.print("📦 Publishing configuration file (");
    Serial.print(content.length());
    Serial.println(" bytes)");

    esp_mqtt_client_handle_t mqttClient = ESP32Module::getMqttClient();
    String fullTopic = baseTopic + "/Registration/Request";
    
    // esp-mqtt can handle large payloads (40KB buffer configured)
    int msg_id = esp_mqtt_client_publish(mqttClient, fullTopic.c_str(), content.c_str(), 
                                          content.length(), 1, 1);
    
    if (msg_id >= 0)
    {
        Serial.println("📄 Published Module AAS description from file to: " + fullTopic);
    }
    else
    {
        Serial.println("❌ Failed to publish config from file");
    }
}

bool ESP32Module::saveConfig(const String &json, const char *path)
{
    if (!LittleFS.begin())
    {
        // Try to mount again in case not mounted earlier
        if (!LittleFS.begin())
        {
            Serial.println("⚠️ LittleFS mount failed - cannot save config");
            return false;
        }
    }

    File file = LittleFS.open(path, FILE_WRITE);
    if (!file)
    {
        Serial.println("❌ Failed to open config file for writing");
        return false;
    }

    size_t written = file.print(json);
    file.close();
    Serial.print("💾 Saved config bytes: ");
    Serial.println(written);
    return written > 0;
}

String ESP32Module::readConfig(const char *path)
{
    if (!LittleFS.begin())
    {
        if (!LittleFS.begin())
        {
            Serial.println("⚠️ LittleFS mount failed - cannot read config");
            return String("");
        }
    }

    if (!LittleFS.exists(path))
    {
        Serial.println("ℹ️ Config file does not exist: " + String(path));
        return String("");
    }

    File file = LittleFS.open(path, FILE_READ);
    if (!file)
    {
        Serial.println("❌ Failed to open config file for reading");
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

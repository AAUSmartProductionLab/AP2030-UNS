#ifndef ESP32_MODULE_H
#define ESP32_MODULE_H

#include <Arduino.h>
#include <WiFi.h>
#include <mqtt_client.h>
#include <ArduinoJson.h>
#include <LittleFS.h>

// Forward declaration
class PackMLStateMachine;

/**
 * @class ESP32Module
 * @brief Handles all hardware, WiFi, and MQTT functionality for ESP32-based stations
 *
 * This class encapsulates:
 * - WiFi connectivity management
 * - MQTT client setup and connection handling
 * - Time synchronization (NTP)
 * - MQTT message routing to PackML state machine
 * - Command UUID tracking for all operations
 */
class ESP32Module
{
public:
    /**
     * @brief Constructor - creates an uninitialized ESP32Module instance
     */
    ESP32Module();

    /**
     * @brief Initialize ESP32 module with WiFi, MQTT, and time sync
     * @param baseTopic MQTT base topic for the station
     * @param baudRate Serial baud rate (default 115200)
     */
    void setup(const String &baseTopic, const String &moduleName, unsigned long baudRate = 115200);

    /**
     * @brief Get the MQTT client instance
     * @return ESP-MQTT client handle for publishing messages
     */
    esp_mqtt_client_handle_t getMqttClient();

    /**
     * @brief Get the current command UUID
     * @return Current command UUID string
     */
    String getCommandUuid();

    /**
     * @brief Set the PackML state machine instance
     * @param sm Pointer to PackMLStateMachine
     */
    void setStateMachine(PackMLStateMachine *sm);
    /**
     * @brief Publish the stored configuration JSON (from filesystem) to MQTT
     */
    void publishDescriptionFromFile();

    /**
     * @brief Read configuration JSON from filesystem (LittleFS)
     * @param path Optional path (default: "/config.json")
     * @return The JSON string, or empty String if failed
     */
    String readConfig(const char *path = "/config.json");

private:
    // WiFi and MQTT Configuration
    struct WiFiMQTTConfig
    {
        const char *ssid = "AP2030";
        const char *password = "NovoNordisk";
        const char *mqttServer = "192.168.0.104";
        int mqttPort = 1883;
    };

    // Instance members
    esp_mqtt_client_handle_t client;
    PackMLStateMachine *stateMachine;
    String commandUuid;
    WiFiMQTTConfig config;
    String baseTopic;
    String moduleName;
    bool initialized;
    const char *configFilePath;

    /**
     * @brief Initialize WiFi connection
     */
    void initWiFi();

    /**
     * @brief Initialize MQTT client
     */
    void initMQTT();

    /**
     * @brief Initialize NTP time synchronization
     */
    void initializeTime();

    /**
     * @brief MQTT event handler - handles connection, disconnection, and messages
     */
    static void mqttEventHandler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data);
};

#endif // ESP32_MODULE_H

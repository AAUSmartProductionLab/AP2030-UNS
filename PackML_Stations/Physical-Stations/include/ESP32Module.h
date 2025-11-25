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
     * @brief Initialize ESP32 module with WiFi, MQTT, and time sync
     * @param baseTopic MQTT base topic for the station
     * @param baudRate Serial baud rate (default 115200)
     */
    static void begin(const String &baseTopic, unsigned long baudRate = 115200);

    /**
     * @brief Main loop - handles MQTT connection and state machine updates
     * Must be called continuously in Arduino loop()
     */
    static void loop();

    /**
     * @brief Get the MQTT client instance
     * @return ESP-MQTT client handle for publishing messages
     */
    static esp_mqtt_client_handle_t getMqttClient();

    /**
     * @brief Get the current command UUID
     * @return Current command UUID string
     */
    static String getCommandUuid();

    /**
     * @brief Set the PackML state machine instance
     * @param sm Pointer to PackMLStateMachine
     */
    static void setStateMachine(PackMLStateMachine *sm);
    static void publishDescription(const String &moduleDescription);
    /**
     * @brief Publish the stored configuration JSON (from filesystem) to MQTT
     */
    static void publishDescriptionFromFile();

    /**
     * @brief Save configuration JSON to filesystem (LittleFS)
     * @param json The JSON string to save
     * @param path Optional path (default: "/config.json")
     * @return true if saved successfully
     */
    static bool saveConfig(const String &json, const char *path = "/config.json");

    /**
     * @brief Read configuration JSON from filesystem (LittleFS)
     * @param path Optional path (default: "/config.json")
     * @return The JSON string, or empty String if failed
     */
    static String readConfig(const char *path = "/config.json");

private:
    // WiFi and MQTT Configuration
    struct WiFiMQTTConfig
    {
        const char *ssid = "AP2030";
        const char *password = "NovoNordisk";
        const char *mqttServer = "192.168.0.104";
        int mqttPort = 1883;
    };

    // Static members
    static esp_mqtt_client_handle_t client;
    static PackMLStateMachine *stateMachine;
    static String commandUuid;
    static WiFiMQTTConfig config;
    static String baseTopic;
    static bool initialized;
    static const char *configFilePath;

    /**
     * @brief Initialize WiFi connection
     */
    static void initWiFi();

    /**
     * @brief Initialize MQTT client
     */
    static void initMQTT();

    /**
     * @brief Initialize NTP time synchronization
     */
    static void initializeTime();

    /**
     * @brief MQTT event handler - handles connection, disconnection, and messages
     */
    static void mqttEventHandler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data);
};

#endif // ESP32_MODULE_H

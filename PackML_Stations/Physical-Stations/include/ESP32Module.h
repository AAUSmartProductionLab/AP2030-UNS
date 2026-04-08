#ifndef ESP32_MODULE_H
#define ESP32_MODULE_H

#include <Arduino.h>
#include <WiFi.h>
#include <AsyncMqttClient.h>
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
     * @return AsyncMqttClient reference for publishing messages
     */
    AsyncMqttClient &getMqttClient();

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
     * @brief Publish the stored YAML configuration (from filesystem) to MQTT
     * 
     * Sends the YAML config to the Registration/Config topic where the
     * Registration Service will generate the full AAS description.
     */
    void publishDescriptionFromFile();

    /**
     * @brief Read configuration YAML from filesystem (LittleFS)
     * @param path Optional path (default: "/config.yaml")
     * @return The YAML string, or empty String if failed
     */
    String readConfig(const char *path = "/config.yaml");

private:
    // WiFi and MQTT Configuration
    // These values are injected at build time from the root .env file
    // See copy_config.py pre-build script
    struct WiFiMQTTConfig
    {
#ifdef WIFI_SSID_ENV
        const char *ssid = WIFI_SSID_ENV;
#else
        const char *ssid = "AAU5G_CISCO";  // Fallback default
#endif
#ifdef WIFI_PASSWORD_ENV
        const char *password = WIFI_PASSWORD_ENV;
#else
        const char *password = "5G_rules";  // Fallback default
#endif
#ifdef MQTT_SERVER
        const char *mqttServer = MQTT_SERVER;
#else
        const char *mqttServer = "192.168.100.123";  // Fallback default
#endif
#ifdef MQTT_PORT_NUM
        int mqttPort = MQTT_PORT_NUM;
#else
        int mqttPort = 1883;  // Fallback default
#endif
    };

    // Instance members
    AsyncMqttClient mqttClient;
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
     * @brief MQTT event handlers
     */
    void onMqttConnect(bool sessionPresent);
    void onMqttDisconnect(AsyncMqttClientDisconnectReason reason);
    void onMqttMessage(char *topic, char *payload, AsyncMqttClientMessageProperties properties, size_t len, size_t index, size_t total);
};

#endif // ESP32_MODULE_H

#ifndef ESP32_MODULE_H
#define ESP32_MODULE_H

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

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
     * @return Pointer to PubSubClient for publishing messages
     */
    static PubSubClient *getMqttClient();

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
    static WiFiClient espClient;
    static PubSubClient client;
    static PackMLStateMachine *stateMachine;
    static String commandUuid;
    static WiFiMQTTConfig config;
    static String baseTopic;
    static bool initialized;

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
     * @brief Reconnect to MQTT broker if connection is lost
     */
    static void reconnect();

    /**
     * @brief MQTT message callback - handles command UUID extraction and routing
     */
    static void mqttCallback(char *topic, byte *payload, unsigned int length);
};

#endif // ESP32_MODULE_H

#ifndef STATION_MODULE_H
#define STATION_MODULE_H

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "PackMLStateMachine.h"

/**
 * @class StationModule
 * @brief Base class for all station modules providing common MQTT and PackML functionality
 *
 * This abstract base class encapsulates common functionality shared by all stations:
 * - MQTT client management
 * - WiFi connectivity
 * - PackML state machine integration
 * - Message callback handling
 * - Command UUID tracking
 */
class StationModule
{
public:
    /**
     * @brief Main loop - must be called continuously in Arduino loop()
     */
    static void loop();

protected:
    // Common static members
    static WiFiClient espClient;
    static PubSubClient client;
    static PackMLStateMachine *stateMachine;
    static String commandUuid;

    /**
     * @brief Initialize the station module
     * @param baseTopic MQTT base topic for the station
     * @param baudRate Serial baud rate (default 115200)
     */
    static void initializeStation(const String &baseTopic, unsigned long baudRate = 115200);

    /**
     * @brief Register all station-specific command handlers
     * Must be implemented by derived classes
     */
    static void registerCommands() {}

    /**
     * @brief Initialize station-specific hardware
     * Must be implemented by derived classes
     */
    static void initHardware() {}

    /**
     * @brief MQTT message callback - handles command UUID extraction and message routing
     */
    static void mqttCallback(char *topic, byte *payload, unsigned int length);

    /**
     * @brief Base PackML state machine with common initialization
     */
    class BaseStateMachine : public PackMLStateMachine
    {
    public:
        BaseStateMachine(const String &baseTopic, PubSubClient *mqttClient, WiFiClient *wifiClient);

    protected:
        void onResetting() override;

        /**
         * @brief Station-specific hardware initialization hook
         * Called during the resetting state
         */
        virtual void initStationHardware() = 0;
    };
};

#endif // STATION_MODULE_H

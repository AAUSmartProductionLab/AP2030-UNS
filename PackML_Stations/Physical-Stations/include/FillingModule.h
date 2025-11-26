#ifndef FILLING_MODULE_H
#define FILLING_MODULE_H

#include <Arduino.h>
#include <ArduinoJson.h>

// Forward declarations
class ESP32Module;
class PackMLStateMachine;

/**
 * @class FillingModule
 * @brief Filling station hardware control and device primitives
 *
 * This module handles:
 * - Motor control for needle movement
 * - Limit switch reading
 * - Device primitives (filling, needle attachment, tare)
 * - Weight measurement and publishing
 */
class FillingModule
{
public:
    /**
     * @brief Initialize and start the filling module
     * @param esp32Module Pointer to initialized ESP32Module instance
     * Must be called once in Arduino setup()
     */
    static void setup(ESP32Module *esp32Module);

    /**
     * @brief Initialize hardware pins and move to home position
     */
    static void initHardware();

private:
    // Pin definitions
    static const int BUTTON_PIN_BOTTOM = 36;
    static const int BUTTON_PIN_TOP = 39;
    static const int PIN_ENB = 19;
    static const int PIN_IN3 = 18;
    static const int PIN_IN4 = 5;

    // Motor speed settings
    static const int MOTOR_SPEED = 140;
    static const int MOTOR_SPEED_BOOST = 50;
    static const unsigned long MOTION_TIMEOUT = 8000; // 8 seconds

    // Custom MQTT action/data topics
    static const String TOPIC_SUB_FILLING_CMD;
    static const String TOPIC_PUB_FILLING_DATA;
    static const String TOPIC_SUB_NEEDLE_CMD;
    static const String TOPIC_PUB_NEEDLE_DATA;
    static const String TOPIC_SUB_TARE_CMD;
    static const String TOPIC_PUB_TARE_DATA;
    static const String TOPIC_PUB_WEIGHT;

    /**
     * @brief Execute complete filling cycle
     */
    static void runFillingCycle();

    /**
     * @brief Move needle down to attachment position
     */
    static void attachNeedle();

    /**
     * @brief Tare the scale
     */
    static void tareScale();

    /**
     * @brief Move needle to top position
     */
    static void moveToTop();

    /**
     * @brief Move needle to bottom position
     */
    static void moveToBottom();

    /**
     * @brief Stop motor movement
     */
    static void stopMotor();

    /**
     * @brief Publish weight data via MQTT
     * @param weight Weight value to publish
     */
    static void publishWeight(double weight);

    /**
     * @brief Wait for button press with timeout
     * @param buttonPin Pin number of button to monitor
     * @param timeoutMs Timeout in milliseconds
     * @return true if button pressed, false if timeout
     */
    static bool waitForButton(int buttonPin, unsigned long timeoutMs);

    // Static members
    static ESP32Module *esp32Module;
    static PackMLStateMachine *stateMachine;
};

#endif // FILLING_MODULE_H
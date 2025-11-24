#ifndef STOPPERING_MODULE_H
#define STOPPERING_MODULE_H

#include <Arduino.h>
#include <ESP32Servo.h>
#include "StationModule.h"

/**
 * @class StopperingModule
 * @brief Stoppering station module with hardware control and device primitives
 *
 * This module encapsulates stoppering station-specific functionality:
 * - Servo motor, DC motor, and linear actuator control
 * - Sensor reading
 * - Device primitives (plunging operation)
 */
class StopperingModule : public StationModule
{
public:
    /**
     * @brief Initialize and start the stoppering module
     * Must be called once in Arduino setup()
     */
    static void begin();

    /**
     * @brief Main loop - must be called continuously in Arduino loop()
     */
    static void loop();

private:
    // Pin definitions
    static const int SERVO_PIN = 2;
    static const int BUTTON_PIN = 4;

    // DC Motor pins
    static const int DC_ENB = 41;
    static const int DC_IN3 = 39;
    static const int DC_IN4 = 40;

    // Linear Actuator pins
    static const int LA_ENA = 18;
    static const int LA_IN1 = 17;
    static const int LA_IN2 = 16;

    // PWM configuration
    static const int LA_PWM_CHANNEL = 3;
    static const int LA_PWM_FREQ = 1000;
    static const int LA_PWM_RES = 8;
    static const int DC_PWM_CHANNEL = 5;
    static const int DC_PWM_FREQ = 1000;
    static const int DC_PWM_RES = 8;

    // MQTT topics
    static const String TOPIC_PUB_STATUS;
    static const String TOPIC_SUB_STOPPERING_CMD;
    static const String TOPIC_PUB_STOPPERING_DATA;
    static const String TOPIC_PUB_CYCLE_TIME;

    // Station-specific members
    static Servo servo;

    /**
     * @brief Initialize all hardware pins
     */
    static void initHardware();

    /**
     * @brief Initialize servo motor to home position
     */
    static void initServo();

    /**
     * @brief Initialize linear actuator to home position
     */
    static void initLinearActuator();

    /**
     * @brief Initialize DC motor to home position
     */
    static void initDCMotor();

    /**
     * @brief Execute complete stoppering cycle
     */
    static void runStopperingCycle();

    /**
     * @brief Move linear actuator down and up
     */
    static void runLinearActuator();

    /**
     * @brief Move servo from inner to outer position
     */
    static void runServo();

    /**
     * @brief Move DC motor down until limit switch
     */
    static void moveDCDown();

    /**
     * @brief Move DC motor up for clearance
     */
    static void moveDCUp();

    /**
     * @brief Custom PackML state machine with stoppering-specific initialization
     */
    class StopperingStateMachine : public BaseStateMachine
    {
    public:
        StopperingStateMachine(const String &baseTopic, PubSubClient *mqttClient, WiFiClient *wifiClient);

    protected:
        void initStationHardware() override;
    };
};

#endif // STOPPERING_MODULE_H

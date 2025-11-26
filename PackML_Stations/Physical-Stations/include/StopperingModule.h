#ifndef STOPPERING_MODULE_H
#define STOPPERING_MODULE_H

#include <Arduino.h>
#include <ESP32Servo.h>

// Forward declarations
class ESP32Module;
class PackMLStateMachine;

/**
 * @class StopperingModule
 * @brief Stoppering station hardware control and device primitives
 *
 * This module handles:
 * - Servo motor control
 * - DC motor control
 * - Linear actuator control
 * - Limit switch reading
 * - Plunging operation sequence
 */
class StopperingModule
{
public:
    /**
     * @brief Initialize and start the stoppering module
     * @param esp32Module Pointer to initialized ESP32Module instance
     * Must be called once in Arduino setup()
     */
    static void setup(ESP32Module *esp32Module);

    /**
     * @brief Initialize all hardware pins
     */
    static void initHardware();

private:
    // Pin definitions - Servo
    static const int SERVO_PIN = 2;

    // Pin definitions - Limit Switch
    static const int BUTTON_PIN = 4;

    // Pin definitions - DC Motor
    static const int DC_ENB = 41;
    static const int DC_IN3 = 39;
    static const int DC_IN4 = 40;

    // Pin definitions - Linear Actuator
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

    // Motor timing settings
    static const unsigned long SERVO_MOVE_TIME = 2000;
    static const unsigned long LA_DOWN_TIME = 10000;
    static const unsigned long LA_UP_TIME = 6500;
    static const unsigned long DC_UP_TIME = 2000;
    static const unsigned long DC_INIT_UP_TIME = 1500;
    static const unsigned long MOTION_TIMEOUT = 10000; // 10 seconds

    // Custom MQTT action/data topics
    static const String TOPIC_SUB_STOPPERING_CMD;
    static const String TOPIC_PUB_STOPPERING_DATA;
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
     * @return true if successful, false if timeout
     */
    static bool moveDCDown();

    /**
     * @brief Move DC motor up for clearance
     */
    static void moveDCUp();

    /**
     * @brief Stop DC motor
     */
    static void stopDCMotor();

    /**
     * @brief Stop linear actuator
     */
    static void stopLinearActuator();

    /**
     * @brief Wait for limit switch with timeout
     * @param buttonPin Pin number of button to monitor
     * @param timeoutMs Timeout in milliseconds
     * @return true if button pressed, false if timeout
     */
    static bool waitForButton(int buttonPin, unsigned long timeoutMs);

    // Static members
    static ESP32Module *esp32Module;
    static Servo servo;
    static PackMLStateMachine *stateMachine;
};

#endif // STOPPERING_MODULE_H

#include "StopperingModule.h"
#include "ESP32Module.h"
#include "PackMLStateMachine.h"
#include <esp_task_wdt.h>

// Static member initialization
ESP32Module *StopperingModule::esp32Module = nullptr;
Servo StopperingModule::servo;
PackMLStateMachine *StopperingModule::stateMachine = nullptr;

// MQTT topic definitions

const String baseTopic = "NN/Nybrovej/InnoLab";
const String moduleName = "Stoppering";
const String StopperingModule::TOPIC_SUB_STOPPERING_CMD = "/CMD/Stopper";
const String StopperingModule::TOPIC_PUB_STOPPERING_DATA = "/DATA/Stopper";

void StopperingModule::setup(ESP32Module *moduleInstance)
{
    esp32Module = moduleInstance;

    // Initialize ESP32 (WiFi, MQTT, Time)
    esp32Module->setup(baseTopic, moduleName);

    // Initialize stoppering hardware
    initHardware();

    // Create PackML state machine with MQTT client from ESP32Module
    stateMachine = new PackMLStateMachine(baseTopic, moduleName, &(esp32Module->getMqttClient()));

    // Register state machine with ESP32Module for message routing
    esp32Module->setStateMachine(stateMachine);

    // Register command handler for device primitive
    stateMachine->registerCommandHandler(
        TOPIC_SUB_STOPPERING_CMD,
        TOPIC_PUB_STOPPERING_DATA,
        [](PackMLStateMachine *sm, const JsonDocument &msg)
        {
            sm->executeCommand(msg, TOPIC_PUB_STOPPERING_DATA, runStopperingCycle);
        });
    stateMachine->subscribeToTopics();
    stateMachine->publishState();
    Serial.println("Stoppering Module ready!\n");
}

void StopperingModule::initHardware()
{
    // Configure servo motor
    servo.attach(SERVO_PIN);
    delay(100);

    // Configure linear actuator pins
    pinMode(LA_ENA, OUTPUT);
    pinMode(LA_IN1, OUTPUT);
    pinMode(LA_IN2, OUTPUT);
    delay(10);

    // Setup PWM for linear actuator
    ledcSetup(LA_PWM_CHANNEL, LA_PWM_FREQ, LA_PWM_RES);
    ledcAttachPin(LA_ENA, LA_PWM_CHANNEL);
    ledcWrite(LA_PWM_CHANNEL, 200);
    delay(10);

    // Configure limit switch pin
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    delay(10);

    // Configure DC motor pins
    pinMode(DC_ENB, OUTPUT);
    pinMode(DC_IN3, OUTPUT);
    pinMode(DC_IN4, OUTPUT);
    delay(10);

    // Setup PWM for DC motor
    ledcSetup(DC_PWM_CHANNEL, DC_PWM_FREQ, DC_PWM_RES);
    ledcAttachPin(DC_ENB, DC_PWM_CHANNEL);
    ledcWrite(DC_PWM_CHANNEL, 200);
    delay(10);

    // Initialize all subsystems to home positions
    initServo();
    delay(15);

    initLinearActuator();
    delay(15);

    initDCMotor();
    delay(15);

    Serial.println("Stoppering hardware initialized");
}

void StopperingModule::initServo()
{
    Serial.println("Initializing servo to home position");

    // Move to intermediate position
    servo.write(90);
    delay(SERVO_MOVE_TIME);

    // Move to home position (outer)
    servo.write(120);
    delay(SERVO_MOVE_TIME);
}

void StopperingModule::initLinearActuator()
{
    Serial.println("Initializing linear actuator to home position");

    // Move actuator up to home position
    digitalWrite(LA_IN1, HIGH);
    digitalWrite(LA_IN2, LOW);
    delay(LA_UP_TIME);

    // Stop actuator
    stopLinearActuator();
}

void StopperingModule::initDCMotor()
{
    Serial.println("Initializing DC motor to home position");

    // Move down until limit switch
    digitalWrite(DC_IN3, LOW);
    digitalWrite(DC_IN4, HIGH);

    if (!waitForButton(BUTTON_PIN, MOTION_TIMEOUT))
    {
        Serial.println("Motion Error: DC motor initialization timeout");
    }

    // Move up for clearance
    digitalWrite(DC_IN3, HIGH);
    digitalWrite(DC_IN4, LOW);
    delay(DC_INIT_UP_TIME);

    // Stop motor
    stopDCMotor();
}

bool StopperingModule::runStopperingCycle()
{
    Serial.println("Starting stoppering cycle");

    // Position DC motor down to working position
    if (!moveDCDown())
    {
        Serial.println("Error: Failed to move DC motor down");
        return false;
    }
    delay(100);

    // Move servo to position stopper
    runServo();
    delay(100);

    // Execute plunging operation
    runLinearActuator();
    delay(100);

    // Return DC motor to home position
    moveDCUp();
    delay(500);

    Serial.println("Stoppering cycle completed successfully");
    return true;
}

void StopperingModule::runLinearActuator()
{
    Serial.println("Running linear actuator cycle");

    // Move actuator down to push plunger
    digitalWrite(LA_IN1, LOW);
    digitalWrite(LA_IN2, HIGH);
    delay(LA_DOWN_TIME);

    // Move actuator back up to home position
    digitalWrite(LA_IN1, HIGH);
    digitalWrite(LA_IN2, LOW);
    delay(LA_UP_TIME);

    // Stop actuator
    stopLinearActuator();
}

void StopperingModule::runServo()
{
    Serial.println("Moving servo to position stopper");

    // Move from outer position to inner position
    servo.write(0);
    delay(SERVO_MOVE_TIME);

    // Return to home position (outer)
    servo.write(120);
    delay(SERVO_MOVE_TIME);
}

bool StopperingModule::moveDCDown()
{
    Serial.println("Moving DC motor down to working position");

    // Run piston down until it hits the limit switch
    digitalWrite(DC_IN3, LOW);
    digitalWrite(DC_IN4, HIGH);

    if (!waitForButton(BUTTON_PIN, MOTION_TIMEOUT))
    {
        Serial.println("Motion Error: Move DC down timeout");
        stopDCMotor();
        return false;
    }

    // Stop motor
    stopDCMotor();
    return true;
}

void StopperingModule::moveDCUp()
{
    Serial.println("Moving DC motor up to home position");

    // Run piston up for clearance
    digitalWrite(DC_IN3, HIGH);
    digitalWrite(DC_IN4, LOW);
    delay(DC_UP_TIME);

    // Stop motor
    stopDCMotor();
}

void StopperingModule::stopDCMotor()
{
    digitalWrite(DC_IN3, LOW);
    digitalWrite(DC_IN4, LOW);
}

void StopperingModule::stopLinearActuator()
{
    digitalWrite(LA_IN1, LOW);
    digitalWrite(LA_IN2, LOW);
    delay(10);
}

bool StopperingModule::waitForButton(int buttonPin, unsigned long timeoutMs)
{
    unsigned long startTime = millis();

    // Wait for button to be pressed (HIGH when pressed due to logic)
    while (digitalRead(buttonPin) == LOW)
    {
        if (millis() - startTime >= timeoutMs)
        {
            return false; // Timeout
        }
        delay(5); // Sample the endswitch at 200Hz
    }

    return true; // Button pressed
}

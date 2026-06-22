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
const String StopperingModule::TOPIC_SUB_STOPPERING_CMD = "/CMD/Stoppering";
const String StopperingModule::TOPIC_PUB_STOPPERING_DATA = "/DATA/Stoppering";
const String StopperingModule::TOPIC_PUB_VC_CMD = "/VC/CMD/Stoppering";
const String StopperingModule::TOPIC_SUB_VC_RESPONSE = "/VC/Response/Stoppering";
volatile bool StopperingModule::vcResponseReceived = false;
volatile bool StopperingModule::buttonPressed = false;

void StopperingModule::setup(ESP32Module *moduleInstance)
{
    esp32Module = moduleInstance;

    // Initialize ESP32 (WiFi, MQTT, Time)
    esp32Module->setup(baseTopic, moduleName);

    // Wait for Serial to be ready
    delay(500);
    Serial.println("\n=== Starting Stoppering Module Setup ===");
    Serial.println("Initializing hardware...");
    Serial.flush(); // Ensure message is sent

    // Initialize stoppering hardware
    initHardware();

    Serial.println("Hardware initialization complete");
    Serial.flush();

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

    // Register VC (Visual Components) response handler for visualization mirroring
    {
        String vcResponseTopic = esp32Module->getBaseTopic() + "/" + esp32Module->getModuleName() + TOPIC_SUB_VC_RESPONSE;
        esp32Module->registerTopicHandler(vcResponseTopic, onVcResponse);
        esp32Module->subscribeTopic(vcResponseTopic, 2);
    }

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
    Serial.flush();

    // Move to intermediate position
    servo.write(90);
    delay(SERVO_MOVE_TIME);

    // Move to home position (outer)
    servo.write(120);
    delay(SERVO_MOVE_TIME);

    // Keep servo attached during initialization to avoid PWM conflicts
    // It will be detached after first use in runServo()
    Serial.println("Servo initialized to home position");
    Serial.flush();
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

    // Notify Visual Components to start visualization (parallel with physical movement)
    vcResponseReceived = false;
    publishVcCommand(esp32Module->getCommandUuid());

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

    // Wait for VC animation to complete before reporting SUCCESS
    {
        unsigned long startWait = millis();
        while (!vcResponseReceived && (millis() - startWait < VC_RESPONSE_TIMEOUT))
        {
            delay(50);
        }
        if (vcResponseReceived)
        {
            Serial.println("✅ VC animation completed");
        }
        else
        {
            Serial.println("⚠️  VC response timeout — physical operation completed, proceeding anyway");
        }
    }

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
    Serial.flush();

    // Re-attach servo if needed (in case it was detached)
    if (!servo.attached())
    {
        servo.attach(SERVO_PIN);
        delay(100);
    }

    // Move from outer position to inner position
    servo.write(1);
    delay(SERVO_MOVE_TIME);

    // Return to home position (outer)
    servo.write(121);
    delay(SERVO_MOVE_TIME);

    // Detach servo to prevent vibration
    servo.detach();
    Serial.println("Servo cycle complete, servo detached");
    Serial.flush();
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

// ---------------------------------------------------------------------------
// Interrupt Service Routine for limit switch
// ---------------------------------------------------------------------------

void IRAM_ATTR StopperingModule::buttonISR()
{
    buttonPressed = true;
}

// ---------------------------------------------------------------------------
// Interrupt-driven button wait (replaces tight-loop polling)
// ---------------------------------------------------------------------------

bool StopperingModule::waitForButton(int buttonPin, unsigned long timeoutMs)
{
    if (buttonPin != BUTTON_PIN)
    {
        Serial.print("  ⚠️  waitForButton: unknown pin ");
        Serial.println(buttonPin);
        return false;
    }

    buttonPressed = false;

    Serial.print("  Waiting for button on pin ");
    Serial.print(buttonPin);
    Serial.print(" (interrupt-driven, timeout ");
    Serial.print(timeoutMs);
    Serial.println("ms)");

    attachInterrupt(digitalPinToInterrupt(buttonPin), buttonISR, FALLING);

    unsigned long startTime = millis();
    while (!buttonPressed && (millis() - startTime < timeoutMs))
    {
        delay(10);  // yield CPU to WiFi / MQTT / FreeRTOS tasks
    }

    detachInterrupt(digitalPinToInterrupt(buttonPin));

    if (buttonPressed)
    {
        Serial.print("  Button pressed after ");
        Serial.print(millis() - startTime);
        Serial.println(" ms");
        return true;
    }
    else
    {
        Serial.println("  Button wait TIMEOUT");
        return false;
    }
}

void StopperingModule::publishVcCommand(const String &uuid)
{
    AsyncMqttClient &client = esp32Module->getMqttClient();
    String fullTopic = esp32Module->getBaseTopic() + "/" + esp32Module->getModuleName() + TOPIC_PUB_VC_CMD;

    JsonDocument doc;
    doc["Command"] = "StartStoppering";
    doc["Uuid"] = uuid;

    char output[256];
    size_t len = serializeJson(doc, output);
    client.publish(fullTopic.c_str(), 2, true, output, len);

    Serial.print("📺 Published VC command to ");
    Serial.println(fullTopic);
}

void StopperingModule::onVcResponse(const String &topic, const JsonDocument &msg)
{
    Serial.print("📺 VC Response on ");
    Serial.print(topic);
    Serial.print(": ");
    if (msg["State"].is<String>())
    {
        Serial.print("State=");
        Serial.print(msg["State"].as<String>());
    }
    if (msg["Uuid"].is<String>())
    {
        Serial.print(" Uuid=");
        Serial.print(msg["Uuid"].as<String>());
    }
    Serial.println();

    // Signal that VC has finished its animation
    vcResponseReceived = true;
}

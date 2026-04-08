#include "FillingModule.h"
#include "ESP32Module.h"
#include "PackMLStateMachine.h"
#include <esp_task_wdt.h>

// MQTT topic definitions
const String baseTopic = "NN/Nybrovej/InnoLab";
const String moduleName = "Dispensing";
const String FillingModule::TOPIC_SUB_FILLING_CMD = "/CMD/Dispensing";
const String FillingModule::TOPIC_PUB_FILLING_DATA = "/DATA/Dispensing";
const String FillingModule::TOPIC_SUB_NEEDLE_CMD = "/CMD/Needle";
const String FillingModule::TOPIC_PUB_NEEDLE_DATA = "/DATA/Needle";
const String FillingModule::TOPIC_SUB_TARE_CMD = "/CMD/Tare";
const String FillingModule::TOPIC_PUB_TARE_DATA = "/DATA/Tare";
const String FillingModule::TOPIC_PUB_WEIGHT = "/DATA/Weight";

// Static member initialization
ESP32Module *FillingModule::esp32Module = nullptr;
PackMLStateMachine *FillingModule::stateMachine = nullptr;

void FillingModule::setup(ESP32Module *moduleInstance)
{
    esp32Module = moduleInstance;

    // Initialize ESP32 (WiFi, MQTT, Time) first to get valid MQTT client
    esp32Module->setup(baseTopic, moduleName);

    // Initialize filling hardware
    initHardware();

    // Create PackML state machine with MQTT client from ESP32Module
    stateMachine = new PackMLStateMachine(baseTopic, moduleName, &(esp32Module->getMqttClient()));

    // Register state machine with ESP32Module for message routing
    esp32Module->setStateMachine(stateMachine);

    // Register command handlers for device primitives
    stateMachine->registerCommandHandler(
        TOPIC_SUB_FILLING_CMD,
        TOPIC_PUB_FILLING_DATA,
        [](PackMLStateMachine *sm, const JsonDocument &msg)
        {
            sm->executeCommand(msg, TOPIC_PUB_FILLING_DATA, runFillingCycle);
        });

    stateMachine->registerCommandHandler(
        TOPIC_SUB_NEEDLE_CMD,
        TOPIC_PUB_NEEDLE_DATA,
        [](PackMLStateMachine *sm, const JsonDocument &msg)
        {
            sm->executeCommand(msg, TOPIC_PUB_NEEDLE_DATA, attachNeedle);
        });

    stateMachine->registerCommandHandler(
        TOPIC_SUB_TARE_CMD,
        TOPIC_PUB_TARE_DATA,
        [](PackMLStateMachine *sm, const JsonDocument &msg)
        {
            sm->executeCommand(msg, TOPIC_PUB_TARE_DATA, tareScale);
        });

    // Subscribe to MQTT topics now that state machine is fully configured
    stateMachine->subscribeToTopics();
    stateMachine->publishState();

    Serial.println("Filling Module ready!\n");
}

// Hardware control methods
void FillingModule::initHardware()
{
    // Configure motor control pins
    pinMode(PIN_ENB, OUTPUT);
    pinMode(PIN_IN3, OUTPUT);
    pinMode(PIN_IN4, OUTPUT);

    // Configure sensor pins
    pinMode(BUTTON_PIN_BOTTOM, INPUT_PULLUP);
    pinMode(BUTTON_PIN_TOP, INPUT_PULLUP);

    // Initialize motor to stopped state
    analogWrite(PIN_ENB, 0);

    // Move to top (initial) position
    moveToTop();

    Serial.println("Filling hardware initialized");
}

bool FillingModule::moveToTop()
{
    Serial.println("Moving to top position");
    Serial.print("  Top button state at start: ");
    Serial.println(digitalRead(BUTTON_PIN_TOP) == HIGH ? "HIGH (Pressed)" : "LOW (pressed)");

    // Move up with boost
    digitalWrite(PIN_IN3, HIGH);
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENB, MOTOR_SPEED + MOTOR_SPEED_BOOST);

    delay(200);
    analogWrite(PIN_ENB, MOTOR_SPEED);

    // Wait for top button
    bool success = waitForButton(BUTTON_PIN_TOP, MOTION_TIMEOUT);
    if (!success)
    {
        Serial.println("Motion Error: Move to top timeout");
    }

    // Brief reverse with boost to stop smoothly
    analogWrite(PIN_ENB, MOTOR_SPEED + MOTOR_SPEED_BOOST);
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    delay(100);
    analogWrite(PIN_ENB, MOTOR_SPEED);
    // Stop motor
    stopMotor();

    return success;
}

bool FillingModule::moveToBottom()
{
    Serial.println("Moving to bottom position");
    Serial.print("  Bottom button state at start: ");
    Serial.println(digitalRead(BUTTON_PIN_BOTTOM) == HIGH ? "HIGH (not pressed)" : "LOW (pressed)");

    // Move down with boost
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    analogWrite(PIN_ENB, MOTOR_SPEED + MOTOR_SPEED_BOOST);

    delay(200);
    analogWrite(PIN_ENB, MOTOR_SPEED);

    // Wait for bottom button
    bool success = waitForButton(BUTTON_PIN_BOTTOM, MOTION_TIMEOUT);
    if (!success)
    {
        Serial.println("Motion Error: Move to bottom timeout");
    }

    digitalWrite(PIN_IN3, HIGH);
    digitalWrite(PIN_IN4, LOW);
    delay(100);
    // Stop motor
    stopMotor();

    return success;
}

void FillingModule::stopMotor()
{
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENB, 0);
}

bool FillingModule::waitForButton(int buttonPin, unsigned long timeoutMs)
{
    unsigned long startTime = millis();
    Serial.print("  Waiting for button on pin ");
    Serial.print(buttonPin);
    Serial.print(", current state: ");
    Serial.println(digitalRead(buttonPin) == 0 ? "Not pressed" : "Pressed");

    // Button will read HIGH when physically pressed
    while (digitalRead(buttonPin) == LOW)
    {
        if (millis() - startTime >= timeoutMs)
        {
            Serial.println("  Button wait TIMEOUT");
            return false; // Timeout
        }
        //delay(5); // Sample the endswitch at 200Hz
    }

    Serial.print("  Button pressed after ");
    Serial.print(millis() - startTime);
    Serial.println(" ms");
    return true; // Button pressed
}

bool FillingModule::runFillingCycle()
{
    Serial.println("Starting filling cycle");

    // Move down to fill position
    if (!moveToBottom())
    {
        Serial.println("Filling cycle failed: Motion error during move to bottom");
        return false;
    }

    // Wait at bottom (simulating filling)
    delay(1000);

    // Move back up to stop position
    if (!moveToTop())
    {
        Serial.println("Filling cycle failed: Motion error during move to top");
        return false;
    }

    // Generate and publish random weight (1.8 - 2.2 g)
    long weightInt = random(1800, 2200);
    float weight = weightInt / 1000.0;
    publishWeight(weight);

    Serial.println("Filling cycle completed successfully");
    return true;
}

void FillingModule::attachNeedle()
{
    Serial.println("Attaching needle");

    // Move down to attachment position
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    analogWrite(PIN_ENB, MOTOR_SPEED);

    if (!waitForButton(BUTTON_PIN_BOTTOM, MOTION_TIMEOUT))
    {
        Serial.println("Motion Error: Needle attachment timeout");
    }

    // Brief reverse to stop smoothly
    digitalWrite(PIN_IN3, HIGH);
    digitalWrite(PIN_IN4, LOW);
    delay(100);

    // Stop motor
    stopMotor();

    Serial.println("Needle attached");
}

void FillingModule::tareScale()
{
    Serial.println("Taring scale");

    // Simulate tare operation
    delay(2000);

    // Publish zero weight
    publishWeight(0.0);

    Serial.println("Scale tared");
}

void FillingModule::publishWeight(double weight)
{
    AsyncMqttClient &client = esp32Module->getMqttClient();
    String commandUuid = esp32Module->getCommandUuid();

    struct tm timeinfo;
    if (!getLocalTime(&timeinfo))
    {
        Serial.println("⚠️ Error getting time for weight publication");
        return;
    }

    // Format timestamp as ISO 8601
    char timestamp[30];
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", &timeinfo);
    String isoTimestamp = String(timestamp) + ".000Z";

    // Create JSON document
    JsonDocument doc;
    doc["Weight"] = weight;
    doc["TimeStamp"] = isoTimestamp;
    doc["Uuid"] = commandUuid;

    // Serialize and publish
    char output[256];
    size_t len = serializeJson(doc, output);

    String fullTopic = baseTopic + "/" + moduleName + TOPIC_PUB_WEIGHT;
    client.publish(fullTopic.c_str(), 2, true, output, len);

    Serial.print("⚖️  Published weight: ");
    Serial.print(weight);
    Serial.println(" g");
}

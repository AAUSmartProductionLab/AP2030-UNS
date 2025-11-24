#include "FillingModule.h"
#include "ESP32Module.h"
#include "PackMLStateMachine.h"

// MQTT topic definitions
const String FillingModule::TOPIC_PUB_STATUS = "/DATA/State";
const String FillingModule::TOPIC_SUB_FILLING_CMD = "/CMD/Dispense";
const String FillingModule::TOPIC_PUB_FILLING_DATA = "/DATA/Dispense";
const String FillingModule::TOPIC_SUB_NEEDLE_CMD = "/CMD/Needle";
const String FillingModule::TOPIC_PUB_NEEDLE_DATA = "/DATA/Needle";
const String FillingModule::TOPIC_SUB_TARE_CMD = "/CMD/Tare";
const String FillingModule::TOPIC_PUB_TARE_DATA = "/DATA/Tare";
const String FillingModule::TOPIC_PUB_WEIGHT = "/DATA/Weight";

// Static member initialization
PackMLStateMachine *FillingModule::stateMachine = nullptr;

void FillingModule::begin()
{
    const String baseTopic = "NN/Nybrovej/InnoLab/Filling";

    // Initialize ESP32 (WiFi, MQTT, Time)
    ESP32Module::begin(baseTopic);

    // Initialize filling hardware
    initHardware();

    // Create PackML state machine with MQTT client from ESP32Module
    stateMachine = new PackMLStateMachine(baseTopic, ESP32Module::getMqttClient());

    // Register state machine with ESP32Module for message routing
    ESP32Module::setStateMachine(stateMachine);

    // Register command handlers for device primitives
    stateMachine->registerCommandHandler(
        TOPIC_SUB_FILLING_CMD,
        TOPIC_PUB_FILLING_DATA,
        [](PackMLStateMachine *sm, const JsonDocument &msg)
        {
            sm->executeCommand(msg, TOPIC_PUB_FILLING_DATA, runFillingCycle);
        },
        runFillingCycle);

    stateMachine->registerCommandHandler(
        TOPIC_SUB_NEEDLE_CMD,
        TOPIC_PUB_NEEDLE_DATA,
        [](PackMLStateMachine *sm, const JsonDocument &msg)
        {
            sm->executeCommand(msg, TOPIC_PUB_NEEDLE_DATA, attachNeedle);
        },
        attachNeedle);

    stateMachine->registerCommandHandler(
        TOPIC_SUB_TARE_CMD,
        TOPIC_PUB_TARE_DATA,
        [](PackMLStateMachine *sm, const JsonDocument &msg)
        {
            sm->executeCommand(msg, TOPIC_PUB_TARE_DATA, tareScale);
        },
        tareScale);

    // Start the state machine
    stateMachine->begin();

    Serial.println("🎯 Filling Module ready!\n");
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

void FillingModule::runFillingCycle()
{
    Serial.println("Starting filling cycle");

    // Move down to fill position
    moveToBottom();

    // Wait at bottom (simulating filling)
    delay(1000);

    // Move back up to stop position
    moveToTop();

    // Generate and publish random weight (1.8 - 2.2 g)
    long weightInt = random(1800, 2200);
    float weight = weightInt / 1000.0;
    publishWeight(weight);

    Serial.println("Filling cycle completed");
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

void FillingModule::moveToTop()
{
    Serial.println("Moving to top position");

    // Move up with boost
    digitalWrite(PIN_IN3, HIGH);
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENB, MOTOR_SPEED + MOTOR_SPEED_BOOST);

    delay(200);
    analogWrite(PIN_ENB, MOTOR_SPEED);

    // Wait for top button
    if (!waitForButton(BUTTON_PIN_TOP, MOTION_TIMEOUT))
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
}

void FillingModule::moveToBottom()
{
    Serial.println("Moving to bottom position");

    // Move down with boost
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    analogWrite(PIN_ENB, MOTOR_SPEED + MOTOR_SPEED_BOOST);

    delay(200);
    analogWrite(PIN_ENB, MOTOR_SPEED);

    // Wait for bottom button
    if (!waitForButton(BUTTON_PIN_BOTTOM, MOTION_TIMEOUT))
    {
        Serial.println("Motion Error: Move to bottom timeout");
    }

    // Brief reverse to stop smoothly
    digitalWrite(PIN_IN3, HIGH);
    digitalWrite(PIN_IN4, LOW);
    delay(100);

    // Stop motor
    stopMotor();
}

void FillingModule::stopMotor()
{
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENB, 0);
}

void FillingModule::publishWeight(double weight)
{
    PubSubClient *client = ESP32Module::getMqttClient();
    String commandUuid = ESP32Module::getCommandUuid();

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
    serializeJson(doc, output);

    String fullTopic = "NN/Nybrovej/InnoLab/Filling" + TOPIC_PUB_WEIGHT;
    client->publish(fullTopic.c_str(), output, true);

    Serial.print("⚖️  Published weight: ");
    Serial.print(weight);
    Serial.println(" g");
}

bool FillingModule::waitForButton(int buttonPin, unsigned long timeoutMs)
{
    unsigned long startTime = millis();

    // Wait for button to be pressed (LOW when using INPUT_PULLUP)
    while (digitalRead(buttonPin) == HIGH)
    {
        if (millis() - startTime >= timeoutMs)
        {
            return false; // Timeout
        }
        delay(10); // Small delay to avoid tight loop
    }

    return true; // Button pressed
}

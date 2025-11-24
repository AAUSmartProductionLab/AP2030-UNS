#include "StopperingModule.h"

// Static member initialization
Servo StopperingModule::servo;

// MQTT topic definitions
const String StopperingModule::TOPIC_PUB_STATUS = "/DATA/State";
const String StopperingModule::TOPIC_SUB_STOPPERING_CMD = "/CMD/Plunge";
const String StopperingModule::TOPIC_PUB_STOPPERING_DATA = "/DATA/Plunge";
const String StopperingModule::TOPIC_PUB_CYCLE_TIME = "/DATA/CycleTime";

// StopperingStateMachine implementation
StopperingModule::StopperingStateMachine::StopperingStateMachine(const String &baseTopic, PubSubClient *mqttClient, WiFiClient *wifiClient)
    : BaseStateMachine(baseTopic, mqttClient, wifiClient)
{
}

void StopperingModule::StopperingStateMachine::initStationHardware()
{
    StopperingModule::initHardware();
}

// Public interface
void StopperingModule::begin()
{
    initializeStation("NN/Nybrovej/InnoLab/Stoppering");

    stateMachine = new StopperingStateMachine("NN/Nybrovej/InnoLab/Stoppering", &client, &espClient);
    client.setCallback(mqttCallback);

    // Register command handler for stoppering operation
    stateMachine->registerCommandHandler(
        TOPIC_SUB_STOPPERING_CMD,
        TOPIC_PUB_STOPPERING_DATA,
        [](PackMLStateMachine *sm, const JsonDocument &msg)
        {
            sm->executeCommand(msg, TOPIC_PUB_STOPPERING_DATA, runStopperingCycle);
        },
        runStopperingCycle);

    stateMachine->begin();
}

// Hardware control methods
void StopperingModule::initHardware()
{
    // Configure servo
    servo.attach(SERVO_PIN);
    delay(100);

    // Configure linear actuator pins
    pinMode(LA_ENA, OUTPUT);
    pinMode(LA_IN1, OUTPUT);
    pinMode(LA_IN2, OUTPUT);
    delay(10);

    ledcSetup(LA_PWM_CHANNEL, LA_PWM_FREQ, LA_PWM_RES);
    ledcAttachPin(LA_ENA, LA_PWM_CHANNEL);
    ledcWrite(LA_PWM_CHANNEL, 200);
    delay(10);

    // Configure button pin
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    delay(10);

    // Configure DC motor pins
    pinMode(DC_ENB, OUTPUT);
    pinMode(DC_IN3, OUTPUT);
    pinMode(DC_IN4, OUTPUT);
    delay(10);

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
    servo.write(90);
    delay(2000);
    servo.write(120);
    delay(2000);
}

void StopperingModule::initLinearActuator()
{
    digitalWrite(LA_IN1, HIGH);
    digitalWrite(LA_IN2, LOW);
    delay(6500);

    digitalWrite(LA_IN1, LOW);
    digitalWrite(LA_IN2, LOW);
    delay(10);
}

void StopperingModule::initDCMotor()
{
    digitalWrite(DC_IN3, LOW);
    digitalWrite(DC_IN4, HIGH);

    while (digitalRead(BUTTON_PIN) == LOW)
    {
        // Wait for limit switch
    }

    digitalWrite(DC_IN3, HIGH);
    digitalWrite(DC_IN4, LOW);
    delay(1500);

    digitalWrite(DC_IN3, LOW);
    digitalWrite(DC_IN4, LOW);
}

void StopperingModule::runStopperingCycle()
{
    Serial.println("Starting stoppering cycle");

    moveDCDown();
    delay(100);

    runServo();
    delay(100);

    runLinearActuator();
    delay(100);

    moveDCUp();
    delay(500);

    // Reconnect if needed after long delays
    if (!client.connected())
    {
        stateMachine->reconnect();
    }

    Serial.println("Stoppering cycle completed");
}

void StopperingModule::runLinearActuator()
{
    // Move actuator down to push plunger
    digitalWrite(LA_IN1, LOW);
    digitalWrite(LA_IN2, HIGH);
    delay(10000); // Extra time to let gravity help push the plunger

    // Move actuator back up
    digitalWrite(LA_IN1, HIGH);
    digitalWrite(LA_IN2, LOW);
    delay(6500);
}

void StopperingModule::runServo()
{
    // Move from inner position to outer position
    servo.write(0);
    delay(2000);

    servo.write(120);
    delay(2000);
}

void StopperingModule::moveDCDown()
{
    // Run piston down until it hits the limit switch
    digitalWrite(DC_IN3, LOW);
    digitalWrite(DC_IN4, HIGH);

    while (digitalRead(BUTTON_PIN) == LOW)
    {
        // Wait for limit switch
    }

    digitalWrite(DC_IN3, LOW);
    digitalWrite(DC_IN4, LOW);
}

void StopperingModule::moveDCUp()
{
    // Run piston up for clearance
    digitalWrite(DC_IN3, HIGH);
    digitalWrite(DC_IN4, LOW);
    delay(2000);

    digitalWrite(DC_IN3, LOW);
    digitalWrite(DC_IN4, LOW);
}

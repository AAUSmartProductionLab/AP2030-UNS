#ifndef STOPPERIN_STATION_H
#define STOPPERIN_STATION_H

#include <ESP32Servo.h>
#include <Arduino.h>
#include <PubSubClient.h>

extern PubSubClient client;

#define servoPWM 2

#define buttonPin 4

#define DC_ENB 41
#define DC_IN3 39
#define DC_IN4 40

#define LA_ENA 18
#define LA_IN1 17
#define LA_IN2 16

#define LA_PWM_CHANNEL 3 // Choose an unused channel (0–15)
#define LA_PWM_FREQ 1000 // 1 kHz is good for motor PWM
#define LA_PWM_RES 8     // 8-bit resolution: values from 0–255

#define DC_PWM_CHANNEL 5
#define DC_PWM_FREQ 1000
#define DC_PWM_RES 8

Servo myservo;

void initPins()
{

  myservo.attach(servoPWM);
  delay(100);

  pinMode(LA_ENA, OUTPUT);
  pinMode(LA_IN1, OUTPUT);
  pinMode(LA_IN2, OUTPUT);
  delay(10);

  ledcSetup(LA_PWM_CHANNEL, LA_PWM_FREQ, LA_PWM_RES); // Configure PWM channel
  ledcAttachPin(LA_ENA, LA_PWM_CHANNEL);              // Attach pin to channel

  ledcWrite(LA_PWM_CHANNEL, 200); // Set speed (0–255)
  delay(10);

  pinMode(buttonPin, INPUT_PULLUP); // Enable internal pull-up resistor
  delay(10);

  // Setting the pin modes for the DC motor controller pins
  pinMode(DC_ENB, OUTPUT);
  pinMode(DC_IN3, OUTPUT);
  pinMode(DC_IN4, OUTPUT);
  delay(10);

  ledcSetup(DC_PWM_CHANNEL, DC_PWM_FREQ, DC_PWM_RES); // Configure PWM channel
  ledcAttachPin(DC_ENB, DC_PWM_CHANNEL);              // Attach pin to channel

  ledcWrite(DC_PWM_CHANNEL, 200);
  delay(10);
}

void initServo()
{
  myservo.write(90);
  delay(2000);
  myservo.write(120);
  delay(2000);
}

void initLA()
{
  digitalWrite(LA_IN1, HIGH);
  digitalWrite(LA_IN2, LOW);
  delay(6500);

  digitalWrite(LA_IN1, LOW);
  digitalWrite(LA_IN2, LOW);
  delay(10);
}

void initDC()
{
  digitalWrite(DC_IN3, LOW);
  digitalWrite(DC_IN4, HIGH);

  while (digitalRead(buttonPin) == LOW)
  {
  }

  digitalWrite(DC_IN3, HIGH);
  digitalWrite(DC_IN4, LOW);
  delay(1500);

  digitalWrite(DC_IN3, LOW);
  digitalWrite(DC_IN4, LOW);
}

void InitStoppering()
{
  initPins();
  delay(15);

  initServo();
  delay(15);

  initLA();
  delay(15);

  initDC();
  delay(15);

  delay(1000);
}

void runLA()
{
  // First we run the actuator down to push a plunger
  digitalWrite(LA_IN1, LOW);
  digitalWrite(LA_IN2, HIGH);
  delay(10000); // This could be less, however we found that sometimes it helps when it has more time to let gravity push the plunger

  // Then we move it back up again
  digitalWrite(LA_IN1, HIGH);
  digitalWrite(LA_IN2, LOW);
  delay(6500);
}

void runServo()
{
  // Simply going from the inner position to the outer position
  myservo.write(0);
  delay(2000);

  myservo.write(120);
  delay(2000);
}

void DCDown()
{ // Simply running the piston down until it hits the limit switch
  digitalWrite(DC_IN3, LOW);
  digitalWrite(DC_IN4, HIGH);

  while (digitalRead(buttonPin) == LOW)
  {
  }

  digitalWrite(DC_IN3, LOW);
  digitalWrite(DC_IN4, LOW);
}

void DCUp()
{ // Simply running the piston up for 2 seconds to ensure it has clearance
  digitalWrite(DC_IN3, HIGH);
  digitalWrite(DC_IN4, LOW);
  delay(2000);

  digitalWrite(DC_IN3, LOW);
  digitalWrite(DC_IN4, LOW);
}

void StopperingRunning()
{ // This is the full execution
  SendMQTTMessage(commandUuid, "Executing", topic_pub_status);
  DCDown();
  delay(100);

  runServo();
  delay(100);

  runLA();
  delay(100);

  DCUp();
  delay(500);
  reconnect(); // Had some problems with it disconnecting after these longer delays, so we just make sure to reconnect
  SendMQTTMessage(commandUuid, "Idle", topic_pub_status);
}

#endif
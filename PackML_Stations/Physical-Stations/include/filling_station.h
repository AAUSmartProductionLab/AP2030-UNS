#ifndef FILLING_STATION_H
#define FILLING_STATION_H

#include <Arduino.h>
#include <PubSubClient.h>

extern PubSubClient client;
extern const String topic_pub_weight;
extern void sendWeight(double weight, const String &topic);

#define BUTTON_PIN_BOTTOM 36
#define BUTTON_PIN_TOP 39

#define enB 19
#define in3 18
#define in4 5

int speed = 140;

unsigned long startTime;

void FillingStop()
{
  digitalWrite(in3, HIGH);
  digitalWrite(in4, LOW);
  analogWrite(enB, speed + 50);
  startTime = millis();
  delay(200);
  analogWrite(enB, speed);

  while (digitalRead(BUTTON_PIN_TOP) == 0)
  {
    if (millis() - startTime >= 8000)
    {
      Serial.println("Motion Error Up");
      break;
    }
  }
  analogWrite(enB, speed + 50);
  digitalWrite(in3, LOW);
  digitalWrite(in4, HIGH);
  delay(100);
  analogWrite(enB, speed);
  digitalWrite(in3, LOW);
  digitalWrite(in4, LOW);
  analogWrite(enB, 0);

  // Publish a random weight
  //  Generate a number between 25000 and 26000
  long weight_int = random(25000, 26000); // 25000 inclusive, 26000 exclusive

  // Convert to float with three decimal places
  float weight_float = weight_int / 1000.0;

  sendWeight(weight_float, topic_pub_weight);
}

void FillingRunning()
{
  digitalWrite(in3, LOW);
  digitalWrite(in4, HIGH);
  analogWrite(enB, speed + 50);
  startTime = millis();
  delay(200);
  analogWrite(enB, speed);

  while (digitalRead(BUTTON_PIN_BOTTOM) == 0)
  {
    if (millis() - startTime >= 8000)
    {
      Serial.println("Motion Error Down");
      break;
    }
  }

  digitalWrite(in3, HIGH);
  digitalWrite(in4, LOW);
  delay(100);
  digitalWrite(in3, LOW);
  digitalWrite(in4, LOW);
  delay(1000);

  FillingStop();
}

void InitFilling()
{
  pinMode(enB, OUTPUT);
  pinMode(in3, OUTPUT);
  pinMode(in4, OUTPUT);
  pinMode(BUTTON_PIN_BOTTOM, INPUT_PULLUP);
  pinMode(BUTTON_PIN_TOP, INPUT_PULLUP);

  analogWrite(enB, 0);
  FillingStop();
}

void Needle_Attachment()
{
  digitalWrite(in3, LOW);
  digitalWrite(in4, HIGH);
  analogWrite(enB, speed);
  startTime = millis();

  while (digitalRead(BUTTON_PIN_BOTTOM) == 0)
  {
    if (millis() - startTime >= 8000)
    {
      Serial.println("Motion Error down");
      break;
    }
  }

  digitalWrite(in3, HIGH);
  digitalWrite(in4, LOW);
  delay(100);

  digitalWrite(in3, LOW);
  digitalWrite(in4, LOW);
  analogWrite(enB, 0);
}

void TareScale()
{
  // Simulate tare operation by waiting briefly then publishing weight of 0
  delay(2000);
  sendWeight(0.0, topic_pub_weight);
}

#endif
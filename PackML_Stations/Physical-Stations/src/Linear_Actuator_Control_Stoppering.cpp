#include <Arduino.h>

#define DC_ENB 18
#define DC_IN3 17
#define DC_IN4 16

int speed = 140; // Example speed value for analogWrite

void setup()
{
  // Setting the pin modes for the DC motor controller pins
  pinMode(DC_ENB, OUTPUT);
  pinMode(DC_IN3, OUTPUT);
  pinMode(DC_IN4, OUTPUT);

  Serial.begin(9600); // Initialize serial communication
  delay(100);         // Delay for good measure

  // Starting the DC motor movement
  digitalWrite(DC_IN3, LOW);
  digitalWrite(DC_IN4, LOW);
  analogWrite(DC_ENB, speed);
  delay(1000);
  Serial.println("Write 'd' or 'u' followed by a number to move the actuator down or up for a number of milliseconds");
  Serial.println("Example could be 'u1000' to make the piston go up for 1 second (1000 milliseconds)");
}

void loop()
{
  if (Serial.available() > 0)
  {
    char command = Serial.read(); // Read the command character

    if (command == 'u' || command == 'd')
    {
      while (Serial.available() == 0)
        ; // Wait for the number to be available

      int duration = Serial.parseInt(); // Read the duration in milliseconds

      // Perform action based on command ('u' for up, 'd' for down)
      if (command == 'u')
      {
        digitalWrite(DC_IN3, HIGH);
        digitalWrite(DC_IN4, LOW);
      }
      else if (command == 'd')
      {
        digitalWrite(DC_IN3, LOW);
        digitalWrite(DC_IN4, HIGH);
      }

      // Wait for the specified duration
      delay(duration);

      // Stop the motor after the duration
      digitalWrite(DC_IN3, LOW);
      digitalWrite(DC_IN4, LOW);
    }
  }
}

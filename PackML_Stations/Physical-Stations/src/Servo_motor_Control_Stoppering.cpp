#include <ESP32Servo.h>

Servo myservo;

int currentAngle = 180;         // Start at mid position
int targetAngle = 180;          // Target position (user-defined)
const int moveDelay = 0;      // Delay in ms between steps (lower = faster)

void setup() {
  Serial.begin(115200);
  myservo.attach(2);          // Attach to GPIO 18
  myservo.write(targetAngle); // Move to initial position
  Serial.println("Enter angle (0 to 180):");
}

void loop() {
  // Check for new serial input
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    int angle = input.toInt();
    if (angle >= 0 && angle <= 180) {
      targetAngle = angle;
      Serial.print("Moving to angle: ");
      Serial.println(targetAngle);
    } else {
      Serial.println("Invalid input. Enter a number between 0 and 180.");
    }
  }

  // Smooth motion toward targetAngle
  if (currentAngle < targetAngle) {
    currentAngle++;
    myservo.write(currentAngle);
    delay(moveDelay);
  } else if (currentAngle > targetAngle) {
    currentAngle--;
    myservo.write(currentAngle);
    delay(moveDelay);
  }
}

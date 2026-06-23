#include <Arduino.h>
#include "ESP32Module.h"

#ifdef FILLING_STATION
#include "FillingModule.h"
#endif

#ifdef STOPPERING_STATION
#include "StopperingModule.h"
#endif

// Create ESP32Module instance
ESP32Module esp32Module;

void setup()
{
    // Initialize Serial first and wait for USB to be ready (ESP32-S3 USB CDC)
    Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
    Serial.setTxTimeoutMs(0); // Never block on USB CDC TX when no host connected
#endif
    delay(2000); // Give USB serial time to initialize
    Serial.println("\n\n=== ESP32 Starting ===");
    if (Serial)
    {
        Serial.flush();
    }

#ifdef FILLING_STATION
    FillingModule::setup(&esp32Module);
#endif

#ifdef STOPPERING_STATION
    StopperingModule::setup(&esp32Module);
#endif

    Serial.println("=== Setup Complete ===\n");
    if (Serial)
    {
        Serial.flush();
    }
}

void loop()
{
    // Event-driven architecture - all processing handled by MQTT callbacks
}

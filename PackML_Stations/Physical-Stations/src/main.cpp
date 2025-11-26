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
#ifdef FILLING_STATION
    FillingModule::setup(&esp32Module);
#endif

#ifdef STOPPERING_STATION
    StopperingModule::setup(&esp32Module);
#endif
}

void loop()
{
    // Event-driven architecture - all processing handled by MQTT callbacks
}

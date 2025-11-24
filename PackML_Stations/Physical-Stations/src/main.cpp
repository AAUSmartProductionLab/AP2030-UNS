#include <Arduino.h>
#include "ESP32Module.h"

#ifdef FILLING_STATION
#include "FillingModule.h"
#endif

#ifdef STOPPERING_STATION
#include "StopperingModule.h"
#endif

void setup()
{
#ifdef FILLING_STATION
    FillingModule::begin();
#endif

#ifdef STOPPERING_STATION
    StopperingModule::begin();
#endif
}

void loop()
{
    ESP32Module::loop();
}

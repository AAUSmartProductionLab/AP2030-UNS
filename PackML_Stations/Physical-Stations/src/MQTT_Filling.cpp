#include <Arduino.h>
#include "wifi_mqtt_setup_filling.h"
#include "filling_station.h"

void callback(char *topic, byte *payload, unsigned int length);
unsigned long cycle_time_start = 0;
unsigned long cycle_time_end = 0;

void setup()
{
  Serial.begin(115200);
  initWiFiAndMQTT(); // Fra wifi_mqtt_setup.h
  InitFilling();
  initializeTime();
}

void loop()
{
  if (!client.connected())
  {
    reconnect();
  }
  client.loop();
}

void callback(char *topic, byte *payload, unsigned int length)
{
  String message;
  for (unsigned int i = 0; i < length; i++)
  {
    message += (char)payload[i];
  }

  if (String(topic) == topic_sub_Filling_Cmd)
  {
    cycle_time_start = millis();
    readMessage(message);
    FillingRunning();
    cycle_time_end = millis();
    double cycle_time = (cycle_time_end - cycle_time_start) / 1000.0;
    sendCycleTime(cycle_time, topic_pub_cycle_time);
  }
  else if (String(topic) == topic_sub_Needle_Cmd)
  {
    cycle_time_start = millis();
    readMessage(message);
    Needle_Attachment();
    cycle_time_end = millis();
    double cycle_time = (cycle_time_end - cycle_time_start) / 1000.0;
    sendCycleTime(cycle_time, topic_pub_cycle_time);
  }
}

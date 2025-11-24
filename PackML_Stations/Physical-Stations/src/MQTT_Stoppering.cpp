#include <Arduino.h>
#include "wifi_mqtt_setup_stoppering.h"
#include "stoppering_station.h"

unsigned long cycle_time_start = 0;
unsigned long cycle_time_end = 0;

void callback(char *topic, byte *payload, unsigned int length);

void setup()
{
  Serial.begin(115200);
  initWiFiAndMQTT(); // Fra wifi_mqtt_setup.h
  InitStoppering();
  initializeTime();
  reconnect();
  SendMQTTMessage("null", "Idle", topic_pub_status);
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

  if (String(topic) == topic_sub_Stoppering_Cmd)
  {
    cycle_time_start = millis();
    readMessage(message);
    StopperingRunning();
    cycle_time_end = millis();
    double cycle_time = (cycle_time_end - cycle_time_start) / 1000.0;
    sendCycleTime(cycle_time, topic_pub_cycle_time);
  }
}
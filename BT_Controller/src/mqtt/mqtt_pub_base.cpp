#include "mqtt/mqtt_pub_base.h"
#include "mqtt/mqtt_client.h"
#include "utils.h"
#include <iostream>

namespace fs = std::filesystem;

MqttPubBase::MqttPubBase(MqttClient &mqtt_client,
                         const mqtt_utils::Topic &request_topic)
    : mqtt_client_(mqtt_client),
      request_topic_(request_topic),
      halt_topic_(mqtt_utils::Topic())
{
  request_topic_.initValidator();
}
MqttPubBase::MqttPubBase(MqttClient &mqtt_client,
                         const mqtt_utils::Topic &request_topic, const mqtt_utils::Topic &halt_topic)
    : mqtt_client_(mqtt_client),
      request_topic_(request_topic),
      halt_topic_(halt_topic)
{
  request_topic_.initValidator();
  halt_topic_.initValidator();
}

void MqttPubBase::publish(const json &msg)
{
  if (request_topic_.validateMessage(msg))
  {
    mqtt_client_.publish(request_topic_.getTopic(), msg.dump(), request_topic_.getQos(), request_topic_.getRetain());
  }
}
void MqttPubBase::publishHalt(const json &msg)
{
  if (halt_topic_.validateMessage(msg))
  {
    mqtt_client_.publish(halt_topic_.getTopic(), msg.dump(), halt_topic_.getQos(), halt_topic_.getRetain());
  }
}
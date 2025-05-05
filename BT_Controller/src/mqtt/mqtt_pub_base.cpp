#include "mqtt/mqtt_pub_base.h"
#include "mqtt/mqtt_client.h"
#include "mqtt/utils.h"
#include <iostream>

namespace fs = std::filesystem;

MqttPubBase::MqttPubBase(MqttClient &mqtt_client,
                         const mqtt_utils::Topic &request_topic)
    : mqtt_client_(mqtt_client),
      request_topic_(request_topic)
{
  request_topic_.initValidator();
}

void MqttPubBase::publish(const json &msg)
{
  if (request_topic_.validateMessage(msg))
  {
    mqtt_client_.publish(request_topic_.getTopic(), msg.dump(), request_topic_.getQos(), request_topic_.getRetain());
  }
}

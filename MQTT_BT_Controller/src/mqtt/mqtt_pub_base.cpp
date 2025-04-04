#include "mqtt/mqtt_pub_base.h"
#include "mqtt/proxy.h"
#include <iostream>

MqttPubBase::MqttPubBase(Proxy &proxy,
                         const std::string &request_topic = "",
                         const std::string &request_schema_path = "",
                         const int &qos = 0,
                         const bool &retain = false)
    : proxy_(proxy),
      request_topic_(request_topic),
      request_schema_path_(request_schema_path),
      qos_(qos),
      retain_(retain)
{
}

void MqttPubBase::publish(const json &msg)
{
  // TODO this should do json validation
  proxy_.publish(request_topic_, msg.dump(), qos_, retain_);
}

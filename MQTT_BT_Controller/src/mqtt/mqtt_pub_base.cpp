#include "mqtt/mqtt_pub_base.h"
#include "mqtt/mqtt_client.h"
#include "mqtt/utils.h"
#include <iostream>

namespace fs = std::filesystem;

MqttPubBase::MqttPubBase(MqttClient &mqtt_client,
                         const std::string &request_topic = "",
                         const std::string &request_schema_path = "",
                         const int &qos = 0,
                         const bool &retain = false)
    : mqtt_client_(mqtt_client),
      request_topic_(request_topic),
      request_topic_pattern_(request_topic),
      request_schema_path_(request_schema_path),
      request_schema_validator_(nullptr),
      pubqos_(qos),
      retain_(retain)     
{
  // Load schema if path is provided
  if (!request_schema_path_.empty())
  {
    request_schema_validator_ = mqtt_utils::createSchemaValidator(request_schema_path_);
  }
}

void MqttPubBase::publish(const json &msg)
{
  // TODO this should do json validation
  // Validate JSON against schema if validator is available
  if (request_schema_validator_)
  {
    try
    {
      request_schema_validator_->validate(msg);
    }
    catch (const std::exception &e)
    {
      std::cerr << "JSON validation failed: " << e.what() << std::endl;
      return; // Don't publish invalid messages
    }
  }
  mqtt_client_.publish(request_topic_, msg.dump(), pubqos_, retain_);
}

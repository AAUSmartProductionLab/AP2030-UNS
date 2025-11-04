#include "mqtt/mqtt_pub_base.h"
#include "mqtt/mqtt_client.h" // Ensure MqttClient definition is available
#include <iostream>

namespace fs = std::filesystem;

MqttPubBase::MqttPubBase(MqttClient &mqtt_client)
    : mqtt_client_(&mqtt_client)
{
}

MqttPubBase::~MqttPubBase()
{
  // Destructor logic if any
}

void MqttPubBase::publish(const std::string &topic_key, const json &message)
{
  if (!mqtt_client_)
  {
    std::cerr << "MqttPubBase: MQTT client is not initialized." << std::endl;
    return;
  }

  auto it = topics_.find(topic_key);
  if (it != topics_.end())
  {
    const std::string &topic_str = it->second.getTopic();
    if (topic_str.empty() || topic_str.find('{') != std::string::npos)
    {
      std::cerr << "MqttPubBase: Topic for key '" << topic_key << "' is not fully formatted or is empty: " << topic_str << std::endl;
      return;
    }
    mqtt_client_->publish(topic_str, message.dump(), it->second.getQos(), it->second.getRetain());
  }
  else
  {
    std::cerr << "MqttPubBase: Topic key '" << topic_key << "' not found." << std::endl;
  }
}

void MqttPubBase::publish(const std::string &topic_key, const std::string &message)
{
  if (!mqtt_client_)
  {
    std::cerr << "MqttPubBase: MQTT client is not initialized." << std::endl;
    return;
  }

  auto it = topics_.find(topic_key);
  if (it != topics_.end())
  {
    const std::string &topic_str = it->second.getTopic();
    if (topic_str.empty() || topic_str.find('{') != std::string::npos)
    {
      std::cerr << "MqttPubBase: Topic for key '" << topic_key << "' is not fully formatted or is empty: " << topic_str << std::endl;
      return;
    }
    mqtt_client_->publish(topic_str, message, it->second.getQos(), it->second.getRetain());
  }
  else
  {
    std::cerr << "MqttPubBase: Topic key '" << topic_key << "' not found." << std::endl;
  }
}

void MqttPubBase::setTopic(const std::string &topic_key, const mqtt_utils::Topic &topic_object)
{
  topics_[topic_key] = topic_object;
}

void MqttPubBase::setFormattedTopic(const std::string &topic_key, const std::string &formatted_topic_str)
{
  auto it = topics_.find(topic_key);
  if (it != topics_.end())
  {
    it->second.setTopic(formatted_topic_str);
  }
  else
  {
    std::cerr << "MqttPubBase: Cannot set formatted topic for unknown key '" << topic_key << "'" << std::endl;
  }
}
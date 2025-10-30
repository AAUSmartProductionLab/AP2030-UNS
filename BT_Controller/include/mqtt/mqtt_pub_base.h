#pragma once

#include "utils.h"
#include <nlohmann/json.hpp>
#include <string>
#include <vector>
#include <map>

class MqttClient;

class MqttPubBase
{
protected:
    MqttClient *mqtt_client_;
    std::map<std::string, mqtt_utils::Topic> topics_;
    bool initialized_ = false;

public:
    MqttPubBase(MqttClient &mqtt_client);
    virtual ~MqttPubBase();

    virtual void publish(const std::string &topic_key, const nlohmann::json &message);
    virtual void publish(const std::string &topic_key, const std::string &message);

    void setTopic(const std::string &topic_key, const mqtt_utils::Topic &topic_object);
    void setFormattedTopic(const std::string &topic_key, const std::string &formatted_topic_str);
};
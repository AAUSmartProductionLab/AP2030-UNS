#pragma once

#include "utils.h"
#include <nlohmann/json.hpp>
#include <string>
#include <vector>
#include <map> // Required for std::map

// Forward declaration
class MqttClient;
using nlohmann::json;

class MqttPubBase
{
protected:
    MqttClient *mqtt_client_;
    std::map<std::string, mqtt_utils::Topic> topics_; // Map to store topics by logical key

public:
    MqttPubBase(MqttClient &mqtt_client,
                const std::map<std::string, mqtt_utils::Topic> &topics);
    virtual ~MqttPubBase();

    virtual void publish(const std::string &topic_key, const json &message, bool retain = false, int qos = 1);
    virtual void publish(const std::string &topic_key, const std::string &message, bool retain = false, int qos = 1);

    // Optional: Method to set/update a topic pattern after construction if needed
    void setTopic(const std::string &topic_key, const mqtt_utils::Topic &topic_object);
    // Method to update the formatted topic string for an existing key
    void setFormattedTopic(const std::string &topic_key, const std::string &formatted_topic_str);

    // Method to get the underlying map if direct access is needed (use with caution)
    // const std::map<std::string, mqtt_utils::Topic>& getAllTopics() const { return topics_; }
};
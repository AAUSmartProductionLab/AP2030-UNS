#pragma once

#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include <mutex>
#include <string>
#include <functional>

// Forward declarations
namespace BT
{
    class BehaviorTreeFactory;
}

class MqttClient;

namespace mqtt
{
    struct properties;
}

using json = nlohmann::json;
using json_uri = nlohmann::json_uri;

/**
 * @brief Base class for MQTT-enabled nodes
 */
class MqttPubBase
{
protected:
    MqttClient &mqtt_client_;
    std::string request_topic_;
    std::string request_schema_path_;
    int qos_;
    bool retain_;
    std::unique_ptr<nlohmann::json_schema::json_validator> request_schema_validator_;
    std::string request_topic_pattern_;
    std::string formatTopic(const std::string &topic_pattern, std::string &replacement)
    {
        std::string formatted_topic = topic_pattern;
        size_t pos = formatted_topic.find("+");
        if (pos != std::string::npos)
        {
            formatted_topic.replace(pos, 1, replacement);
        }
        return formatted_topic;
    }

public:
    MqttPubBase(MqttClient &mqtt_client,
                const std::string &request_topic,
                const std::string &request_schema_path,
                const int &qos,
                const bool &retain);

    virtual ~MqttPubBase() = default;
    void publish(const json &msg);
};
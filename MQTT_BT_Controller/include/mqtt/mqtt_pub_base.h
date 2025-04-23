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
    std::string request_topic_; // The precise request_topic on which the node is publishing without wildcards
    const std::string request_topic_pattern_; // The request_topic that may include wildcards
    std::string request_schema_path_;
    int pubqos_;
    bool retain_;
    std::unique_ptr<nlohmann::json_schema::json_validator> request_schema_validator_;


public:
    MqttPubBase(MqttClient &mqtt_client,
                const std::string &request_topic,
                const std::string &request_schema_path,
                const int &pubqos,
                const bool &retain);

    virtual ~MqttPubBase() = default;
    void publish(const json &msg);
};
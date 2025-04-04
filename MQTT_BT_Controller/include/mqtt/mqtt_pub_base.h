#pragma once

#include <nlohmann/json.hpp>
#include <mutex>
#include <string>
#include <functional>

// Forward declarations
namespace BT
{
    class BehaviorTreeFactory;
}

class Proxy;

namespace mqtt
{
    struct properties;
}

using json = nlohmann::json;

/**
 * @brief Base class for MQTT-enabled nodes
 */
class MqttPubBase
{
protected:
    Proxy &proxy_;
    std::string request_topic_;
    std::string request_schema_path_;
    int qos_;
    bool retain_;

public:
    MqttPubBase(Proxy &proxy,
                const std::string &request_topic,
                const std::string &request_schema_path,
                const int &qos,
                const bool &retain);

    virtual ~MqttPubBase() = default;
    void publish(const json &msg);
};
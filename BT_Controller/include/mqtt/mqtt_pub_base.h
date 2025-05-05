#pragma once

#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include <mutex>
#include <string>
#include <functional>
#include "mqtt/utils.h"
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

public:
    MqttPubBase(MqttClient &mqtt_client,
                const mqtt_utils::Topic &resquest_topic);

    virtual ~MqttPubBase() = default;
    void publish(const json &msg);

    mqtt_utils::Topic request_topic_;
};
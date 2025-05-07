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
    MqttPubBase(MqttClient &mqtt_client,
                const mqtt_utils::Topic &resquest_topic,
                const mqtt_utils::Topic &halt_topic);
    virtual ~MqttPubBase() = default;
    void publish(const json &msg);
    void publish(const json &msg, const mqtt_utils::Topic &topic);

    mqtt_utils::Topic request_topic_;
    mqtt_utils::Topic halt_topic_;
};
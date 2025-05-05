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
class NodeMessageDistributor;

namespace mqtt
{
    struct properties;
}

using json = nlohmann::json;
using json_uri = nlohmann::json_uri;

class MqttSubBase
{
protected:
    MqttClient &mqtt_client_;
    std::mutex mutex_;
    static NodeMessageDistributor *node_message_distributor_;

public:
    MqttSubBase(MqttClient &mqtt_client,
                const mqtt_utils::Topic &response_topic);

    virtual ~MqttSubBase() = default;

    void processMessage(const json &msg, mqtt::properties props);

    virtual bool isInterestedIn(const json &msg);

    virtual void callback(const json &msg, mqtt::properties props) = 0;

    static void setNodeMessageDistributor(NodeMessageDistributor *manager);

    virtual std::string getRegistrationName() const
    {
        // Default implementation - derived classes can override this
        return typeid(*this).name();
    }
    virtual std::string getBTNodeName() const = 0;

    mqtt_utils::Topic response_topic_;
};
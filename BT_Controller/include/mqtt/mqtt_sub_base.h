#pragma once

#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include <mutex>
#include <string>
#include <functional>
#include <map> // Add this line
#include "utils.h"

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

using json_uri = nlohmann::json_uri;

class MqttSubBase
{
protected:
    MqttClient &mqtt_client_;
    std::mutex mutex_;
    static NodeMessageDistributor *node_message_distributor_;

public:
    MqttSubBase(MqttClient &mqtt_client);

    virtual ~MqttSubBase() = default;

    void processMessage(const std::string &actual_topic_str, const nlohmann::json &msg, mqtt::properties props);
    void setTopic(const std::string &topic_key, const mqtt_utils::Topic &topic_object);
    virtual void callback(const std::string &topic_key, const nlohmann::json &msg, mqtt::properties props) = 0;

    static void setNodeMessageDistributor(NodeMessageDistributor *manager);

    virtual std::string getRegistrationName() const
    {
        return typeid(*this).name();
    }
    virtual std::string getBTNodeName() const = 0;

    std::map<std::string, mqtt_utils::Topic> topics_;
};
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

using json = nlohmann::json;
using json_uri = nlohmann::json_uri;

class MqttSubBase
{
protected:
    MqttClient &mqtt_client_;
    std::mutex mutex_;
    static NodeMessageDistributor *node_message_distributor_;
    // mqtt_utils::Topic response_topic_; // Remove

public:
    // MqttSubBase(MqttClient &mqtt_client,
    //             const mqtt_utils::Topic &response_topic); // Remove
    MqttSubBase(MqttClient &mqtt_client,
                const std::map<std::string, mqtt_utils::Topic> &topics);

    virtual ~MqttSubBase() = default;

    void processMessage(const std::string &actual_topic_str, const json &msg, mqtt::properties props);
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) = 0; // Added topic_key

    static void setNodeMessageDistributor(NodeMessageDistributor *manager);

    virtual std::string getRegistrationName() const
    {
        // Default implementation - derived classes can override this
        return typeid(*this).name();
    }
    virtual std::string getBTNodeName() const = 0;

    // Made public for UseStation to format topics and NodeMessageDistributor to access.
    // Consider protected with accessors for better encapsulation.
    std::map<std::string, mqtt_utils::Topic> topics_;
    // const std::map<std::string, mqtt_utils::Topic>& getTopics() const { return topics_; } // Alternative
};
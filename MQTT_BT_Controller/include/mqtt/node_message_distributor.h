#pragma once

#include <nlohmann/json.hpp>
#include <vector>
#include <map>
#include <string>
#include <typeindex>
#include <algorithm>
#include <functional>
#include "mqtt/async_client.h"
#include "mqtt/mqtt_sub_base.h"

using json = nlohmann::json;

// Forward declarations
class MqttClient;

/**
 * @brief Manages MQTT subscriptions for behavior tree nodes
 */
class NodeMessageDistributor
{
public:
    // Constructor and destructor
    NodeMessageDistributor(MqttClient &mqtt_client);
    ~NodeMessageDistributor();

    // Message handling
    void handle_message(const std::string &msg_topic, const json &payload, mqtt::properties props);
    void route_to_nodes(const std::type_index &type_index, const std::string &topic, const json &msg, mqtt::properties props);

    // Topic handler registration
    void register_topic_handler(const std::string &topic,
        std::function<void(const std::string &, const json &, mqtt::properties)> callback,
        const int &qos);

    // Node registration methods
    template <typename T>
    void registerNodeType(const std::string &response_topic, const int &qos)
    {
        auto type_index = std::type_index(typeid(T));

        node_subscriptions_[type_index] = {
            response_topic,
            {} // Empty vector for instances
        };
        // Register with the topic
        register_topic_handler(response_topic,
                               [this, type_idx = type_index](const std::string &msg_topic, const json &msg, mqtt::properties props)
                               {
                                   route_to_nodes(type_idx, msg_topic, msg, props);
                               },qos);
    }

    // Register the individual nodes
    void registerDerivedInstance(MqttSubBase *instance);
    void unregisterInstance(MqttSubBase *instance);

private:
    bool topicMatches(const std::string &pattern, const std::string &topic);
    struct TopicHandler
    {
        std::string topic;
        std::function<void(const std::string &, const json &, mqtt::properties)> callback;
    };
    struct NodeTypeSubscription
    {
        std::string topic;
        std::vector<MqttSubBase *> instances;
    };
    MqttClient &mqtt_client_;
    std::vector<TopicHandler> topic_handlers_;

    std::map<std::type_index, NodeTypeSubscription> node_subscriptions_;
};

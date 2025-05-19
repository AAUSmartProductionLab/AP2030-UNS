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
#include <behaviortree_cpp/bt_factory.h>
#include <set>

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
    void handle_incoming_message(const std::string &msg_topic, const json &payload, mqtt::properties props);
    void route_to_nodes(const std::type_index &type_index, const std::string &topic, const json &msg, mqtt::properties props);

    // Node registration methods
    template <typename T>
    void registerNodeType(const std::string &response_topic)
    {
        auto type_index = std::type_index(typeid(T));
        node_subscriptions_[type_index] = {
            response_topic,
            {}};
    }

    // Register the individual nodes
    void registerDerivedInstance(MqttSubBase *instance);
    void unregisterInstance(MqttSubBase *instance);

    // New method to subscribe only to topics for nodes in the active tree
    void subscribeToActiveNodes(const BT::Tree &tree);

    // Method to get all currently subscribed topic patterns
    std::vector<std::string> getActiveTopicPatterns() const; // New method

private:
    // Modified structure to track subscription status
    struct TopicHandler
    {
        std::string topic;
        std::function<void(const std::string &, const json &, mqtt::properties)> callback;
        int qos;
        bool subscribed;
    };
    struct NodeTypeSubscription
    {
        std::string topic_pattern;
        std::vector<MqttSubBase *> instances;
    };

    MqttClient &mqtt_client_;
    std::vector<TopicHandler> topic_handlers_;
    std::map<std::type_index, NodeTypeSubscription> node_subscriptions_;
};

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
#include <optional>
#include <mutex>
#include <chrono>

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

    // Register a late-initializing node AND subscribe to its specific topics
    // This triggers the broker to resend retained messages for those topics
    bool registerLateInitializingNode(MqttSubBase *instance,
                                      std::chrono::milliseconds timeout = std::chrono::seconds(2));

    // Set up routing AND subscribe to specific topics for nodes in the active tree
    // Subscribing triggers delivery of retained messages
    bool subscribeForActiveNodes(const BT::Tree &tree,
                                 std::chrono::milliseconds timeout_per_subscription = std::chrono::seconds(5));

    // Method to get all currently subscribed topic patterns
    std::vector<std::string> getActiveTopicPatterns() const;

private:
    // Modified structure to track subscription status and route to multiple instances
    struct TopicHandler
    {
        std::string topic;
        std::vector<MqttSubBase*> instances;  // All instances listening to this topic
        int qos;
        bool subscribed;
        
        void routeMessage(const std::string &msg_topic, const json &msg, mqtt::properties props) const
        {
            for (MqttSubBase *instance : instances)
            {
                if (instance)
                {
                    instance->processMessage(msg_topic, msg, props);
                }
            }
        }
    };
    struct NodeTypeSubscription
    {
        std::string topic_pattern;
        std::vector<MqttSubBase *> instances;
    };

    MqttClient &mqtt_client_;
    std::vector<TopicHandler> topic_handlers_;
    std::map<std::type_index, NodeTypeSubscription> node_subscriptions_;

    // Mutex for thread-safe operations
    mutable std::mutex handlers_mutex_;
    mutable std::mutex registry_mutex_;
};

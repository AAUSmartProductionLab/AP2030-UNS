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
class Proxy;

/**
 * @brief Manages MQTT subscriptions for behavior tree nodes
 */
class SubscriptionManager : public mqtt::callback
{
public:
    // Constructor and destructor
    SubscriptionManager(Proxy &proxy);
    virtual ~SubscriptionManager() override;

    // MQTT callback interface implementation
    void message_arrived(mqtt::const_message_ptr msg) override;

    // Add the other required virtual methods from mqtt::callback
    void connection_lost(const std::string &cause) override;
    void delivery_complete(mqtt::delivery_token_ptr token) override;
    // Add any other virtual methods required by mqtt::callback

    // Add your existing methods...
    void register_topic_handler(const std::string &topic,
                                std::function<void(const json &, mqtt::properties)> callback);

    // Other methods...
    void route_to_nodes(const std::type_index &type_index, const json &msg, mqtt::properties props);

    // Node registration methods...
    // Template methods...

    // Register a topic handler for the entire node type
    template <typename T>
    void registerNodeType(const std::string &response_topic)
    {
        auto type_index = std::type_index(typeid(T));

        node_subscriptions_[type_index] = {
            response_topic,
            {} // Empty vector for instances
        };
        std::cout << "Registering node type: " << type_index.name() << " with topic: " << response_topic << std::endl;
        // Register with the full topic including subtopic
        register_topic_handler(response_topic,
                               [this, type_idx = type_index](const json &msg, mqtt::properties props)
                               {
                                   route_to_nodes(type_idx, msg, props);
                               });
    }

    // Register the individual nodes
    void registerDerivedInstance(MqttSubBase *instance)
    {
        std::type_index type_index(typeid(*instance));
        if (node_subscriptions_.find(type_index) != node_subscriptions_.end())
        {
            node_subscriptions_[type_index].instances.push_back(instance);
        }
    }

    // Node instance unregistration
    void unregisterInstance(MqttSubBase *instance)
    {
        std::type_index type_index(typeid(*instance));
        if (node_subscriptions_.find(type_index) != node_subscriptions_.end())
        {
            auto &instances = node_subscriptions_[type_index].instances;
            instances.erase(std::remove(instances.begin(), instances.end(), instance), instances.end());
        }
    }

private:
    // Your existing members...
    // For general topic handlers
    struct TopicHandler
    {
        std::string topic;
        std::function<void(const json &, mqtt::properties)> callback;
    };
    std::vector<TopicHandler> topic_handlers_;

    // For node type subscriptions
    struct NodeTypeSubscription
    {
        std::string topic;
        std::vector<MqttSubBase *> instances;
    };
    std::map<std::type_index, NodeTypeSubscription> node_subscriptions_;

    Proxy &proxy_;
};
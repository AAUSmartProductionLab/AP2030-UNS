#pragma once

#include <map>
#include <vector>
#include <string>
#include <memory>
#include <typeindex>
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include "mqtt/subscription_manager_client.h"
// Forward declarations
class Proxy;

using nlohmann::json;
using nlohmann::json_schema::json_validator;

/**
 * @brief A subscription manager that routes mqtt messages to behaviourtree nodes that are interested in the specific CommandUuid
 * @brief The messages are generally expected on a topic part of the /Data topic of the UNS
 */
class SubscriptionManager : public mqtt::callback
{
public:
    explicit SubscriptionManager(Proxy &proxy);

    // MQTT callback implementation
    void message_arrived(mqtt::const_message_ptr msg) override;
    void connected(const std::string &cause) override {}
    void connection_lost(const std::string &cause) override {}

    // General topic handler registration (simplified version without validation)
    void register_topic_handler(const std::string &topic,
                                std::function<void(const json &, mqtt::properties)> callback);

    // Register a topic handler for the entire node type
    template <typename T>
    void registerNodeType(const std::string &UNS_TOPIC,
                          const std::string &schema_path,
                          int qos = 1)
    {
        auto type_index = std::type_index(typeid(T));
        std::string subtopic = extractSubtopicFromSchema(schema_path);
        std::string full_topic = UNS_TOPIC + "/DATA" + subtopic;

        if (node_subscriptions_.find(type_index) == node_subscriptions_.end())
        {
            NodeTypeSubscription sub;
            sub.topic = full_topic;
            sub.schema_path = schema_path;
            sub.qos = qos;
            node_subscriptions_[type_index] = sub;

            // Register with MQTT broker via proxy
            register_topic_handler(full_topic,
                                   [this, type_index](const json &msg, mqtt::properties props)
                                   {
                                       this->route_to_nodes(type_index, msg, props);
                                   });
        }
    }

    // Register the individual nodes
    template <typename T>
    void registerDerivedInstance(SubscriptionManagerClient *instance)
    {
        auto type_index = std::type_index(typeid(T));
        if (node_subscriptions_.find(type_index) != node_subscriptions_.end())
        {
            node_subscriptions_[type_index].instances.push_back(instance);
        }
        else
        {
            std::cerr << "Attempting to register instance of unregistered type" << std::endl;
        }
    }

    // Node instance unregistration
    template <typename T>
    void unregisterInstance(SubscriptionManagerClient *instance)
    {
        auto type_index = std::type_index(typeid(T));
        if (node_subscriptions_.find(type_index) != node_subscriptions_.end())
        {
            auto &instances = node_subscriptions_[type_index].instances;
            instances.erase(std::remove(instances.begin(), instances.end(), instance), instances.end());
        }
    }

    // Make this method public so it can be used by MqttActionNode
    std::string extractSubtopicFromSchema(const std::string &schema_path);

private:
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
        std::string schema_path;
        int qos;
        std::vector<SubscriptionManagerClient *> instances;
    };
    std::map<std::type_index, NodeTypeSubscription> node_subscriptions_;

    Proxy &proxy_;

    // Helper methods
    void route_to_nodes(const std::type_index &type_index, const json &msg, mqtt::properties props);
};
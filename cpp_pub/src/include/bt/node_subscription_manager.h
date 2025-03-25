#pragma once

#include <map>
#include <vector>
#include <string>
#include <fstream>
#include <memory>
#include <typeindex>
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include "mqtt/proxy.h"
#include "bt/mqtt_action_node.h"
using nlohmann::json;

/**
 * @brief Manages MQTT subscriptions per node type and routes messages to instances
 */
class NodeTypeSubscriptionManager
{
private:
    struct NodeTypeSubscription
    {
        std::string topic;
        std::string schema_path;
        int qos;
        std::vector<MqttActionNode *> instances;

        // Message handler that will route to appropriate instances
        std::function<void(const json &, mqtt::properties)> message_handler;
    };

    std::map<std::type_index, NodeTypeSubscription> subscriptions_;
    Proxy &mqtt_proxy_;

public:
    NodeTypeSubscriptionManager(Proxy &proxy) : mqtt_proxy_(proxy) {}

    /**
     * @brief Register a node type subscription
     *
     * @tparam T Node type
     * @param topic MQTT topic to subscribe to
     * @param schema_path Schema path for message validation
     * @param qos Quality of service
     */
    template <typename T>
    void registerNodeType(const std::string &topic_base, const std::string &schema_path, int qos = 1)
    {
        auto type_index = std::type_index(typeid(T));
        // Extract subtopic from schema if needed
        std::string subtopic = extractSubtopicFromSchema(schema_path);
        std::string full_topic = topic_base + "/DATA" + subtopic;

        // If this is a new node type, set up the subscription
        if (subscriptions_.find(type_index) == subscriptions_.end())
        {
            NodeTypeSubscription sub;
            sub.topic = full_topic;
            sub.schema_path = schema_path;
            sub.qos = qos;

            // Create a handler that will route messages
            sub.message_handler = [this, type_index](const json &msg, mqtt::properties props)
            {
                this->routeMessage(type_index, msg, props);
            };

            // Register with MQTT broker
            mqtt_proxy_.register_topic_handler(full_topic, sub.message_handler);
            mqtt_proxy_.subscribe(full_topic, qos);

            subscriptions_[type_index] = sub;
        }
    }

    /**
     * @brief Register a node instance with its type subscription
     *
     * @tparam T Node type
     * @param node Node instance
     */
    template <typename T>
    void registerInstance(T *node)
    {
        auto type_index = std::type_index(typeid(T));

        if (subscriptions_.find(type_index) != subscriptions_.end())
        {
            subscriptions_[type_index].instances.push_back(node);
        }
    }

    /**
     * @brief Unregister a node instance
     *
     * @tparam T Node type
     * @param node Node instance to remove
     */
    template <typename T>
    void unregisterInstance(T *node)
    {
        auto type_index = std::type_index(typeid(T));

        if (subscriptions_.find(type_index) != subscriptions_.end())
        {
            auto &instances = subscriptions_[type_index].instances;
            instances.erase(std::remove(instances.begin(), instances.end(), node), instances.end());
        }
    }

    // Add this utility method to properly register derived types
    template <typename T>
    void registerDerivedInstance(MqttActionNode *node)
    {
        auto type_index = std::type_index(typeid(T));

        if (subscriptions_.find(type_index) != subscriptions_.end())
        {
            subscriptions_[type_index].instances.push_back(node);
            std::cout << "Registered node " << node->name() << " with type "
                      << type_index.name() << std::endl;
        }
        else
        {
            std::cerr << "Warning: Attempted to register instance before type: "
                      << type_index.name() << std::endl;
        }
    }

private:
    /**
     * @brief Routes incoming messages to the appropriate node instances
     *
     * @param type_index Type of node to route to
     * @param msg JSON message
     * @param props MQTT properties
     */
    void routeMessage(const std::type_index &type_index, const json &msg, mqtt::properties props)
    {
        std::cout << "Received message on topic for type " << type_index.name() << std::endl;
        std::cout << "Message content: " << msg.dump(2) << std::endl;

        if (subscriptions_.find(type_index) == subscriptions_.end())
        {
            std::cout << "No subscription found for this type!" << std::endl;
            return;
        }

        // Check if the message contains CommandUuid which is often used for routing
        if (msg.contains("CommandUuid"))
        {
            std::string msgUuid = msg["CommandUuid"].get<std::string>();
            std::cout << "Message has CommandUuid: " << msgUuid << std::endl;

            bool found_interested_node = false;
            // Route to specific node instances that are interested in this CommandUuid
            for (auto node : subscriptions_[type_index].instances)
            {
                std::cout << "Checking node " << node->name() << " for interest in UUID" << std::endl;
                if (node->isInterestedIn("CommandUuid", msg["CommandUuid"]))
                {
                    std::cout << "Found interested node: " << node->name() << std::endl;
                    node->handleMessage(msg, props);
                    found_interested_node = true;
                }
            }

            if (!found_interested_node)
            {
                std::cout << "WARNING: No node was interested in CommandUuid: " << msgUuid << std::endl;
                // Optionally, print the UUIDs that nodes are looking for:
                if (!subscriptions_[type_index].instances.empty())
                {
                    std::cout << "Active instances: " << subscriptions_[type_index].instances.size() << std::endl;
                }
            }
        }
        else
        {
            // Route to all instances of this node type
            std::cout << "Message has no CommandUuid, routing to all instances" << std::endl;
            for (auto node : subscriptions_[type_index].instances)
            {
                node->handleMessage(msg, props);
            }
        }
    }

    // Add this method to extract subtopics from schema files
    std::string extractSubtopicFromSchema(const std::string &schema_path)
    {
        // Parse the schema file and extract subtopic information
        // This is just a placeholder - implement according to your schema format
        try
        {
            std::ifstream file(schema_path);
            json schema = json::parse(file);

            // Check if the schema contains subtopic information
            if (schema.contains("subtopic"))
            {
                return schema["subtopic"].get<std::string>();
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << "Failed to parse schema file: " << e.what() << std::endl;
        }
        return "";
    }
};
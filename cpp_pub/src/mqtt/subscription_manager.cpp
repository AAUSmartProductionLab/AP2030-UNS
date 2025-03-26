#include "mqtt/subscription_manager.h"
#include "mqtt/proxy.h"
#include "bt/mqtt_action_node.h"
#include <iostream>
#include <fstream>

SubscriptionManager::SubscriptionManager(Proxy &proxy) : proxy_(proxy)
{
    // Register this as the callback for the proxy
    proxy.set_callback(*this);
}

void SubscriptionManager::message_arrived(mqtt::const_message_ptr msg)
{
    std::string topic = msg->get_topic();

    try
    {
        json payload = json::parse(msg->get_payload());
        mqtt::properties props = msg->get_properties();

        // Check for any matching handlers
        bool handled = false;
        for (const auto &handler : topic_handlers_)
        {
            if (topic == handler.topic || topic.find(handler.topic) != std::string::npos)
            {
                handler.callback(payload, props);
                handled = true;
            }
        }

        if (!handled)
        {
            std::cout << "No handler found for topic: " << topic << std::endl;
            std::cout << "Registered handlers are: " << std::endl;
            for (const auto &handler : topic_handlers_)
            {
                std::cout << " - " << handler.topic << std::endl;
            }
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error processing message: " << e.what() << std::endl;
    }
}

void SubscriptionManager::register_topic_handler(
    const std::string &topic,
    std::function<void(const json &, mqtt::properties)> callback)
{
    topic_handlers_.push_back({topic, callback});
    proxy_.subscribe(topic, 0); // Default QoS 0
}

void SubscriptionManager::route_to_nodes(
    const std::type_index &type_index,
    const json &msg,
    mqtt::properties props)
{
    if (node_subscriptions_.find(type_index) == node_subscriptions_.end())
    {
        std::cout << "No subscription found for type index: " << type_index.name() << std::endl;
        return;
    }

    auto &instances = node_subscriptions_[type_index].instances;
    for (auto *node : instances)
    {
        if (node)
        {
            // Check if the node is interested in this message
            bool interested = true;

            if (msg.contains("CommandUuid") && msg["CommandUuid"].is_string())
            {
                interested = node->isInterestedIn("CommandUuid", msg["CommandUuid"]);
            }
            else
            {
                // If no CommandUuid, check all fields for interest
                for (auto &[key, value] : msg.items())
                {
                    if (!node->isInterestedIn(key, value))
                    {
                        interested = false;
                        break;
                    }
                }
            }

            if (interested)
            {
                node->callback(msg, props);
            }
        }
    }
}

std::string SubscriptionManager::extractSubtopicFromSchema(const std::string &schema_path)
{
    try
    {
        std::ifstream file(schema_path);
        if (!file.is_open())
        {
            std::cerr << "Failed to open schema file: " << schema_path << std::endl;
            return "";
        }

        json schema_json;
        file >> schema_json;

        if (schema_json.contains("subtopic"))
        {
            return schema_json["subtopic"].get<std::string>();
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error parsing schema: " << e.what() << std::endl;
    }

    return "";
}
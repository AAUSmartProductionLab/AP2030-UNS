#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include <iostream>
#include <fstream>

NodeMessageDistributor::NodeMessageDistributor(MqttClient &mqtt_client) : mqtt_client_(mqtt_client)
{
    // Set this manager as the message handler for the mqtt_client
    mqtt_client.set_message_handler([this](const std::string &topic,
                                           const json &payload,
                                           mqtt::properties props)
                                    { handle_message(topic, payload, props); });
}

NodeMessageDistributor::~NodeMessageDistributor()
{
    // No need for explicit cleanup
}

void NodeMessageDistributor::register_topic_handler(
    const std::string &topic,
    std::function<void(const json &, mqtt::properties)> callback)
{
    topic_handlers_.push_back({topic, callback});

    // Subscribe to the topic through the mqtt_client
    mqtt_client_.subscribe_topic(topic, 0);
}

void NodeMessageDistributor::handle_message(const std::string &topic,
                                            const json &payload,
                                            mqtt::properties props)
{
    // Check for any matching handlers
    bool handled = false;
    for (const auto &handler : topic_handlers_)
    {
        if (topic == handler.topic)
        {
            handler.callback(payload, props);
            handled = true;
        }
    }

    if (!handled)
    {
        std::cout << "No handler found for topic: " << topic << std::endl;
    }
}

void NodeMessageDistributor::route_to_nodes(
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
            bool interested = false;

            for (auto &[key, value] : msg.items())
            {
                if (node->isInterestedIn(key, value))
                {
                    interested = true;
                    break;
                }
            }

            if (interested)
            {
                node->handleMessage(msg, props);
            }
        }
    }
}

void NodeMessageDistributor::registerDerivedInstance(MqttSubBase *instance)
{
    std::type_index type_index(typeid(*instance));
    if (node_subscriptions_.find(type_index) != node_subscriptions_.end())
    {
        node_subscriptions_[type_index].instances.push_back(instance);
    }
}

void NodeMessageDistributor::unregisterInstance(MqttSubBase *instance)
{
    std::type_index type_index(typeid(*instance));
    if (node_subscriptions_.find(type_index) != node_subscriptions_.end())
    {
        auto &instances = node_subscriptions_[type_index].instances;
        instances.erase(std::remove(instances.begin(), instances.end(), instance), instances.end());
    }
}
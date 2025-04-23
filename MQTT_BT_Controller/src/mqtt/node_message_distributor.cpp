#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include <iostream>
#include <fstream>

NodeMessageDistributor::NodeMessageDistributor(MqttClient &mqtt_client) : mqtt_client_(mqtt_client)
{
    // Set this manager as the message handler for the mqtt_client
    mqtt_client.set_message_handler([this](const std::string &msg_topic, const json &payload, mqtt::properties props){ handle_message(msg_topic, payload, props); });
}

NodeMessageDistributor::~NodeMessageDistributor()
{
    // No need for explicit cleanup
}

void NodeMessageDistributor::register_topic_handler(
    const std::string &topic,
    std::function<void(const std::string &, const json &, mqtt::properties)> callback,
    const int &subqos=0)
{
    topic_handlers_.push_back({topic, callback});

    // Subscribe to the topic through the mqtt_client
    mqtt_client_.subscribe_topic(topic, subqos);
}
bool NodeMessageDistributor::topicMatches(const std::string &pattern, const std::string &topic)
{
    std::istringstream patternStream(pattern);
    std::istringstream topicStream(topic);
    std::string patternSegment, topicSegment;

    while (std::getline(patternStream, patternSegment, '/') &&
           std::getline(topicStream, topicSegment, '/'))
    {
        if (patternSegment == "+")
        {
            continue;
        }
        else if (patternSegment == "#")
        {
            if (patternStream.peek() != EOF)
            {
                std::cout << "Invalid MQTT pattern: # must be the last segment in topic filter" << std::endl;
                return false;
            }
            return true;
        }
        else if (patternSegment != topicSegment)
        {
            return false;
        }
    }
    bool patternDone = !std::getline(patternStream, patternSegment, '/');
    bool topicDone = !std::getline(topicStream, topicSegment, '/');
    return patternDone && topicDone;
}
void NodeMessageDistributor::handle_message(const std::string &msg_topic,
                                            const json &payload,
                                            mqtt::properties props)
{
    bool handled = false;
    for (const auto &handler : topic_handlers_)
    {
        // Check if the incoming topic fits to any registered handlers considering wild cards
        if (topicMatches(handler.topic, msg_topic))
        {
            handler.callback(msg_topic, payload, props);
            handled = true;
        }
    }
    if (!handled)
    {
        std::cout << "No handler found for topic: " << msg_topic << std::endl;
    }
}

void NodeMessageDistributor::route_to_nodes(
    const std::type_index &type_index,
    const std::string &topic,
    const json &msg,
    mqtt::properties props)
{
    if (node_subscriptions_.find(type_index) == node_subscriptions_.end())
    {
        std::cout << "No subscription found for type index: " << type_index.name() << std::endl;
        return;
    }

    auto &subscription = node_subscriptions_[type_index];
    for (auto *node : subscription.instances)
    {
        if (node)
        {
            // Check if the bt node is interested in exactly this topic ignoring wild cards
            // and if the node is interested in the message
            if (node->getResponseTopic() == topic  && node->isInterestedIn(msg))
            {
                node->processMessage(msg, props);
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
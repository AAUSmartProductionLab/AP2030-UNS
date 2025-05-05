#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include <iostream>
#include <fstream>
#include <unordered_set>
#include <sstream>

NodeMessageDistributor::NodeMessageDistributor(MqttClient &mqtt_client) : mqtt_client_(mqtt_client)
{
    // Set this manager as the message handler for the mqtt_client
    mqtt_client.set_message_handler([this](const std::string &msg_topic, const json &payload, mqtt::properties props)
                                    { handle_message(msg_topic, payload, props); });
}

NodeMessageDistributor::~NodeMessageDistributor()
{
    // No need for explicit cleanup
}

void NodeMessageDistributor::subscribeToActiveNodes(const BT::Tree &tree)
{
    std::cout << "Subscribing to topics for active behavior tree nodes..." << std::endl;

    // Collect all node types in the tree
    std::set<std::string> activeNodeTypes;
    BT::applyRecursiveVisitor(tree.rootNode(), [&activeNodeTypes](const BT::TreeNode *node)
                              {
        if (node) {
            activeNodeTypes.insert(node->registrationName());
        } });

    // Map topics to their subscriber type indices
    std::map<std::string, std::vector<std::type_index>> topicSubscribers;
    std::map<std::string, int> topicMaxQoS; // Track maximum QoS per topic

    // Find all topics needed by active nodes
    for (const auto &[type_index, subscription] : node_subscriptions_)
    {
        for (auto *instance : subscription.instances)
        {
            if (!instance)
                continue;

            std::string nodeName = instance->getBTNodeName();
            if (activeNodeTypes.find(nodeName) == activeNodeTypes.end())
                continue;

            // Store the type index for this topic
            topicSubscribers[instance->response_topic_.getTopic()].push_back(type_index);

            // Update maximum QoS for this topic if necessary
            if (topicMaxQoS.find(instance->response_topic_.getTopic()) == topicMaxQoS.end() ||
                instance->response_topic_.getQos() > topicMaxQoS[instance->response_topic_.getTopic()])
            {
                topicMaxQoS[instance->response_topic_.getTopic()] = instance->response_topic_.getQos();
            }
        }
    }

    // Clear existing handlers
    topic_handlers_.clear();

    // Create new handlers and subscribe
    for (const auto &[topic, type_indices] : topicSubscribers)
    {
        // Create a handler that routes messages to appropriate node types
        auto callback = [this, type_indices](
                            const std::string &msg_topic, const json &msg, mqtt::properties props)
        {
            for (const auto &type_index : type_indices)
            {
                this->route_to_nodes(type_index, msg_topic, msg, props);
            }
        };
        const int qos = topicMaxQoS[topic];
        topic_handlers_.push_back({topic, callback, qos, false});
        mqtt_client_.subscribe_topic(topic, qos);
        topic_handlers_.back().subscribed = true;
    }

    std::cout << "Subscribed to " << topicSubscribers.size() << " topics for active nodes." << std::endl;
}

bool NodeMessageDistributor::topicMatches(const std::string &pattern, const std::string &topic)
{
    std::istringstream patternStream(pattern);
    std::istringstream topicStream(topic);
    std::string patternSegment, topicSegment;

    while (std::getline(patternStream, patternSegment, '/') &&
           std::getline(topicStream, topicSegment, '/'))
    {
        if (patternSegment == "+" || topicSegment == "+")
        {
            continue;
        }
        else if (patternSegment == "#" || topicSegment == "#")
        {
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
            if (topicMatches(node->response_topic_.getTopic(), topic) && node->isInterestedIn(msg))
            {
                node->processMessage(msg, props);
            }
        }
    }
}

void NodeMessageDistributor::registerDerivedInstance(MqttSubBase *instance)
{
    if (!instance)
        return;

    std::type_index type_index(typeid(*instance));
    node_subscriptions_[type_index].instances.push_back(instance);
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
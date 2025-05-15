#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h" // For MqttClient::subscribe_topic
#include "utils.h"            // For mqtt_utils::topicMatches
#include <iostream>
#include <set> // For std::set in getActiveTopicPatterns & subscribeToActiveNodes

NodeMessageDistributor::NodeMessageDistributor(MqttClient &mqtt_client_ref)
    : mqtt_client_(mqtt_client_ref) {}

NodeMessageDistributor::~NodeMessageDistributor()
{
}

std::vector<std::string> NodeMessageDistributor::getActiveTopicPatterns() const
{
    std::set<std::string> unique_topics;
    for (const auto &handler : topic_handlers_)
    {
        if (handler.subscribed) // Only include topics that are actively subscribed
        {
            unique_topics.insert(handler.topic);
        }
    }
    return std::vector<std::string>(unique_topics.begin(), unique_topics.end());
}

void NodeMessageDistributor::subscribeToActiveNodes(const BT::Tree &tree)
{
    std::set<std::string> active_node_registration_names;
    BT::applyRecursiveVisitor(tree.rootNode(),
                              [&active_node_registration_names](const BT::TreeNode *node)
                              {
                                  if (node)
                                  {
                                      active_node_registration_names.insert(node->registrationName());
                                  }
                              });

    std::map<std::string, std::vector<std::type_index>> topic_to_subscriber_types;
    std::map<std::string, int> topic_to_max_qos;

    for (const auto &[type_idx, type_subscription_info] : node_subscriptions_)
    {
        for (MqttSubBase *instance : type_subscription_info.instances)
        {
            if (!instance)
                continue;
            const std::string &topic_str = instance->response_topic_.getTopic();
            topic_to_subscriber_types[topic_str].push_back(type_idx);

            int instance_qos = instance->response_topic_.getQos();
            if (topic_to_max_qos.find(topic_str) == topic_to_max_qos.end() || instance_qos > topic_to_max_qos[topic_str])
            {
                topic_to_max_qos[topic_str] = instance_qos;
            }
        }
    }

    topic_handlers_.clear();
    int subscribed_count = 0;

    for (const auto &[topic_str, subscriber_type_indices] : topic_to_subscriber_types)
    {
        if (subscriber_type_indices.empty())
            continue;

        auto callback = [this, subscriber_type_indices_copy = subscriber_type_indices](
                            const std::string &msg_topic, const json &msg, mqtt::properties props)
        {
            for (const auto &type_idx : subscriber_type_indices_copy)
            {
                this->route_to_nodes(type_idx, msg_topic, msg, props);
            }
        };

        int qos = topic_to_max_qos[topic_str];
        if (mqtt_client_.subscribe_topic(topic_str, qos))
        {
            topic_handlers_.push_back({topic_str, callback, qos, true});
            subscribed_count++;
        }
        else
        {
            topic_handlers_.push_back({topic_str, callback, qos, false});
            std::cerr << "NodeMessageDistributor: Failed to subscribe to topic '" << topic_str << "'" << std::endl;
        }
    }
}

void NodeMessageDistributor::handle_incoming_message(const std::string &msg_topic,
                                                     const json &payload,
                                                     mqtt::properties props)
{
    bool handled = false;
    for (const auto &handler : topic_handlers_)
    {
        if (handler.subscribed && mqtt_utils::topicMatches(handler.topic, msg_topic))
        {
            handler.callback(msg_topic, payload, props);
            handled = true;
        }
    }

    if (!handled)
    {
    }
}

void NodeMessageDistributor::route_to_nodes(
    const std::type_index &type_idx_param,
    const std::string &topic,
    const json &msg,
    mqtt::properties props)
{
    auto it = node_subscriptions_.find(type_idx_param);
    if (it == node_subscriptions_.end())
    {
        return;
    }

    for (MqttSubBase *node_instance : it->second.instances)
    {
        if (node_instance)
        {
            if (mqtt_utils::topicMatches(node_instance->response_topic_.getTopic(), topic))
            {
                node_instance->processMessage(msg, props);
            }
        }
    }
}

void NodeMessageDistributor::registerDerivedInstance(MqttSubBase *instance)
{
    if (!instance)
        return;

    std::type_index instance_type_idx(typeid(*instance));
    node_subscriptions_[instance_type_idx].instances.push_back(instance);
}

void NodeMessageDistributor::unregisterInstance(MqttSubBase *instance)
{
    if (!instance)
        return;

    std::type_index instance_type_idx(typeid(*instance));
    auto it = node_subscriptions_.find(instance_type_idx);
    if (it != node_subscriptions_.end())
    {
        auto &instances_vec = it->second.instances;
        instances_vec.erase(std::remove(instances_vec.begin(), instances_vec.end(), instance), instances_vec.end());
    }
}
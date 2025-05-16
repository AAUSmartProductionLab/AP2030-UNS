#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include "utils.h"
#include <iostream>
#include <set>

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
        if (handler.subscribed)
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

    std::map<std::string, std::vector<MqttSubBase *>> topic_to_instances_map;
    std::map<std::string, int> topic_to_max_qos;

    for (const auto &[type_idx, type_subscription_info] : node_subscriptions_)
    {
        for (MqttSubBase *instance : type_subscription_info.instances)
        {
            if (!instance)
                continue;

            for (const auto &[key, topic_obj] : instance->topics_) // Accessing public topics_
            {
                const std::string &topic_str = topic_obj.getTopic(); // This is the fully formatted topic string
                if (topic_str.empty())
                    continue;

                topic_to_instances_map[topic_str].push_back(instance);

                int instance_qos = topic_obj.getQos();
                if (topic_to_max_qos.find(topic_str) == topic_to_max_qos.end() || instance_qos > topic_to_max_qos[topic_str])
                {
                    topic_to_max_qos[topic_str] = instance_qos;
                }
            }
        }
    }

    topic_handlers_.clear();
    int subscribed_count = 0;

    for (const auto &[topic_str, instances_for_topic] : topic_to_instances_map)
    {
        if (instances_for_topic.empty())
            continue;

        auto callback = [this, instances_copy = instances_for_topic](
                            const std::string &msg_topic, const json &msg, mqtt::properties props)
        {
            for (MqttSubBase *instance : instances_copy)
            {
                // MqttSubBase::processMessage will internally find the matching logical topic (key)
                instance->processMessage(msg_topic, msg, props);
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
        // handler.topic is the subscribed topic (can have wildcards)
        // msg_topic is the actual topic the message arrived on
        if (handler.subscribed && mqtt_utils::topicMatches(handler.topic, msg_topic))
        {
            handler.callback(msg_topic, payload, props);
            handled = true;
            // If multiple handlers match (e.g. overlapping wildcards), all will be called.
            // If only one should handle, the logic might need adjustment or ensure non-overlapping subscriptions.
        }
    }

    if (!handled)
    {
        // std::cout << "NodeMessageDistributor: Message on topic '" << msg_topic << "' was not handled." << std::endl;
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
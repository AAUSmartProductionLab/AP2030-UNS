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

// MODIFIED: Method signature and implementation
bool NodeMessageDistributor::subscribeToActiveNodes(const BT::Tree &tree, std::chrono::milliseconds timeout_per_subscription)
{
    if (!tree.rootNode())
    {
        std::cerr << "NodeMessageDistributor: Cannot subscribe, behavior tree has no root node." << std::endl;
        return true; // Or false, depending on desired behavior for an empty/invalid tree
    }

    std::set<std::string> active_node_instance_names;
    BT::applyRecursiveVisitor(tree.rootNode(),
                              [&active_node_instance_names](const BT::TreeNode *node)
                              {
                                  if (node)
                                  {
                                      active_node_instance_names.insert(node->name()); // Get instance name
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

            // Only consider instances whose BTNodeName is present in the active tree
            if (active_node_instance_names.find(instance->getBTNodeName()) == active_node_instance_names.end())
            {
                // Optional: Log that this instance is skipped
                // std::cout << "Skipping subscriptions for BT node instance '" << instance->getBTNodeName()
                //           << "' as it's not in the active tree." << std::endl;
                continue;
            }

            for (const auto &[key, topic_obj] : instance->topics_)
            {
                const std::string &topic_str = topic_obj.getTopic();
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
    std::vector<std::pair<mqtt::token_ptr, std::string>> subscription_tokens_with_topic;
    int attempted_subscriptions = 0;

    for (const auto &[topic_str, instances_for_topic] : topic_to_instances_map)
    {
        if (instances_for_topic.empty())
            continue;

        attempted_subscriptions++;
        auto callback = [this, instances_copy = instances_for_topic](
                            const std::string &msg_topic, const json &msg, mqtt::properties props)
        {
            for (MqttSubBase *instance : instances_copy)
            {
                instance->processMessage(msg_topic, msg, props);
            }
        };
        int qos = topic_to_max_qos[topic_str];

        topic_handlers_.push_back({topic_str, callback, qos, false});

        mqtt::token_ptr token = mqtt_client_.subscribe_topic(topic_str, qos); // Ensure this returns mqtt::token_ptr
        if (token)
        {
            subscription_tokens_with_topic.emplace_back(token, topic_str);
        }
        else
        {
            std::cerr << "NodeMessageDistributor: Failed to initiate subscription to topic '" << topic_str << "'" << std::endl;
        }
    }

    if (attempted_subscriptions == 0)
    {
        std::cout << "NodeMessageDistributor: No topics to subscribe to for active nodes." << std::endl;
        return true;
    }

    std::cout << "NodeMessageDistributor: Waiting for " << subscription_tokens_with_topic.size() << " MQTT subscription initiations to complete..." << std::endl;

    for (auto &token_pair : subscription_tokens_with_topic)
    {
        auto &token = token_pair.first;
        const std::string &topic_str = token_pair.second;

        auto handler_it = std::find_if(topic_handlers_.begin(), topic_handlers_.end(),
                                       [&](const TopicHandler &h)
                                       { return h.topic == topic_str; });

        if (handler_it == topic_handlers_.end())
        {
            std::cerr << "NodeMessageDistributor: Internal error, could not find handler for topic " << topic_str << " while waiting for token." << std::endl;
            continue;
        }

        if (token->wait_for(timeout_per_subscription))
        {
            if (token->get_return_code() == mqtt::SUCCESS)
            {
                handler_it->subscribed = true;
            }
            else
            {
                std::cerr << "NodeMessageDistributor: Subscription failed for topic '" << handler_it->topic
                          << "'. MQTT Reason Code: " << token->get_return_code() << ". Error message:" << token->get_error_message() << std::endl;
            }
        }
        else
        {
            std::cerr << "NodeMessageDistributor: Subscription timed out for topic '" << handler_it->topic << "'" << std::endl;
        }
    }

    long actual_subscribed_count = std::count_if(topic_handlers_.begin(), topic_handlers_.end(), [](const TopicHandler &h)
                                                 { return h.subscribed; });
    std::cout << "NodeMessageDistributor: " << actual_subscribed_count << " of " << attempted_subscriptions << " topic subscriptions are now active." << std::endl;

    return actual_subscribed_count == attempted_subscriptions;
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
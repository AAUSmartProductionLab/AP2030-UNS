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
    std::lock_guard<std::mutex> lock(handlers_mutex_);
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

bool NodeMessageDistributor::subscribeForActiveNodes(const BT::Tree &tree,
                                                     std::chrono::milliseconds timeout_per_subscription)
{
    if (!tree.rootNode())
    {
        std::cerr << "NodeMessageDistributor: Cannot subscribe, behavior tree has no root node." << std::endl;
        return false;
    }

    // Collect names of nodes in the active tree
    std::set<std::string> active_node_instance_names;
    BT::applyRecursiveVisitor(tree.rootNode(),
                              [&active_node_instance_names](const BT::TreeNode *node)
                              {
                                  if (node)
                                  {
                                      active_node_instance_names.insert(node->name());
                                  }
                              });

    // Build map of topics to node instances
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
                continue;
            }

            for (const auto &[key, topic_obj] : instance->getTopics())
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

    // Clear existing handlers and set up routing
    {
        std::lock_guard<std::mutex> lock(handlers_mutex_);
        topic_handlers_.clear();

        for (const auto &[topic_str, instances_for_topic] : topic_to_instances_map)
        {
            if (instances_for_topic.empty())
                continue;

            TopicHandler handler;
            handler.topic = topic_str;
            handler.instances = instances_for_topic;
            handler.qos = topic_to_max_qos[topic_str];
            handler.subscribed = false;
            topic_handlers_.push_back(handler);
        }
    }

    if (topic_handlers_.empty())
    {
        std::cout << "NodeMessageDistributor: No topics to subscribe to for active nodes." << std::endl;
        return true;
    }

    std::cout << "NodeMessageDistributor: Subscribing to " << topic_handlers_.size() << " specific topics..." << std::endl;

    // Subscribe to each topic
    std::vector<std::pair<mqtt::token_ptr, std::string>> subscription_tokens;

    for (const auto &handler : topic_handlers_)
    {
        try
        {
            auto token = mqtt_client_.subscribe_topic(handler.topic, handler.qos);
            if (token)
            {
                subscription_tokens.emplace_back(token, handler.topic);
            }
            else
            {
                std::cerr << "  Failed to initiate subscription to: " << handler.topic << std::endl;
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << "  Exception subscribing to " << handler.topic << ": " << e.what() << std::endl;
        }
    }

    // Wait for all subscriptions to complete
    int success_count = 0;
    for (auto &[token, topic_str] : subscription_tokens)
    {
        if (token->wait_for(timeout_per_subscription))
        {
            if (token->get_return_code() == mqtt::SUCCESS)
            {
                std::cout << "  Subscribed: " << topic_str << std::endl;
                success_count++;

                // Mark as subscribed
                std::lock_guard<std::mutex> lock(handlers_mutex_);
                for (auto &h : topic_handlers_)
                {
                    if (h.topic == topic_str)
                    {
                        h.subscribed = true;
                        break;
                    }
                }
            }
            else
            {
                std::cerr << "  Subscription failed for: " << topic_str << std::endl;
            }
        }
        else
        {
            std::cerr << "  Subscription timed out for: " << topic_str << std::endl;
        }
    }

    std::cout << "NodeMessageDistributor: Subscription complete: "
              << success_count << "/" << topic_handlers_.size() << " topics" << std::endl;

    return success_count == static_cast<int>(topic_handlers_.size());
}

void NodeMessageDistributor::handle_incoming_message(const std::string &msg_topic,
                                                     const json &payload,
                                                     mqtt::properties props)
{
    // Route message to registered handlers
    // Note: We rely on MQTT broker retained messages instead of local caching
    std::lock_guard<std::mutex> lock(handlers_mutex_);
    bool handled = false;
    for (const auto &handler : topic_handlers_)
    {
        // handler.topic is the subscribed topic (can have wildcards)
        // msg_topic is the actual topic the message arrived on
        if (handler.subscribed && mqtt_utils::topicMatches(handler.topic, msg_topic))
        {
            handler.routeMessage(msg_topic, payload, props);
            handled = true;
            // If multiple handlers match (e.g. overlapping wildcards), all will be called.
        }
    }

    if (!handled)
    {
        // Message not handled - this is normal for messages from wildcard subscriptions
        // that don't have a specific handler (e.g., CMD topics when we only care about DATA)
    }
}

void NodeMessageDistributor::registerDerivedInstance(MqttSubBase *instance)
{
    if (!instance)
        return;

    std::type_index instance_type_idx(typeid(*instance));
    node_subscriptions_[instance_type_idx].instances.push_back(instance);
}

bool NodeMessageDistributor::registerLateInitializingNode(MqttSubBase *instance,
                                                          std::chrono::milliseconds timeout)
{
    if (!instance)
        return false;

    // First, register the instance in our data structures
    registerDerivedInstance(instance);

    // Get the topics this node wants to subscribe to
    const auto &topics = instance->getTopics();
    if (topics.empty())
    {
        std::cerr << "Late-initializing node " << instance->getBTNodeName()
                  << " has no topics configured" << std::endl;
        return false;
    }

    bool all_success = true;

    for (const auto &[key, topic_obj] : topics)
    {
        std::string topic_str = topic_obj.getTopic();
        int qos = topic_obj.getQos();

        // Check if handler already exists for this topic and add instance if so
        bool handler_exists = false;
        {
            std::lock_guard<std::mutex> lock(handlers_mutex_);
            for (auto &h : topic_handlers_)
            {
                if (h.topic == topic_str)
                {
                    handler_exists = true;
                    // Check if instance is already in the list
                    bool instance_already_registered = false;
                    for (MqttSubBase* existing : h.instances)
                    {
                        if (existing == instance)
                        {
                            instance_already_registered = true;
                            break;
                        }
                    }
                    if (!instance_already_registered)
                    {
                        // ADD the new instance to the existing handler
                        h.instances.push_back(instance);
                        std::cout << "  Added late-init instance to existing handler for: " << topic_str << std::endl;
                    }
                    break;
                }
            }

            if (!handler_exists)
            {
                // Add new handler for this late-initializing node
                TopicHandler handler;
                handler.topic = topic_str;
                handler.instances.push_back(instance);
                handler.qos = qos;
                handler.subscribed = false;
                topic_handlers_.push_back(handler);
            }
        }

        // Always (re-)subscribe to trigger retained message delivery
        // Re-subscribing is idempotent but causes broker to resend retained message
        try
        {
            std::cout << "Late-init node " << instance->getBTNodeName()
                      << (handler_exists ? " re-subscribing to: " : " subscribing to: ") 
                      << topic_str << std::endl;

            auto token = mqtt_client_.subscribe_topic(topic_str, qos);
            if (token)
            {
                bool completed = token->wait_for(timeout);
                if (!completed)
                {
                    std::cerr << "Timeout subscribing to " << topic_str << std::endl;
                    all_success = false;
                }
                else if (token->get_return_code() == mqtt::SUCCESS)
                {
                    // Mark as subscribed
                    std::lock_guard<std::mutex> lock(handlers_mutex_);
                    for (auto &h : topic_handlers_)
                    {
                        if (h.topic == topic_str)
                        {
                            h.subscribed = true;
                            break;
                        }
                    }
                }
                else
                {
                    std::cerr << "Subscription failed for " << topic_str << std::endl;
                    all_success = false;
                }
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << "Exception subscribing to " << topic_str << ": " << e.what() << std::endl;
            all_success = false;
        }
    }

    return all_success;
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
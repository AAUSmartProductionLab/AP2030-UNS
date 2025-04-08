#include "mqtt/subscription_manager.h"
#include "mqtt/proxy.h"
#include <iostream>
#include <fstream>

SubscriptionManager::SubscriptionManager(Proxy &proxy) : proxy_(proxy)
{
    // Register this as the callback for the proxy
    proxy.set_callback(*this);
}

SubscriptionManager::~SubscriptionManager()
{
    // Cleanup if needed
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
            if (topic == handler.topic) //|| topic.find(handler.topic) != std::string::npos
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
        std::cout << msg->get_topic() << " " << msg->get_payload() << std::endl;
        std::cerr << "Error processing message: " << e.what() << std::endl;
    }
}

void SubscriptionManager::register_topic_handler(
    const std::string &topic,
    std::function<void(const json &, mqtt::properties)> callback)
{
    topic_handlers_.push_back({topic, callback});
    std::cout << "Registered topic handler for topic: " << topic << std::endl;

    // Create and store the listener
    auto listener = std::make_shared<subscription_listener>(topic, *this);
    subscription_listeners_.push_back(listener);
    proxy_.subscribe_with_listener(topic, 0, nullptr, listener);
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

void SubscriptionManager::connection_lost(const std::string &cause)
{
    std::cout << "Connection lost: " << cause << std::endl;
    // Connection will be handled by Proxy's reconnect mechanism
}

void SubscriptionManager::delivery_complete(mqtt::delivery_token_ptr token)
{
    // Optional implementation
}

void subscription_listener::on_failure(const mqtt::token &tok)
{
    std::cout << "Subscription failed for topic: " << topic_ << std::endl;
    // Retry subscription after failure
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    manager_.retry_subscription(topic_);
}

void subscription_listener::on_success(const mqtt::token &tok)
{
    std::cout << "Successfully subscribed to topic: " << topic_ << std::endl;
}

void SubscriptionManager::retry_subscription(const std::string &topic)
{
    std::cout << "Retrying subscription for topic: " << topic << std::endl;
    auto listener = std::make_shared<subscription_listener>(topic, *this);
    subscription_listeners_.push_back(listener);
    proxy_.subscribe_with_listener(topic, 0, nullptr, listener);
}

void SubscriptionManager::resubscribe_all_topics()
{
    std::cout << "Resubscribing to all topics after reconnection" << std::endl;
    for (const auto &handler : topic_handlers_)
    {
        auto listener = std::make_shared<subscription_listener>(handler.topic, *this);
        subscription_listeners_.push_back(listener);
        proxy_.subscribe_with_listener(handler.topic, 0, nullptr, listener);
    }
}
#pragma once

#include <nlohmann/json.hpp>
#include <mutex>
#include <string>
#include <functional>

// Forward declarations
namespace BT
{
    class BehaviorTreeFactory;
}

class Proxy;
class SubscriptionManager;

namespace mqtt
{
    struct properties;
}

using json = nlohmann::json;

/**
 * @brief Base class for MQTT-enabled nodes
 */
class MqttNodeBase
{
protected:
    Proxy &proxy_;
    std::string uns_topic_;
    std::string response_schema_path_;
    std::mutex mutex_;

    static SubscriptionManager *subscription_manager_;

public:
    MqttNodeBase(Proxy &proxy,
                 const std::string &uns_topic,
                 const std::string &response_schema_path);

    virtual ~MqttNodeBase() = default;

    // Called when a message arrives
    virtual void handleMessage(const json &msg, mqtt::properties props);

    // Check if this node is interested in a message
    virtual bool isInterestedIn(const std::string &field, const json &value);

    // Callback when a relevant message arrives
    virtual void callback(const json &msg, mqtt::properties props) = 0;

    // Set the subscription manager for all nodes
    static void setSubscriptionManager(SubscriptionManager *manager);

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        SubscriptionManager &subscription_manager,
        const std::string &node_name,
        const std::string &topic,
        const std::string &response_schema_path,
        Proxy &proxy);
};
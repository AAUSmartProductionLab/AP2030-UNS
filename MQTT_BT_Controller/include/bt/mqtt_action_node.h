#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h> // Add this include
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include <atomic>
#include <mutex>
#include <string>
#include "mqtt/subscription_manager.h" // Include full header, not just forward declaration
#include "mqtt/subscription_manager_client.h"

// Forward declarations
class Proxy;

using nlohmann::json;

/**
 * @brief Base class for MQTT-based behavior tree action nodes
 */
class MqttActionNode : public BT::StatefulActionNode, public SubscriptionManagerClient
{
protected:
    Proxy &proxy_;
    const std::string uns_topic_;
    const std::string request_schema_path_;
    const std::string response_schema_path_;

    // Protected state
    BT::NodeStatus state;
    std::atomic<bool> state_updated_{false};
    std::mutex state_mutex_;

    static SubscriptionManager *subscription_manager_;

public:
    MqttActionNode(const std::string &name, const BT::NodeConfig &config, Proxy &proxy,
                   const std::string &uns_topic,
                   const std::string &request_schema_path = "",
                   const std::string &response_schema_path = "");

    virtual ~MqttActionNode();

    // Static method to set the subscription manager
    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        SubscriptionManager &subscription_manager,
        const std::string &node_name,
        const std::string &topic,
        const std::string &response_schema_path,
        Proxy &proxy)
    {
        // Set the subscription manager for all node instances
        setSubscriptionManager(&subscription_manager);

        // Register with subscription manager
        subscription_manager.registerNodeType<DerivedNode>(topic, response_schema_path);

        // Register with behavior tree factory
        factory.registerNodeType<DerivedNode>(node_name, std::ref(proxy));
    }

    static void setSubscriptionManager(SubscriptionManager *manager);
    static void emitWakeUpSignal();
    // Default ports implementation
    static BT::PortsList providedPorts();

    // Internal message handling method used by the subscription manager
    void handleMessage(const json &msg, mqtt::properties props);

    // Virtual method to filter messages
    virtual bool isInterestedIn(const std::string &field, const json &value);

    // Callback method to be implemented by derived classes
    virtual void callback(const json &msg, mqtt::properties props) = 0;

    // Create message to be implemented by derived classes
    virtual json createMessage() = 0;

    // BT::StatefulActionNode interface implementation
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;
};
#pragma once

#include <behaviortree_cpp/action_node.h>
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include <atomic>
#include <mutex>
#include <string>

// Forward declarations
class Proxy;
class SubscriptionManager;

using nlohmann::json;

/**
 * @brief Base class for MQTT-based behavior tree action nodes
 */
class MqttActionNode : public BT::StatefulActionNode
{
protected:
    Proxy &proxy_;
    const std::string topic_base_;
    const std::string request_schema_path_;
    const std::string response_schema_path_;

    // Protected state
    BT::NodeStatus state;
    std::atomic<bool> state_updated_{false};
    std::mutex state_mutex_;

    static SubscriptionManager *subscription_manager_;

public:
    MqttActionNode(const std::string &name, const BT::NodeConfig &config, Proxy &proxy,
                   const std::string &topic_base,
                   const std::string &request_schema_path = "",
                   const std::string &response_schema_path = "");

    virtual ~MqttActionNode();

    // Static method to set the subscription manager
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
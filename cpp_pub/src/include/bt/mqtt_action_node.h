#pragma once

#include <mutex>
#include <atomic>
#include <functional>
#include <behaviortree_cpp/action_node.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtttopic.h"
#include "mqtt/proxy.h"

// Forward declaration
class NodeTypeSubscriptionManager;

using nlohmann::json;

/**
 * @brief Base class for MQTT-based behavior tree action nodes
 */
class MqttActionNode : public BT::StatefulActionNode
{
protected:
    Request topic;
    Proxy &bt_proxy_;
    BT::NodeStatus state;
    std::mutex state_mutex_;
    std::atomic<bool> state_updated_{false};
    static NodeTypeSubscriptionManager *subscription_manager_;

public:
    MqttActionNode(const std::string &name,
                   const BT::NodeConfig &config,
                   Proxy &bt_proxy,
                   const std::string &topic_base,
                   const std::string &pub_schema_path,
                   const std::string &sub_schema_path,
                   int qos = 1);

    virtual ~MqttActionNode();

    static void setSubscriptionManager(NodeTypeSubscriptionManager *manager);

    // New method to handle messages from the subscription manager
    virtual void handleMessage(const json &msg, mqtt::properties props);
    virtual bool isInterestedIn(const std::string &field, const json &value);

    // Existing methods remain the same...
    static BT::PortsList providedPorts();
    virtual void callback(const json &msg, mqtt::properties props);
    virtual json createMessage() = 0;
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;
};
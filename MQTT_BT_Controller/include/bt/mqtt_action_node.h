#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_node_base.h"
#include "mqtt/subscription_manager.h" // Include this to resolve incomplete type issue

// Forward declarations
class Proxy;

using nlohmann::json;

/**
 * @brief Base class for MQTT-based behavior tree action nodes
 */
class MqttActionNode : public BT::StatefulActionNode, public MqttNodeBase
{
protected:
    const std::string request_schema_path_;

public:
    MqttActionNode(const std::string &name,
                   const BT::NodeConfig &config,
                   Proxy &proxy,
                   const std::string &uns_topic,
                   const std::string &request_schema_path = "",
                   const std::string &response_schema_path = "");

    virtual ~MqttActionNode();

    // Default ports implementation
    static BT::PortsList providedPorts();

    // Create message to be implemented by derived classes
    virtual json createMessage() = 0;

    // Override the virtual callback method from base class
    virtual void callback(const json &msg, mqtt::properties props) override;

    // BT::StatefulActionNode interface implementation
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;
};
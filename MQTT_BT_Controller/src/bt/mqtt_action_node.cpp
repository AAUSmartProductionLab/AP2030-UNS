#include "bt/mqtt_action_node.h"
#include "mqtt/subscription_manager.h"
#include "mqtt/proxy.h"
#include "common_constants.h"

#include <iostream>
#include <condition_variable>
#include <mutex>

MqttActionNode::MqttActionNode(const std::string &name,
                               const BT::NodeConfig &config,
                               Proxy &proxy,
                               const std::string &request_topic,
                               const std::string &response_topic,
                               const std::string &request_schema_path,
                               const std::string &response_schema_path,
                               const bool &retain,
                               const int &qos)
    : BT::StatefulActionNode(name, config),
      MqttSubBase(proxy, response_topic, response_schema_path),
      MqttPubBase(proxy, request_topic, request_schema_path, qos, retain)
{
    // Registration happens in derived classes
}

MqttActionNode::~MqttActionNode()
{
    // Optional cleanup if needed
}

// Default implementation of providedPorts - derived classes should override
BT::PortsList MqttActionNode::providedPorts()
{
    return {};
}

void MqttActionNode::callback(const json &msg, mqtt::properties props)
{
    // Base implementation - should be overridden by derived classes
    std::cout << "Base callback called - this should be overridden!" << std::endl;
}

BT::NodeStatus MqttActionNode::onStart()
{
    // Create the message to send
    publish(createMessage());

    return BT::NodeStatus::RUNNING;
}

BT::NodeStatus MqttActionNode::onRunning()
{
    return status();
}

void MqttActionNode::onHalted()
{
    // Clean up when the node is halted
    std::cout << "MQTT action node halted" << std::endl;
    // Additional cleanup as needed
}

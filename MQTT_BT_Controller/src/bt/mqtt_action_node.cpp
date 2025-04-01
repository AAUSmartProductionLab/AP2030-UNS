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
                               const std::string &uns_topic,
                               const std::string &request_schema_path,
                               const std::string &response_schema_path)
    : BT::StatefulActionNode(name, config),
      MqttNodeBase(proxy, uns_topic, response_schema_path),
      request_schema_path_(request_schema_path)
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
    json message = createMessage();

    // Extract subtopic from the request schema and register it with the manager
    std::string subtopic = "";
    if (!request_schema_path_.empty() && subscription_manager_)
    {
        subtopic = subscription_manager_->extractSubtopicFromSchema(request_schema_path_);
    }

    // Send the message with the proper subtopic
    std::string publish_topic = uns_topic_ + "/CMD" + subtopic;
    proxy_.publish(publish_topic, message.dump(), 2, false); // TODO QOS and retention should ideally be parameters

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

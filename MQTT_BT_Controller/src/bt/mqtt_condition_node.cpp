#include "bt/mqtt_condition_node.h"
#include "mqtt/node_message_distributor.h"
#include "common_constants.h"
#include <iostream>

MqttConditionNode::MqttConditionNode(const std::string &name,
                                     const BT::NodeConfig &config,
                                     MqttClient &mqtt_client,
                                     const std::string &response_topic,
                                     const std::string &response_schema_path)
    : BT::ConditionNode(name, config),
      MqttSubBase(mqtt_client, response_topic, response_schema_path)

{
    // Registration happens in derived classes
}

MqttConditionNode::~MqttConditionNode()
{
    // Optional cleanup
}

BT::PortsList MqttConditionNode::providedPorts()
{
    return {};
}

void MqttConditionNode::callback(const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(mutex_);
    latest_msg_ = msg;
    std::cout << "Condition node received message" << std::endl;
}

BT::NodeStatus MqttConditionNode::tick()
{
    return BT::NodeStatus::SUCCESS; // Default implementation
}

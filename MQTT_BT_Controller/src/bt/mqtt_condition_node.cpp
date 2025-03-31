#include "bt/mqtt_condition_node.h"
#include "mqtt/subscription_manager.h"
#include "common_constants.h"
#include <iostream>

// Initialize the static member
SubscriptionManager *MqttConditionNode::subscription_manager_ = nullptr;

MqttConditionNode::MqttConditionNode(const std::string &name,
                                     const BT::NodeConfig &config,
                                     Proxy &proxy,
                                     const std::string &uns_topic,
                                     const std::string &response_schema_path)
    : BT::ConditionNode(name, config),
      proxy_(proxy),
      uns_topic_(uns_topic),
      response_schema_path_(response_schema_path)
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
    latest_msg_ = msg;
}

BT::NodeStatus MqttConditionNode::tick()
{
    return BT::NodeStatus::SUCCESS; // Default implementation
}

void MqttConditionNode::setSubscriptionManager(SubscriptionManager *manager)
{
    subscription_manager_ = manager;
}

void MqttConditionNode::handleMessage(const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(value_mutex_);
    latest_msg_ = msg;
}

bool MqttConditionNode::isInterestedIn(const std::string &field, const json &value)
{
    std::cout << "Base isInterestedIn called - this should be overridden!" << std::endl;
    return true;
}

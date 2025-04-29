#include "bt/mqtt_sync_sub_node.h"
#include "mqtt/node_message_distributor.h"
#include <iostream>

MqttSyncSubNode::MqttSyncSubNode(const std::string &name,
                                 const BT::NodeConfig &config,
                                 MqttClient &mqtt_client,
                                 const std::string &response_topic,
                                 const std::string &response_schema_path)
    : BT::ConditionNode(name, config),
      MqttSubBase(mqtt_client, response_topic, response_schema_path)

{
    // Registration happens in derived classes
}

MqttSyncSubNode::~MqttSyncSubNode()
{
    // Optional cleanup
}

BT::PortsList MqttSyncSubNode::providedPorts()
{
    return {};
}

void MqttSyncSubNode::callback(const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(mutex_);
    latest_msg_ = msg;
    std::cout << "Sync subscription node received message" << std::endl;
}

BT::NodeStatus MqttSyncSubNode::tick()
{
    return BT::NodeStatus::SUCCESS; // Default implementation
}

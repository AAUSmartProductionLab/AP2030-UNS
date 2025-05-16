#include "bt/mqtt_async_sub_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include "utils.h"
#include <iostream>
#include <condition_variable>
#include <mutex>

MqttAsyncSubNode::MqttAsyncSubNode(const std::string &name,
                                   const BT::NodeConfig &config,
                                   MqttClient &mqtt_client,
                                   const mqtt_utils::Topic &response_topic)
    : BT::StatefulActionNode(name, config),
      MqttSubBase(mqtt_client, {{"response", response_topic}})
{
    // Registration happens in derived classes
}

MqttAsyncSubNode::~MqttAsyncSubNode()
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->unregisterInstance(this);
    }
}

// Default implementation of providedPorts - derived classes should override
BT::PortsList MqttAsyncSubNode::providedPorts()
{
    return {};
}

BT::NodeStatus MqttAsyncSubNode::onStart()
{
    return BT::NodeStatus::RUNNING;
}

BT::NodeStatus MqttAsyncSubNode::onRunning()
{
    return status();
}

void MqttAsyncSubNode::onHalted()
{
    std::cout << this->name() << "halted" << std::endl;
}

void MqttAsyncSubNode::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(mutex_);
        // Update state based on message content
        if (status() == BT::NodeStatus::RUNNING)
        {
            setStatus(BT::NodeStatus::SUCCESS);
            emitWakeUpSignal();
        }
        else
        {
            std::cout << "Message the node is not running" << std::endl;
        }
    }
}
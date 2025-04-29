#include "bt/mqtt_async_sub_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"

#include <iostream>
#include <condition_variable>
#include <mutex>

MqttAsyncSubNode::MqttAsyncSubNode(const std::string &name,
                                   const BT::NodeConfig &config,
                                   MqttClient &mqtt_client,
                                   const std::string &response_topic,
                                   const std::string &response_schema_path,
                                   const bool &retain,
                                   const int &qos)
    : BT::StatefulActionNode(name, config),
      MqttSubBase(mqtt_client, response_topic, response_schema_path)
{
    // Registration happens in derived classes
}

MqttAsyncSubNode::~MqttAsyncSubNode()
{
    // Optional cleanup if needed
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

void MqttAsyncSubNode::callback(const json &msg, mqtt::properties props)
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

bool MqttAsyncSubNode::isInterestedIn(const json &msg)
{
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (this->response_schema_validator_ && status() == BT::NodeStatus::RUNNING)
        {
            try
            {
                this->response_schema_validator_->validate(msg);
                return true;
            }
            catch (const std::exception &e)
            {
                std::cerr << "JSON validation failed: " << e.what() << std::endl;
            }
        }
        return false;
    }
}
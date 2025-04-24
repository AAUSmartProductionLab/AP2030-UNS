#include "bt/mqtt_async_sub_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include "common_constants.h"

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
    // Clean up when the node is halted
    std::cout << "MQTT action node halted" << std::endl;
    // Additional cleanup as needed
}

// Standard implementation based on PackML override this if needed
void MqttAsyncSubNode::callback(const json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(mutex_);
        // Update state based on message content
        if (status() == BT::NodeStatus::RUNNING)
        {
            if (msg["State"] == "ABORTED" || msg["State"] == "STOPPED")
            {
                current_command_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::FAILURE);
            }
            else if (msg["State"] == "COMPLETE")
            {
                std::cout << "State is COMPLETE" << std::endl;
                current_command_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::SUCCESS);
            }
            else if (msg["State"] == "HELD" || msg["State"] == "SUSPENDED" || msg["State"] == "EXECUTED")
            {
                std::cout << "State is HELD, SUSPENDED or Executing" << std::endl;
                // No need to set RUNNING again if already running
            }
            emitWakeUpSignal();
        }
        else
        {
            std::cout << "Message doesn't contain 'state' field" << std::endl;
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
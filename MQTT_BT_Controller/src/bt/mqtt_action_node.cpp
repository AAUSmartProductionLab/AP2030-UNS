#include "bt/mqtt_action_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include "common_constants.h"

#include <iostream>
#include <condition_variable>
#include <mutex>

MqttActionNode::MqttActionNode(const std::string &name,
                               const BT::NodeConfig &config,
                               MqttClient &mqtt_client,
                               const std::string &request_topic,
                               const std::string &response_topic,
                               const std::string &request_schema_path,
                               const std::string &response_schema_path,
                               const bool &retain,
                               const int &qos)
    : BT::StatefulActionNode(name, config),
      MqttSubBase(mqtt_client, response_topic, response_schema_path),
      MqttPubBase(mqtt_client, request_topic, request_schema_path, qos, retain)
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

// Standard implementation based on PackML override this if needed
void MqttActionNode::callback(const json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Update state based on message content
        if (msg.contains("State"))
        {
            if (msg["State"] == "ABORTED" || msg["State"] == "STOPPED")
            {
                current_command_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::FAILURE);
                emitWakeUpSignal();
            }
            else if (msg["State"] == "COMPLETE")
            {
                current_command_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::SUCCESS);
                emitWakeUpSignal();
            }
            else if (msg["State"] == "HELD" || msg["State"] == "SUSPENDED" || msg["State"] == "EXECUTED")
            {
                std::cout << "State is HELD, SUSPENDED or Executing" << std::endl;
                // No need to set RUNNING again if already running
                emitWakeUpSignal();
            }
        }
        else
        {
            std::cout << "Message doesn't contain 'state' field" << std::endl;
        }
    }
}

bool MqttActionNode::isInterestedIn(const std::string &field, const json &value)
{
    if (field == "CommandUuid" && value.is_string())
    {
        bool interested = (value.get<std::string>() == current_command_uuid_);
        return interested;
    }
    return false;
}
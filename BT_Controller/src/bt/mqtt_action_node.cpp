#include "bt/mqtt_action_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include "mqtt/utils.h"
#include <iostream>
#include <condition_variable>
#include <mutex>

MqttActionNode::MqttActionNode(const std::string &name,
                               const BT::NodeConfig &config,
                               MqttClient &mqtt_client,
                               const mqtt_utils::Topic &request_topic,
                               const mqtt_utils::Topic &response_topic)
    : BT::StatefulActionNode(name, config),
      MqttSubBase(mqtt_client, response_topic),
      MqttPubBase(mqtt_client, request_topic)
{
    // Registration happens in derived classes
}
MqttActionNode::MqttActionNode(const std::string &name,
                               const BT::NodeConfig &config,
                               MqttClient &mqtt_client,
                               const mqtt_utils::Topic &request_topic,
                               const mqtt_utils::Topic &response_topic,
                               const mqtt_utils::Topic &halt_topic)
    : StatefulActionNode(name, config),
      MqttPubBase(mqtt_client, request_topic, halt_topic),
      MqttSubBase(mqtt_client, response_topic)
{
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
        if (status() == BT::NodeStatus::RUNNING && msg.contains("Uuid") && msg["Uuid"] == current_uuid_)
        {
            if (msg["State"] == "ABORTED" || msg["State"] == "STOPPED")
            {
                current_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::FAILURE);
            }
            else if (msg["State"] == "COMPLETE")
            {
                std::cout << "State is COMPLETE" << std::endl;
                current_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::SUCCESS);
            }
            else if (msg["State"] == "HELD" || msg["State"] == "SUSPENDED" || msg["State"] == "EXECUTED")
            {
                std::cout << "State is HELD, SUSPENDED or Executing" << std::endl;
                // No need to set RUNNING again if already running
            }
        }
        else
        {
            std::cout << "Not interested in message" << std::endl;
        }
        emitWakeUpSignal();
    }
}
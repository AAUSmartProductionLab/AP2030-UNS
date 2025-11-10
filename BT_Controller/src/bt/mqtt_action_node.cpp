#include "bt/mqtt_action_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_client.h"
#include "utils.h"
#include <iostream>
#include <condition_variable>
#include <mutex>

void MqttActionNode::initialize()
{
    // Call the virtual function - safe because construction is complete
    initializeTopicsFromAAS();

    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

MqttActionNode::~MqttActionNode()
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->unregisterInstance(this);
    }
}

BT::NodeStatus MqttActionNode::onStart()
{
    // Create the message to send
    publish("input", createMessage());

    return BT::NodeStatus::RUNNING;
}

BT::NodeStatus MqttActionNode::onRunning()
{
    return status();
}

nlohmann::json MqttActionNode::createMessage()
{
    // Default implementation
    nlohmann::json message;
    BT::Expected<std::string> uuid = this->getInput<std::string>("Uuid");
    if (uuid.has_value())
    {
        current_uuid_ = uuid.value();
        message["Uuid"] = current_uuid_;
        return message;
    }
    return nlohmann::json();
}

void MqttActionNode::onHalted()
{
    // Clean up when the node is halted
    std::cout << "MQTT action node halted" << std::endl;
    // Additional cleanup as needed
}

// Standard implementation based on PackML override this if needed
void MqttActionNode::callback(const std::string &topic_key, const nlohmann::json &msg, mqtt::properties props)
{
    // Check if the message is valid
    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(mutex_);
        // Update state based on message content
        if (status() == BT::NodeStatus::RUNNING)
        {
            if (msg["Uuid"] == current_uuid_)
            {

                if (msg["State"] == "FAILURE")
                {
                    current_uuid_ = "";
                    setStatus(BT::NodeStatus::FAILURE);
                }
                else if (msg["State"] == "SUCCESS")
                {
                    current_uuid_ = "";
                    setStatus(BT::NodeStatus::SUCCESS);
                }
                else if (msg["State"] == "RUNNING")
                {
                    setStatus(BT::NodeStatus::RUNNING);
                }
            }
            emitWakeUpSignal();
        }
    }
}
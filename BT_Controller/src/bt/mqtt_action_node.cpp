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

    // Only register if we have topics initialized
    if (topics_initialized_ && MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

bool MqttActionNode::ensureInitialized()
{
    if (topics_initialized_)
    {
        return true;
    }

    // Try lazy initialization
    std::cout << "Node '" << this->name() << "' attempting lazy initialization..." << std::endl;
    initializeTopicsFromAAS();

    if (topics_initialized_ && MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        std::cout << "Node '" << this->name() << "' lazy initialized successfully" << std::endl;
    }
    else if (!topics_initialized_)
    {
        std::cerr << "Node '" << this->name() << "' lazy initialization FAILED - topics not configured" << std::endl;
    }

    return topics_initialized_;
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
    // Ensure lazy initialization is done
    if (!ensureInitialized())
    {
        auto asset = getInput<std::string>("Asset");
        std::cerr << "Node '" << this->name() << "' FAILED - could not initialize. "
                  << "Asset=" << (asset.has_value() ? asset.value() : "<not set>") << std::endl;
        return BT::NodeStatus::FAILURE;
    }
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
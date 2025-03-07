#include "bt/mqtt_action_node.h"
#include <iostream>

// Base topic for all MQTT communications
extern const std::string BASE_TOPIC;

MqttActionNode::MqttActionNode(const std::string &name,
                               const BT::NodeConfig &config,
                               Proxy &bt_proxy,
                               const std::string &topic_base,
                               const std::string &pub_schema_path,
                               const std::string &sub_schema_path,
                               int qos)
    : BT::StatefulActionNode(name, config),
      bt_proxy_(bt_proxy),
      topic(topic_base, pub_schema_path, sub_schema_path, qos,
            std::bind(&MqttActionNode::callback, this, std::placeholders::_1, std::placeholders::_2))
{
    if (bt_proxy_.is_connected())
    {
        topic.register_callback(bt_proxy);
        topic.subscribe(bt_proxy);
    }
}

BT::PortsList MqttActionNode::providedPorts()
{
    return {};
}

void MqttActionNode::callback(const json &msg, mqtt::properties props)
{

    // Use mutex to protect shared state
    {
        std::lock_guard<std::mutex> lock(state_mutex_);

        // Update state based on message content
        if (msg.contains("state"))
        {
            if (msg["state"] == "failure")
            {
                std::cout << "State updated to FAILURE" << std::endl;
                state = BT::NodeStatus::FAILURE;
            }
            else if (msg["state"] == "successful")
            {
                std::cout << "State updated to SUCCESS" << std::endl;
                state = BT::NodeStatus::SUCCESS;
            }
            else if (msg["state"] == "running")
            {
                std::cout << "State updated to RUNNING" << std::endl;
                state = BT::NodeStatus::RUNNING;
            }
            else
            {
                std::cout << "Unknown state value: " << msg["state"] << std::endl;
            }

            // Use explicit memory ordering when setting the flag
            state_updated_.store(true, std::memory_order_seq_cst);
        }
        else
        {
            std::cout << "Message doesn't contain 'state' field" << std::endl;
        }
    }
}

BT::NodeStatus MqttActionNode::onStart()
{
    try
    {
        json message = createMessage();
        topic.publish(bt_proxy_, message);
        state = BT::NodeStatus::RUNNING;
    }
    catch (const std::exception &e)
    {
        std::cout << "Exception in onStart(): " << e.what() << std::endl;
        state = BT::NodeStatus::FAILURE;
    }
    catch (...)
    {
        std::cout << "Unknown exception in onStart()" << std::endl;
        state = BT::NodeStatus::FAILURE;
    }
    return state;
}

BT::NodeStatus MqttActionNode::onRunning()
{
    // Use mutex for accessing shared state
    std::lock_guard<std::mutex> lock(state_mutex_);

    // Use explicit memory ordering when loading the flag
    bool updated = state_updated_.load(std::memory_order_acquire);
    if (updated)
    {
        // We got an update from the callback, reset the flag
        state_updated_.store(false, std::memory_order_seq_cst);
        // Return the updated state (SUCCESS/FAILURE/RUNNING)
        return state;
    }
    else
    {
        // No update received yet, continue in RUNNING state
        return BT::NodeStatus::RUNNING;
    }
}

void MqttActionNode::onHalted()
{
    std::cout << "MQTT action node halted" << std::endl;
}

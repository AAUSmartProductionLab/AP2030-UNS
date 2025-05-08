#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/utils.h"
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class StationStartNode : public MqttActionNode
{
public:
    StationStartNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                     const mqtt_utils::Topic &request_topic,
                     const mqtt_utils::Topic &response_topic,
                     const mqtt_utils::Topic &halt_topic)
        : MqttActionNode(name, config, bt_mqtt_client,
                         request_topic, response_topic, halt_topic)
    {
        response_topic_.setTopic(getFormattedTopic(response_topic.getPattern(), config));
        request_topic_.setTopic(getFormattedTopic(request_topic_.getPattern(), config));
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }
    static BT::PortsList providedPorts()
    {
        return {
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Station",
                "{_Station}",
                "The station to register with"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Uuid",
                "{_ID}",
                "UUID for the command to execute")};
    }
    json createMessage() override
    {
        std::cout << "Creating message in StationStartNode" << std::endl;
        json message;
        BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
        if (uuid.has_value())
        {
            current_uuid_ = uuid.value();
            message["Uuid"] = current_uuid_;
            return message;
        }
        return json();
    }
    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
    {
        std::vector<std::string> replacements;
        BT::Expected<std::string> station = getInput<std::string>("Station");
        std::string command = "Start";
        if (station.has_value())
        {
            replacements.push_back(station.value());
            replacements.push_back(command);
            return mqtt_utils::formatWildcardTopic(pattern, replacements);
        }
        return pattern;
    }
    bool isInterestedIn(const json &msg) override
    {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (response_topic_.validateMessage(msg) && status() == BT::NodeStatus::RUNNING)
            {
                return true;
            }
            return false;
        }
    }
    void onHalted() override
    {
        json message;
        message["Uuid"] = current_uuid_;
        publish(message, halt_topic_);
    }
    void callback(const json &msg, mqtt::properties props) override
    {
        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(mutex_);
            std::cout << "Received message: " << msg.dump() << std::endl;
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
                    else if (msg["State"] == "SUCCESSFUL")
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

private:
    // other private members
    mqtt_utils::Topic halt_topic_; // Add this line
};
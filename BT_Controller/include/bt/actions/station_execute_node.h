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
class StationExecuteNode : public MqttActionNode
{
public:
    StationExecuteNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                       const mqtt_utils::Topic &request_topic,
                       const mqtt_utils::Topic &response_topic)
        : MqttActionNode(name,
                         config,
                         bt_mqtt_client,
                         request_topic,
                         response_topic)
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
        return {BT::details::PortWithDefault<std::string>(
                    BT::PortDirection::INPUT,
                    "Station",
                    "{Station}",
                    "The station to register with"),
                BT::details::PortWithDefault<std::string>(
                    BT::PortDirection::INPUT,
                    "Command",
                    "Command",
                    "The command to execute on the station"),
                BT::details::PortWithDefault<std::string>(
                    BT::PortDirection::INPUT,
                    "Uuid",
                    "{_ID}",
                    "UUID for the command to execute")};
    }
    json createMessage() override
    {
        json message;
        auto uuid_result = getInput<std::string>("Uuid");

        if (uuid_result)
        {
            current_uuid_ = uuid_result.value();
        }
        else
        {
            // Handle the error - Uuid is missing
            std::cerr << "Error: Uuid not provided to StationExecuteNode. Error: "
                      << uuid_result.error() << std::endl;

            // Generate a new UUID as fallback or set empty
            current_uuid_ = mqtt_utils::generate_uuid();
            std::cerr << "Using generated UUID instead: " << current_uuid_ << std::endl;
        }
        message["Uuid"] = current_uuid_;
        return message;
    }
    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
    {
        std::vector<std::string> replacements;
        BT::Expected<std::string> station = getInput<std::string>("Station");
        BT::Expected<std::string> command = getInput<std::string>("Command");
        if (station.has_value() && command.has_value())
        {
            replacements.push_back(station.value());
            replacements.push_back(command.value());
            return mqtt_utils::formatWildcardTopic(pattern, replacements);
        }
        return pattern;
    }
    // Standard implementation based on PackML override this if needed
    void callback(const json &msg, mqtt::properties props) override
    {
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
};
#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class StationExecuteNode : public MqttActionNode // Assuming MqttActionNode is the base
{
public:
    StationExecuteNode(const std::string &name,
                       const BT::NodeConfig &config,
                       MqttClient &mqtt_client,
                       const mqtt_utils::Topic &request_topic,  // This is a pattern
                       const mqtt_utils::Topic &response_topic) // This is a pattern
        : MqttActionNode(name, config, mqtt_client,
                         request_topic,  // Pass pattern to MqttActionNode
                         response_topic) // Sub topics
    {
        for (auto &[key, topic_obj] : MqttPubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern()));
        }
        // For SubBase topics
        for (auto &[key, topic_obj] : MqttSubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern()));
        }
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }
    ~StationExecuteNode()
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->unregisterInstance(this);
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
                    "{ID}",
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
    std::string getFormattedTopic(const std::string &pattern)
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
    void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override
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
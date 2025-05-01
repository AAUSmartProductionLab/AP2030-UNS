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
                       const std::string &request_topic,
                       const std::string &response_topic,
                       const std::string &request_schema_path,
                       const std::string &response_schema_path,
                       const bool &retain,
                       const int &pubqos,
                       const int &subqos)
        : MqttActionNode(name,
                         config,
                         bt_mqtt_client,
                         request_topic,
                         response_topic,
                         request_schema_path,
                         response_schema_path,
                         retain,
                         pubqos,
                         subqos)
    {
        request_topic_ = getFormattedTopic(request_topic_pattern_, config);
        response_topic_ = getFormattedTopic(response_topic_pattern_, config);
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
                    "CommandUuid",
                    "{_ID}",
                    "UUID for the command to execute")};
    }
    json createMessage() override
    {
        json message;
        auto command_uuid_result = getInput<std::string>("CommandUuid");

        if (command_uuid_result)
        {
            current_command_uuid_ = command_uuid_result.value();
        }
        else
        {
            // Handle the error - CommandUuid is missing
            std::cerr << "Error: CommandUuid not provided to StationExecuteNode. Error: "
                      << command_uuid_result.error() << std::endl;

            // Generate a new UUID as fallback or set empty
            current_command_uuid_ = mqtt_utils::generate_uuid();
            std::cerr << "Using generated UUID instead: " << current_command_uuid_ << std::endl;
        }
        message["CommandUuid"] = current_command_uuid_;
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
    bool isInterestedIn(const json &msg) override
    {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (this->response_schema_validator_)
            {
                try
                {
                    this->response_schema_validator_->validate(msg);
                }
                catch (const std::exception &e)
                {
                    std::cerr << "JSON validation failed: " << e.what() << std::endl;
                    return false;
                }
            }
            if (status() == BT::NodeStatus::RUNNING)
            {

                return true;
            }
            return false;
        }
    }

    // Standard implementation based on PackML override this if needed
    void
    callback(const json &msg, mqtt::properties props) override
    {
        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(mutex_);
            std::cout << "Received message: " << msg.dump() << std::endl;
            // Update state based on message content
            if (status() == BT::NodeStatus::RUNNING)
            {
                if (!msg["ProcessQueue"].empty() && msg["ProcessQueue"][0].get<std::string>() == current_command_uuid_)
                {

                    if (msg["State"] == "ABORTED" || msg["State"] == "STOPPED")
                    {
                        current_command_uuid_ = "";
                        setStatus(BT::NodeStatus::FAILURE);
                    }
                    else if (msg["State"] == "COMPLETE")
                    {
                        current_command_uuid_ = "";
                        setStatus(BT::NodeStatus::SUCCESS);
                    }
                }
                else
                {
                    std::cout << "The station does not have the command uuid any longer" << std::endl;
                    current_command_uuid_ = "";
                    setStatus(BT::NodeStatus::FAILURE);
                }
                emitWakeUpSignal();
            }
        }
    }
};
#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

class CommandExecuteNode : public MqttActionNode
{
public:
    CommandExecuteNode(const std::string &name,
                       const BT::NodeConfig &config,
                       MqttClient &mqtt_client,
                       const mqtt_utils::Topic &request_topic,
                       const mqtt_utils::Topic &response_topic)
        : MqttActionNode(name, config, mqtt_client,
                         request_topic,
                         response_topic)
    {
        for (auto &[key, topic_obj] : MqttPubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern()));
        }
        for (auto &[key, topic_obj] : MqttSubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern()));
        }
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }
    ~CommandExecuteNode()
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
                    "Entity",
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
        if (uuid_result && uuid_result.has_value())
        {
            current_uuid_ = uuid_result.value();
        }
        else
        {
            std::cout << "Error: Uuid not provided to CommandExecuteNode. Generating and using random UUID." << std::endl;
            current_uuid_ = mqtt_utils::generate_uuid();
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
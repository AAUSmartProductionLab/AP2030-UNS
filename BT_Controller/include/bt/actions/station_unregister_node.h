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
class StationUnRegisterNode : public MqttActionNode
{
public:
    StationUnRegisterNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                          const mqtt_utils::Topic &request_topic,
                          const mqtt_utils::Topic &response_topic)
        : MqttActionNode(name, config, bt_mqtt_client,
                         request_topic, response_topic)
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
        response_topic_.setTopic(getFormattedTopic(response_topic.getPattern(), config));
        request_topic_.setTopic(getFormattedTopic(request_topic_.getPattern(), config));
        halt_topic_.setTopic(getFormattedTopic(request_topic_.getPattern(), config));
    }
    static BT::PortsList providedPorts()
    {
        return {
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Station",
                "{_Station}",
                "The station to unregister from"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "CommandUuid",
                "{_ID}",
                "UUID for the command to execute")};
    }
    json createMessage() override
    {
        std::cout << "Creating message in StationUnRegisterNode" << std::endl;
        json message;

        BT::Expected<std::string> uuid = getInput<std::string>("CommandUuid");
        if (uuid.has_value())
        {
            current_command_uuid_ = uuid.value();
            message["CommandUuid"] = current_command_uuid_;
        }
        return message;
    }

    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
    {
        BT::Expected<std::string> id = getInput<std::string>("Station");
        if (id.has_value())
        {
            return mqtt_utils::formatWildcardTopic(pattern, id.value());
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

    void callback(const json &msg, mqtt::properties props) override
    {
        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(mutex_);
            std::cout << "Received message in StationUnRegisterNode: " << msg.dump() << std::endl;
            if (msg["ProcessQueue"].empty() ||
                (std::find_if(msg["ProcessQueue"].begin(), msg["ProcessQueue"].end(),
                              [this](const auto &item)
                              { return std::string(item) == current_command_uuid_; }) == msg["ProcessQueue"].end()))
            {
                current_command_uuid_ = "";
                setStatus(BT::NodeStatus::SUCCESS);
            }
            // there might be a time based criteria when the node would fail
            emitWakeUpSignal();
        }
    }
};
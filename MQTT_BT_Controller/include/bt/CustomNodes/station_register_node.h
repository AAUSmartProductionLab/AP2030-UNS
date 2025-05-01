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
class StationRegisterNode : public MqttActionNode
{
public:
    StationRegisterNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                        const mqtt_utils::Topic &request_topic,
                        const mqtt_utils::Topic &response_topic)
        : MqttActionNode(name, config, bt_mqtt_client,
                         request_topic, response_topic)
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
                BT::PortDirection::OUTPUT,
                "CommandUuid",
                "{_ID}",
                "UUID for the command to execute")};
    }
    json createMessage() override
    {
        std::cout << "Creating message in StationRegisterNode" << std::endl;
        json message;
        current_command_uuid_ = mqtt_utils::generate_uuid();
        setOutput<std::string>("CommandUuid", current_command_uuid_);
        message["CommandUuid"] = current_command_uuid_;
        return message;
    }
    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
    {
        BT::Expected<std::string> id = config.blackboard->get<std::string>("Station");
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
            std::cout << "Received message in StationRegisterNode: " << msg.dump() << std::endl;
            if (!msg["ProcessQueue"].empty() && msg["ProcessQueue"][0].get<std::string>() == current_command_uuid_ && msg["State"].get<std::string>() == "IDLE")
            {
                current_command_uuid_ = "";
                setStatus(BT::NodeStatus::SUCCESS);
                emitWakeUpSignal();
            }
            else
            {
                emitWakeUpSignal();
            }
        }
    }
};
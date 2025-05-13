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
class StationCompleteNode : public MqttActionNode
{
public:
    StationCompleteNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
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
                "{Station}",
                "The station to unregister from"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Uuid",
                "{ID}",
                "UUID for the command to execute")};
    }
    json createMessage() override
    {
        json message;

        BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
        if (uuid.has_value())
        {
            current_uuid_ = uuid.value();
            message["Uuid"] = current_uuid_;
        }
        return message;
    }

    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
    {
        BT::Expected<std::string> station = getInput<std::string>("Station");
        if (station.has_value())
        {
            return mqtt_utils::formatWildcardTopic(pattern, station.value());
        }
        return pattern;
    }

    void callback(const json &msg, mqtt::properties props) override
    {
        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(mutex_);
            // Update state based on message content
            if (status() == BT::NodeStatus::RUNNING)
            {
                // such that we can unregister evwen when it is not our turn
                if (std::find(msg["ProcessQueue"].begin(),
                              msg["ProcessQueue"].end(),
                              current_uuid_) != msg["ProcessQueue"].end())
                {
                    current_uuid_ = "";
                    setStatus(BT::NodeStatus::SUCCESS);
                }
                else if (!msg["ProcessQueue"].empty() && msg["ProcessQueue"][0] == current_uuid_)
                {
                    if (msg["State"] == "STOPPING")
                    {
                        current_uuid_ = "";
                        setStatus(BT::NodeStatus::FAILURE);
                    }
                    else if (msg["State"] == "COMPLETE")
                    {
                        current_uuid_ = "";
                        setStatus(BT::NodeStatus::SUCCESS);
                    }
                }

                emitWakeUpSignal();
            }
        }
    }
};
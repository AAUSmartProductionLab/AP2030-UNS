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
                        const std::string &request_topic,
                        const std::string &response_topic,
                        const std::string &request_schema_path,
                        const std::string &response_schema_path)
        : MqttActionNode(name, config, bt_mqtt_client,
                         request_topic, response_topic, request_schema_path, response_schema_path)
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }

    json createMessage() override
    {
        json message;
        current_command_uuid_ = mqtt_utils::generate_uuid();
        message["CommandUuid"] = current_command_uuid_;
        return message;
    }

    bool isInterestedIn(const json &msg) override
    {
        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (status() == BT::NodeStatus::RUNNING)
            {
                if (!msg.contains("State") || !msg.contains("ProcessQueue"))
                {
                    return false;
                }
                return true;
            }
            return false;
        }
    }

    void
    callback(const json &msg, mqtt::properties props) override
    {
        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(mutex_);

            // Update state based on message content
            if (!msg["ProcessQueue"].contains(current_command_uuid_))
            {
                current_command_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::FAILURE);
                emitWakeUpSignal();
            }
            else if (msg["ProcessQueue"][0].get<std::string>() == current_command_uuid_ && msg["State"].get<std::string>() == "IDLE")
            {
                current_command_uuid_ = "";
                // Change from setting internal state to updating node status
                setStatus(BT::NodeStatus::SUCCESS);
                emitWakeUpSignal();
            }
            else
            {
                // No need to set RUNNING again if already running
                emitWakeUpSignal();
            }
        }
    }
};
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
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (status() == BT::NodeStatus::RUNNING)
            {

                // Check if both required fields exist in the message
                if (!msg.contains("State") || !msg.contains("ProcessQueue"))
                {
                    return false;
                }

                if (!msg["ProcessQueue"].empty() && msg["ProcessQueue"][0].get<std::string>() == current_command_uuid_)
                {
                    return true;
                }
            }
            return false;
        }
    }
};
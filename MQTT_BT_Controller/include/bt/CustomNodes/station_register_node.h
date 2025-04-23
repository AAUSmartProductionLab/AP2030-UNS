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
                        const std::string &response_schema_path,const bool &retain,const int &pubqos)
        : MqttActionNode(name, config, bt_mqtt_client,
                         request_topic, response_topic, request_schema_path, response_schema_path, retain, pubqos)
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }
    static BT::PortsList providedPorts()
    {
        return {BT::OutputPort<std::string>("CommandUuid")};
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

    void callback(const json &msg, mqtt::properties props) override
    {
        // Use mutex to protect shared state
        {
            std::lock_guard<std::mutex> lock(mutex_);
            std::cout << "Received message in StationRegisterNode: " << msg.dump() << std::endl;
            // // Update state based on message content
            // if (!msg["ProcessQueue"].contains(current_command_uuid_))
            // {
            //     current_command_uuid_ = "";
            //     // Change from setting internal state to updating node status
            //     setStatus(BT::NodeStatus::FAILURE);
            //     emitWakeUpSignal();
            // }
            if (!msg["ProcessQueue"].empty() && msg["ProcessQueue"][0].get<std::string>() == current_command_uuid_ && msg["State"].get<std::string>() == "IDLE")
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
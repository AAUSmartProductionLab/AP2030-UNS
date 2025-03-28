#include "bt/CustomNodes/omron_arcl_request_node.h"
#include "mqtt/utils.h"
#include "mqtt/subscription_manager.h"
#include "common_constants.h"

// MoveShuttleToPosition implementation
OmronArclRequest::OmronArclRequest(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy)
    : MqttActionNode(name, config, bt_proxy,
                     UNS_TOPIC,
                     "../schemas/amrArclRequest.schema.json",
                     "../schemas/amrArclUpdate.schema.json")
{
    if (MqttActionNode::subscription_manager_)
    {
        MqttActionNode::subscription_manager_->registerDerivedInstance<OmronArclRequest>(this);
    }
}

BT::PortsList OmronArclRequest::providedPorts()
{
    return {BT::InputPort("command")};
}

json OmronArclRequest::createMessage()
{
    BT::Expected<std::string> command = getInput<std::string>("command");

    json message;
    current_command_uuid_ = mqtt_utils::generate_uuid();
    message["id"] = current_command_uuid_;
    message["command"] = command.value();
    return message;
}

bool OmronArclRequest::isInterestedIn(const std::string &field, const json &value)
{
    if (field == "id" && value.is_string())
    {
        bool interested = (value.get<std::string>() == current_command_uuid_);
        return interested;
    }
    return false;
}

void OmronArclRequest::callback(const json &msg, mqtt::properties props)
{
    {
        std::lock_guard<std::mutex> lock(state_mutex_);

        // Update state based on message content
        if (msg.contains("message"))
        {
            if (msg["message"] == 0)
            {
                current_command_uuid_ = "";
                state = BT::NodeStatus::FAILURE;
                emitWakeUpSignal();
            }
            else if (msg["message"] == 0)
            {
                current_command_uuid_ = "";
                state = BT::NodeStatus::SUCCESS;
                emitWakeUpSignal();
            }
            else if (msg["message"] == 0)
            {
                state = BT::NodeStatus::RUNNING;
                emitWakeUpSignal();
            }
            else
            {
                std::cout << "Unknown State value: " << msg["State"] << std::endl;
            }

            // Use explicit memory ordering when setting the flag
            state_updated_.store(true, std::memory_order_seq_cst);
        }
        else
        {
            std::cout << "Message doesn't contain 'state' field" << std::endl;
        }
    }
}
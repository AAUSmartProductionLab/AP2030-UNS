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
        MqttActionNode::subscription_manager_->registerDerivedInstance(this);
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
        // Todo implment state management
        std::lock_guard<std::mutex> lock(mutex_);
        setStatus(BT::NodeStatus::SUCCESS);
        emitWakeUpSignal();
    }
}
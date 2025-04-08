#include "bt/CustomNodes/omron_arcl_request_node.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"
#include "common_constants.h"

// MoveShuttleToPosition implementation
OmronArclRequest::OmronArclRequest(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client, const std::string &request_topic, const std::string &response_topic, const std::string &request_schema_path, const std::string &response_schema_path)
    : MqttActionNode(name, config, bt_mqtt_client,
                     request_topic, response_topic, request_schema_path, response_schema_path)

{
    if (MqttActionNode::node_message_distributor_)
    {
        MqttActionNode::node_message_distributor_->registerDerivedInstance(this);
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
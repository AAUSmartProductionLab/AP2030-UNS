#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"
#include "common_constants.h"

// MoveShuttleToPosition implementation
MoveShuttleToPosition::MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client, const std::string &request_topic, const std::string &response_topic, const std::string &request_schema_path, const std::string &response_schema_path)
    : MqttActionNode(name, config, bt_mqtt_client,
                     request_topic,
                     response_topic, request_schema_path, response_schema_path)
{
    // Replace the wildcard in the request and response topics with the XbotId of this node
    response_topic_ = getFormattedTopic(response_topic_pattern_, config);
    request_topic_ = getFormattedTopic(request_topic_pattern_, config);

    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

std::string MoveShuttleToPosition::getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
{
    BT::Expected<int> id = config.blackboard->get<int>("XbotId");
    if (id.has_value())
    {
        std::string id_str = "Xbot" + std::to_string(id.value());
        return mqtt_utils::formatWildcardTopic(pattern, id_str);
    }
    return pattern;
}

BT::PortsList MoveShuttleToPosition::providedPorts()
{
    return {BT::InputPort<int>("TargetPosition")};
}

json MoveShuttleToPosition::createMessage()
{

    BT::Expected<int> TargetPosition = getInput<int>("TargetPosition");

    json message;
    current_command_uuid_ = mqtt_utils::generate_uuid();
    message["TargetPosition"] = TargetPosition.value();
    message["CommandUuid"] = current_command_uuid_;
    return message;
}
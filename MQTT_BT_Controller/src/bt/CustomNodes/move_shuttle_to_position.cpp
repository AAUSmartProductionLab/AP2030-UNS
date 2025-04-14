#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"
#include "common_constants.h"

// BT template specialization implementation
namespace BT
{
    template <>
    Position2D convertFromString(StringView str)
    {
        // We expect real numbers separated by semicolons
        auto parts = splitString(str, ';');
        if (parts.size() != 2)
        {
            throw RuntimeError("invalid input)");
        }
        else
        {
            Position2D output;
            output.x = convertFromString<double>(parts[0]);
            output.y = convertFromString<double>(parts[1]);
            return output;
        }
    }
}

// MoveShuttleToPosition implementation
MoveShuttleToPosition::MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client, const std::string &request_topic, const std::string &response_topic, const std::string &request_schema_path, const std::string &response_schema_path)
    : MqttActionNode(name, config, bt_mqtt_client,
                     request_topic, response_topic, request_schema_path, response_schema_path)
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

BT::PortsList MoveShuttleToPosition::providedPorts()
{
    return {BT::InputPort<Position2D>("goal"), BT::InputPort<int>("xbot_id")};
}

json MoveShuttleToPosition::createMessage()
{
    BT::Expected<int> id = getInput<int>("xbot_id");
    BT::Expected<Position2D> goal = getInput<Position2D>("goal");

    // since we use a wildcard in the topic pattern, we need to replace it with the id
    if (id.has_value())
    {
        std::string id_str = "Xbot" + std::to_string(id.value());
        request_topic_ = formatTopic(request_topic_pattern_, id_str);
    }

    json message;
    current_command_uuid_ = mqtt_utils::generate_uuid();
    message["XbotId"] = id.value();
    message["TargetPos"] = json::array({goal.value().x, goal.value().y});
    message["CommandUuid"] = current_command_uuid_;
    return message;
}
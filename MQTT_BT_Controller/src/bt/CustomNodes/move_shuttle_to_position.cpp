#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"

MoveShuttleToPosition::MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client, const mqtt_utils::Topic &request_topic, const mqtt_utils::Topic &response_topic) : MqttActionNode(name, config, bt_mqtt_client,
                                                                                                                                                                                                                                  request_topic,
                                                                                                                                                                                                                                  response_topic)
{
    // Replace the wildcard in the request and response topics with the XbotId of this node instance
    response_topic_.setTopic(getFormattedTopic(response_topic.getPattern(), config));
    request_topic_.setTopic(getFormattedTopic(request_topic_.getPattern(), config));

    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

std::string MoveShuttleToPosition::getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
{
    BT::Expected<int> id = config.blackboard->get<int>("XbotId"); // hacky way of getting the ID from the subtree parameter
    if (id.has_value())
    {
        std::string id_str = "Xbot" + std::to_string(id.value());
        std::string formatted = mqtt_utils::formatWildcardTopic(pattern, id_str);
        return formatted;
    }
    return pattern;
}

BT::PortsList MoveShuttleToPosition::providedPorts()
{
    return {BT::InputPort<std::string>("TargetPosition")};
}

json MoveShuttleToPosition::createMessage()
{
    BT::Expected<std::string> TargetPosition = getInput<std::string>("TargetPosition");
    BT::Expected<std::map<std::string, int>> stationMap = config().blackboard->get<std::map<std::string, int>>("StationMap"); // hacky way of getting the ID from the subtree parameter
    json message;

    std::string station = TargetPosition.value();
    if (stationMap.value().find(station) != stationMap.value().end())
    {
        current_command_uuid_ = mqtt_utils::generate_uuid();
        message["TargetPosition"] = stationMap.value()[station];
        message["CommandUuid"] = current_command_uuid_;
        return message;
    }
    return json();
}
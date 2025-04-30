#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"

std::map<std::string, int> stationMap = {
    {"Loading", 1},
    {"Filling", 2},
    {"Stoppering", 3},
    {"Unloading", 4}};

MoveShuttleToPosition::MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client, const std::string &request_topic, const std::string &response_topic, const std::string &request_schema_path, const std::string &response_schema_path, const bool &retain, const int &pubqos, const int &subqos) : MqttActionNode(name, config, bt_mqtt_client,
                                                                                                                                                                                                                                                                                                                                                                 request_topic,
                                                                                                                                                                                                                                                                                                                                                                 response_topic, request_schema_path, response_schema_path, retain, pubqos, subqos)
{
    // Replace the wildcard in the request and response topics with the XbotId of this node instance
    response_topic_ = getFormattedTopic(response_topic_pattern_, config);
    request_topic_ = getFormattedTopic(request_topic_pattern_, config);

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

    json message;
    std::string station = TargetPosition.value();
    if (stationMap.find(station) != stationMap.end())
    {
        current_command_uuid_ = mqtt_utils::generate_uuid();
        message["TargetPosition"] = stationMap[station];
        message["CommandUuid"] = current_command_uuid_;
        return message;
    }
    return json();
}
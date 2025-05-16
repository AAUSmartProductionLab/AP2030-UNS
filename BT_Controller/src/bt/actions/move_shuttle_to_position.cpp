#include "bt/actions/move_shuttle_to_position.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

MoveShuttleToPosition::MoveShuttleToPosition(
    const std::string &name,
    const BT::NodeConfig &config,
    MqttClient &bt_mqtt_client,
    const mqtt_utils::Topic &request_topic,
    const mqtt_utils::Topic &response_topic,
    const mqtt_utils::Topic &halt_topic) : MqttActionNode(name, config, bt_mqtt_client, request_topic, response_topic, halt_topic)
{
    // Replace the wildcard in the request and response topics with the XbotId of this node instance
    for (auto &[key, topic_obj] : MqttPubBase::topics_)
    {
        topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern(), config));
    }
    // For SubBase topics
    for (auto &[key, topic_obj] : MqttSubBase::topics_)
    {
        topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern(), config));
    }
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

MoveShuttleToPosition::~MoveShuttleToPosition()
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->unregisterInstance(this);
    }
}

std::string MoveShuttleToPosition::getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
{
    BT::Expected<std::string> id = config.blackboard->get<std::string>("XbotTopic"); // hacky way of getting the ID from the subtree parameter
    if (id.has_value())
    {
        std::string formatted = mqtt_utils::formatWildcardTopic(pattern, id.value());
        return formatted;
    }
    return pattern;
}

BT::PortsList MoveShuttleToPosition::providedPorts()
{
    return {BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "TargetPosition",
                "{Station}",
                "The name of the station to move to"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Uuid",
                "{ProductID}",
                "UUID for the command to execute")};
}

void MoveShuttleToPosition::onHalted()
{
    // Clean up when the node is halted
    std::cout << "MQTT action node halted" << std::endl;
    // Additional cleanup as needed
    json message;
    message["TargetPosition"] = 0;
    message["Uuid"] = current_uuid_;
    publish("halt", message);
}

json MoveShuttleToPosition::createMessage()
{
    BT::Expected<std::string> TargetPosition = getInput<std::string>("TargetPosition");
    BT::Expected<std::string> Uuid = getInput<std::string>("Uuid");
    BT::Expected<std::map<std::string, int>> stationMap = config().blackboard->get<std::map<std::string, int>>("StationMap"); // hacky way of getting the ID from the subtree parameter
    json message;
    if (TargetPosition.has_value() && Uuid.has_value())
    {
        std::string station = TargetPosition.value();
        if (stationMap.value().find(station) != stationMap.value().end())
        {
            current_uuid_ = Uuid.value();
            message["TargetPosition"] = stationMap.value()[station];
            message["Uuid"] = current_uuid_;
            return message;
        }
    }
    return json();
}
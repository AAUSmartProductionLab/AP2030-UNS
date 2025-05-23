#include "bt/actions/move_to_position.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

MoveToPosition::MoveToPosition(
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

MoveToPosition::~MoveToPosition()
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->unregisterInstance(this);
    }
}

std::string MoveToPosition::getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
{
    BT::Expected<std::string> topic = getInput<std::string>("Topic");
    if (topic.has_value())
    {
        std::string formatted = mqtt_utils::formatWildcardTopic(pattern, topic.value());
        return formatted;
    }
    return pattern;
}

BT::PortsList MoveToPosition::providedPorts()
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
                "UUID for the command to execute"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Topic",
                "{Topic}",
                "Topic to which we want to send the request")};
}

void MoveToPosition::onHalted()
{
    // Clean up when the node is halted
    std::cout << name() << " node halted" << std::endl;
    // Additional cleanup as needed
    json message;
    message["TargetPosition"] = 0;
    message["Uuid"] = current_uuid_;
    publish("halt", message);
}

json MoveToPosition::createMessage()
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
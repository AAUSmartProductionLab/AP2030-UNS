#include "bt/actions/omron_arcl_request_node.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

// MoveShuttleToPosition implementation
OmronArclRequest::OmronArclRequest(const std::string &name,
                                   const BT::NodeConfig &config,
                                   MqttClient &bt_mqtt_client,
                                   const mqtt_utils::Topic &request_topic,
                                   const mqtt_utils::Topic &response_topic)
    : MqttActionNode(name, config, bt_mqtt_client,
                     request_topic, response_topic)

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
    current_uuid_ = mqtt_utils::generate_uuid();
    message["id"] = current_uuid_;
    message["command"] = command.value();
    return message;
}

void OmronArclRequest::callback(const json &msg, mqtt::properties props)
{
    {
        // Todo implment state management
        std::lock_guard<std::mutex> lock(mutex_);
        if (status() == BT::NodeStatus::RUNNING && msg.contains("id") && msg["id"].get<std::string>() == current_uuid_)
        {
            setStatus(BT::NodeStatus::SUCCESS);
        }
        emitWakeUpSignal();
    }
}
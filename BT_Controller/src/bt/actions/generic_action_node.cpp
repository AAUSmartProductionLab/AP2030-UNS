#include "bt/actions/generic_action_node.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

// MoveShuttleToPosition implementation
GenericActionNode::GenericActionNode(const std::string &name,
                                     const BT::NodeConfig &config,
                                     MqttClient &bt_mqtt_client,
                                     const mqtt_utils::Topic &request_topic,
                                     const mqtt_utils::Topic &response_topic)
    : MqttActionNode(name, config, bt_mqtt_client,
                     request_topic, response_topic)
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

json GenericActionNode::createMessage()
{
    json message;
    current_uuid_ = mqtt_utils::generate_uuid();
    message["Uuid"] = current_uuid_;
    return message;
}

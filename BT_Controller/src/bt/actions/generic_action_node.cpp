#include "bt/actions/generic_action_node.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

// MoveShuttleToPosition implementation
GenericActionNode::GenericActionNode(
    const std::string &name,
    const BT::NodeConfig &config,
    MqttClient &bt_mqtt_client,
    AASClient &aas_client)
    : MqttActionNode(name, config, bt_mqtt_client, aas_client)
{
}

json GenericActionNode::createMessage()
{
    json message;
    current_uuid_ = mqtt_utils::generate_uuid();
    message["Uuid"] = current_uuid_;
    return message;
}

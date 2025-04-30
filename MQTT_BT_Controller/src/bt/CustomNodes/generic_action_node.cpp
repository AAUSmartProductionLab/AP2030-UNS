#include "bt/CustomNodes/generic_action_node.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"

// MoveShuttleToPosition implementation
GenericActionNode::GenericActionNode(const std::string &name,
                                     const BT::NodeConfig &config,
                                     MqttClient &bt_mqtt_client,
                                     const std::string &request_topic,
                                     const std::string &response_topic,
                                     const std::string &request_schema_path,
                                     const std::string &response_schema_path,
                                     const bool &retain,
                                     const int &pubqos,
                                     const int &subqos)
    : MqttActionNode(name, config, bt_mqtt_client,
                     request_topic, response_topic, request_schema_path, response_schema_path, retain, pubqos, subqos)
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

json GenericActionNode::createMessage()
{
    json message;
    current_command_uuid_ = mqtt_utils::generate_uuid();
    message["CommandUuid"] = current_command_uuid_;
    return message;
}

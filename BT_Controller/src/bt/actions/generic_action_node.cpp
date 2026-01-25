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

void GenericActionNode::initializeTopicsFromAAS()
{
    // Already initialized, skip
    if (topics_initialized_)
    {
        return;
    }

    try
    {
        auto asset_input = getInput<std::string>("Asset");
        if (!asset_input.has_value())
        {
            std::cerr << "Node '" << this->name() << "' has no Asset input configured" << std::endl;
            return;
        }

        std::string asset_id = asset_input.value();
        std::cout << "Node '" << this->name() << "' initializing for Asset: " << asset_id << std::endl;

        // Create Topic objects using the node's name as the interaction
        auto request_opt = aas_client_.fetchInterface(asset_id, this->name(), "input");
        auto response_opt = aas_client_.fetchInterface(asset_id, this->name(), "output");

        if (!request_opt.has_value() || !response_opt.has_value())
        {
            std::cerr << "Failed to fetch interfaces from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttPubBase::setTopic("input", request_opt.value());
        MqttSubBase::setTopic("output", response_opt.value());
        topics_initialized_ = true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

json GenericActionNode::createMessage()
{
    json message;
    current_uuid_ = mqtt_utils::generate_uuid();
    message["Uuid"] = current_uuid_;
    return message;
}

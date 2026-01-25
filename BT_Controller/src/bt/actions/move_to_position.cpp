#include "bt/actions/move_to_position.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

void MoveToPosition::initializeTopicsFromAAS()
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

        // Create Topic objects
        auto request_opt = aas_client_.fetchInterface(asset_id, this->name(), "input");
        auto halt_opt = aas_client_.fetchInterface(asset_id, "halt", "input");
        auto response_opt = aas_client_.fetchInterface(asset_id, this->name(), "output");

        if (!request_opt.has_value() || !halt_opt.has_value() || !response_opt.has_value())
        {
            std::cerr << "Failed to fetch interfaces from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttPubBase::setTopic("input", request_opt.value());
        MqttPubBase::setTopic("halt", halt_opt.value());
        MqttSubBase::setTopic("output", response_opt.value());
        topics_initialized_ = true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

BT::PortsList MoveToPosition::providedPorts()
{
    return {
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INPUT,
            "Asset",
            "{Xbot}",
            "The Asset to execute the movement"),
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INPUT,
            "TargetPosition",
            "{Station}",
            "The name of the station to move to"),
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INPUT,
            "Uuid",
            "{ProductID}",
            "UUID for the command to execute"),
    };
}

void MoveToPosition::onHalted()
{
    // Clean up when the node is halted
    std::cout << name() << " node halted" << std::endl;
    // Additional cleanup as needed
    nlohmann::json message;
    message["TargetPosition"] = 0;
    message["Uuid"] = current_uuid_;
    publish("halt", message);
}

nlohmann::json MoveToPosition::createMessage()
{
    BT::Expected<std::string> TargetPosition = getInput<std::string>("TargetPosition");
    BT::Expected<std::string> Uuid = getInput<std::string>("Uuid");

    nlohmann::json message;
    if (TargetPosition.has_value() && Uuid.has_value())
    {
        // Use the target position directly as the station ID
        // The blackboard should already contain station names mapped to their AAS IDs
        std::string stationId = TargetPosition.value();
        current_uuid_ = Uuid.value();
        message["TargetPosition"] = stationId;
        message["Uuid"] = current_uuid_;
        return message;
    }

    return nlohmann::json();
}
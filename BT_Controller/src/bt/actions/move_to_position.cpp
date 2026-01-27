#include "bt/actions/move_to_position.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

// Filling line AAS ID - used to look up station positions from HierarchicalStructures
static const std::string FILLING_LINE_AAS_ID = "https://smartproductionlab.aau.dk/aas/aauFillingLineAAS";

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
        // TargetPosition now contains the station's AAS ID (e.g., https://...imaDispensingSystemAAS)
        // We need to look up the actual x, y, yaw position from the filling line's HierarchicalStructures
        std::string station_aas_id = TargetPosition.value();
        current_uuid_ = Uuid.value();
        
        // Fetch position from the filling line's HierarchicalStructures
        auto position_opt = aas_client_.fetchStationPosition(station_aas_id, FILLING_LINE_AAS_ID);
        
        if (position_opt.has_value())
        {
            const auto& pos = position_opt.value();
            float x = pos.value("x", 0.0f);
            float y = pos.value("y", 0.0f);
            float theta = pos.value("theta", 0.0f);
            
            // Build message according to schema: Position: [x, y, theta]
            message["Position"] = nlohmann::json::array({x, y, theta});
            message["Uuid"] = current_uuid_;
            message["TimeStamp"] = bt_utils::getCurrentTimestampISO();
            
            std::cout << "MoveToPosition: Moving to station " << station_aas_id 
                      << " at position [" << x << ", " << y << ", " << theta << "]" << std::endl;
        }
        else
        {
            std::cerr << "MoveToPosition: Failed to fetch position for station: " << station_aas_id << std::endl;
            // Return empty message to indicate failure
            return nlohmann::json();
        }
        
        return message;
    }

    return nlohmann::json();
}
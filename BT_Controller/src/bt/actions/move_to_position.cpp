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
        BT::InputPort<std::string>("Asset", "{Xbot}", 
            "The Asset to execute the movement"),
        BT::InputPort<double>("x", 
            "X position - can be literal, {blackboard}, or $aas{SubmodelId/path}"),
        BT::InputPort<double>("y", 
            "Y position - can be literal, {blackboard}, or $aas{SubmodelId/path}"),
        BT::InputPort<double>("yaw", 
            "Yaw angle (theta) - can be literal, {blackboard}, or $aas{SubmodelId/path}"),
        BT::InputPort<std::string>("Uuid", "{ProductID}", 
            "UUID for the command to execute"),
    };
}

void MoveToPosition::onHalted()
{
    // Clean up when the node is halted
    std::cout << name() << " node halted" << std::endl;
    nlohmann::json message;
    message["TargetPosition"] = 0;
    message["Uuid"] = current_uuid_;
    publish("halt", message);
}

nlohmann::json MoveToPosition::createMessage()
{
    // Get position values - these automatically resolve $aas{} references
    auto x_result = getInput<double>("x");
    auto y_result = getInput<double>("y");
    auto yaw_result = getInput<double>("yaw");
    auto uuid_result = getInput<std::string>("Uuid");

    nlohmann::json message;
    
    if (!x_result.has_value())
    {
        std::cerr << "MoveToPosition: Failed to get x value: " << x_result.error() << std::endl;
        return nlohmann::json();
    }
    if (!y_result.has_value())
    {
        std::cerr << "MoveToPosition: Failed to get y value: " << y_result.error() << std::endl;
        return nlohmann::json();
    }
    if (!yaw_result.has_value())
    {
        std::cerr << "MoveToPosition: Failed to get yaw value: " << yaw_result.error() << std::endl;
        return nlohmann::json();
    }
    if (!uuid_result.has_value())
    {
        std::cerr << "MoveToPosition: Failed to get Uuid: " << uuid_result.error() << std::endl;
        return nlohmann::json();
    }
    
    double x = x_result.value();
    double y = y_result.value();
    double yaw = yaw_result.value();
    current_uuid_ = uuid_result.value();
    
    // Build message according to schema: Position: [x, y, theta]
    message["Position"] = nlohmann::json::array({x, y, yaw});
    message["Uuid"] = current_uuid_;
    
    std::cout << "MoveToPosition: Moving to [" << x << ", " << y << ", " << yaw << "]" << std::endl;
    
    return message;
}
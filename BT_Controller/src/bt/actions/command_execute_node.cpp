#include "bt/mqtt_action_node.h"
#include "bt/actions/command_execute_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>

void CommandExecuteNode::initializeTopicsFromAAS()
{
    // Already initialized, skip
    if (topics_initialized_)
    {
        return;
    }

    try
    {
        auto asset_input = getInput<std::string>("Asset");
        auto operation_input = getInput<std::string>("Operation");

        if (!asset_input.has_value())
        {
            std::cerr << "Node '" << this->name() << "' has no Asset input configured" << std::endl;
            return;
        }

        if (!operation_input.has_value())
        {
            std::cerr << "Node '" << this->name() << "' has no Operation input configured" << std::endl;
            return;
        }

        std::string asset_id = asset_input.value();
        std::string operation = operation_input.value();
        std::cout << "Node '" << this->name() << "' initializing for Asset: " << asset_id
                  << ", Operation: " << operation << std::endl;

        // Create Topic objects
        auto request_opt = aas_client_.fetchInterface(asset_id, operation, "input");
        auto response_opt = aas_client_.fetchInterface(asset_id, operation, "output");

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

BT::PortsList CommandExecuteNode::providedPorts()
{
    return {BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Asset",
                "{Asset}",
                "The asset used for execution"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Operation",
                "Operation",
                "The operation to execute on the asset"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Uuid",
                "{Uuid}",
                "UUID for the operation to execute"),
            BT::details::PortWithDefault<nlohmann::json>(
                BT::PortDirection::INPUT,
                "Parameters",
                "'{}'",
                "The parameters for the operation")};
}

nlohmann::json CommandExecuteNode::createMessage()
{
    nlohmann::json message;
    BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
    if (uuid && uuid.has_value() && !uuid.value().empty())
    {
        current_uuid_ = uuid.value();
    }
    else
    {
        current_uuid_ = mqtt_utils::generate_uuid();
    }
    BT::Expected<nlohmann::json> params = getInput<nlohmann::json>("Parameters");

    if (params)
    {
        if (!params.value().empty() && params.value().is_object())
        {
            message.update(params.value());
        }
    }
    else
    {
        std::cerr << "Warning: Could not get or parse 'Parameters' port. Error: " << params.error() << std::endl;
    }

    message["Uuid"] = current_uuid_;
    return message;
}

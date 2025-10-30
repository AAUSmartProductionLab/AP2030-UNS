#include "bt/mqtt_action_node.h"
#include "bt/actions/command_execute_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>

void CommandExecuteNode::initializeTopicsFromAAS()
{
    try
    {
        std::string asset_id = aas_client_.getInstanceNameByAssetName(getInput<std::string>("Asset").value());
        // Create Topic objects
        mqtt_utils::Topic request = aas_client_.fetchInterface(asset_id, getInput<std::string>("Operation").value(), "request").value();
        mqtt_utils::Topic response = aas_client_.fetchInterface(asset_id, getInput<std::string>("Operation").value(), "response").value();
        MqttPubBase::setTopic("request", request);
        MqttSubBase::setTopic("response", response);
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

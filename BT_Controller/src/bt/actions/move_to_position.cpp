#include "bt/actions/move_to_position.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"

void MoveToPosition::initializeTopicsFromAAS()
{
    try
    {
        std::string asset_id = station_config_.at(getInput<std::string>("Asset").value());
        // Create Topic objects
        mqtt_utils::Topic request = aas_client_.fetchInterface(asset_id, this->name(), "request").value();
        mqtt_utils::Topic halt = aas_client_.fetchInterface(asset_id, this->name(), "halt").value();
        mqtt_utils::Topic response = aas_client_.fetchInterface(asset_id, this->name(), "response").value();

        MqttPubBase::setTopic("request", request);
        MqttPubBase::setTopic("halt", halt);
        MqttSubBase::setTopic("response", response);
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
            "{Asset}",
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
    json message;
    message["TargetPosition"] = 0;
    message["Uuid"] = current_uuid_;
    publish("halt", message);
}

json MoveToPosition::createMessage()
{
    BT::Expected<std::string> TargetPosition = getInput<std::string>("TargetPosition");
    BT::Expected<std::string> Uuid = getInput<std::string>("Uuid");

    json message;
    if (TargetPosition.has_value() && Uuid.has_value())
    {
        std::string targetStation = TargetPosition.value();

        // Use std::find_if to search for the station
        auto it = std::find_if(
            station_config_["Stations"].begin(),
            station_config_["Stations"].end(),
            [&targetStation](const json &station)
            {
                return station.contains("Name") && station["Name"] == targetStation;
            });

        if (it != station_config_["Stations"].end() && it->contains("StationId"))
        {
            current_uuid_ = Uuid.value();
            message["TargetPosition"] = (*it)["StationId"];
            message["Uuid"] = current_uuid_;
            return message;
        }

        std::cerr << "Station '" << targetStation << "' not found in configuration" << std::endl;
    }
    return json();
}
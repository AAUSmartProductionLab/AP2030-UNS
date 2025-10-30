#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

class CommandExecuteNode : public MqttActionNode
{
public:
    CommandExecuteNode(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client,
        const nlohmann::json &station_config)
        : MqttActionNode(name, config, mqtt_client, aas_client, station_config) {}

    static BT::PortsList providedPorts();
    nlohmann::json createMessage() override;
    std::string getFormattedTopic(const std::string &pattern) const;

    void initializeTopicsFromAAS() override;
};
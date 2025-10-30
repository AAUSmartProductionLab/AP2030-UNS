#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

class MoveToPosition : public MqttActionNode
{
private:
    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config);

public:
    MoveToPosition(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client,
        const nlohmann::json &station_config) : MqttActionNode(name, config, mqtt_client, aas_client, station_config) {}

    static BT::PortsList providedPorts();
    void initializeTopicsFromAAS() override;
    void onHalted() override;
    nlohmann::json createMessage() override;
};
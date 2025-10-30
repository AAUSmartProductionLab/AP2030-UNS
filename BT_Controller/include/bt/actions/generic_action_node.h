#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

class GenericActionNode : public MqttActionNode
{
public:
    GenericActionNode(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &bt_mqtt_client,
        AASClient &aas_client,
        const json &station_config);
    json createMessage() override;

    void initializeTopicsFromAAS() override;
};
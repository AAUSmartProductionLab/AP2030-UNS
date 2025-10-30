#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <nlohmann/json.hpp>
#include "aas/aas_client.h"
#include "bt/mqtt_sync_action_node.h"
#include "mqtt/node_message_distributor.h"

class PopElementNode : public MqttSyncActionNode
{
public:
    PopElementNode(const std::string &name,
                   const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   AASClient &aas_client) : MqttSyncActionNode(name, config, mqtt_client, aas_client) {}

    void initializeTopicsFromAAS() override;
    static BT::PortsList providedPorts();
    nlohmann::json createMessage() override;
};
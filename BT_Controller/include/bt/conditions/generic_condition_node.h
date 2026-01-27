#pragma once

#include "bt/mqtt_sync_condition_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "aas/aas_client.h"

class GenericConditionNode : public MqttSyncConditionNode
{
public:
    GenericConditionNode(const std::string &name, const BT::NodeConfig &config, MqttClient &mqtt_client,
                         AASClient &aas_client) : MqttSyncConditionNode(name, config, mqtt_client, aas_client) {}
    static BT::PortsList providedPorts();
    void initializeTopicsFromAAS() override;
    BT::NodeStatus tick() override;
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;
    bool compare(const json &msg, const std::string &field_name, const std::string &comparison_type,
                 const std::string &expected_value);
                 
private:
    std::string initialized_asset_id_;  // Track which asset we initialized for
    std::string initialized_property_;  // Track which property we initialized for
};
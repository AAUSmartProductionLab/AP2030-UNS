#pragma once

#include "bt/mqtt_sync_sub_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class GenericConditionNode : public MqttSyncSubNode
{
public:
    GenericConditionNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                         const mqtt_utils::Topic &response_topic);

    static BT::PortsList providedPorts();

    BT::NodeStatus tick() override;
    bool isInterestedIn(const json &msg) override;
    void callback(const json &msg, mqtt::properties props) override;
    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config);
};
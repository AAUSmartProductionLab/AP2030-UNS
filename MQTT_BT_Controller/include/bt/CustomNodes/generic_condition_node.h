#pragma once

#include "bt/mqtt_condition_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class GenericConditionNode : public MqttConditionNode
{
public:
    GenericConditionNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                         const std::string &response_topic, const std::string &response_schema_path);

    static BT::PortsList providedPorts();

    BT::NodeStatus tick() override;
    bool isInterestedIn(const json &msg) override;
    void callback(const json &msg, mqtt::properties props) override;
};
#pragma once

#include "bt/mqtt_condition_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class Proxy;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class GenericConditionNode : public MqttConditionNode
{
public:
    GenericConditionNode(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy,
                         const std::string &response_topic, const std::string &response_schema_path);

    static BT::PortsList providedPorts();

    BT::NodeStatus tick() override;
    bool isInterestedIn(const std::string &field, const json &value) override;
    void callback(const json &msg, mqtt::properties props) override;
};
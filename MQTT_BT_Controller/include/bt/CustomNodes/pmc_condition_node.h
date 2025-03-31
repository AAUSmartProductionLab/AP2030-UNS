#pragma once

#include "bt/mqtt_condition_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class Proxy;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class PMCConditionNode : public MqttValueComparisonCondition
{
public:
    PMCConditionNode(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy);

    static BT::PortsList providedPorts();

    // Override isInterestedIn to filter messages
    bool isInterestedIn(const std::string &field, const json &value) override;
};
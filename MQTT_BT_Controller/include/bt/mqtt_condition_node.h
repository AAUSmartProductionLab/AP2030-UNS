#pragma once

#include <behaviortree_cpp/behavior_tree.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_node_base.h"
#include "mqtt/subscription_manager.h"

using json = nlohmann::json;

class MqttConditionNode : public BT::ConditionNode, public MqttNodeBase
{
protected:
    json latest_msg_;
    std::mutex value_mutex_;

public:
    MqttConditionNode(const std::string &name,
                      const BT::NodeConfig &config,
                      Proxy &proxy,
                      const std::string &uns_topic,
                      const std::string &response_schema_path);

    ~MqttConditionNode() override;

    static BT::PortsList providedPorts();

    // Override callback to store the latest message
    void callback(const json &msg, mqtt::properties props) override;

    virtual BT::NodeStatus tick() override;
};
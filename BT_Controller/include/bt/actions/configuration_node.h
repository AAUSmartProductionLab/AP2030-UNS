#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include <deque>

class ConfigurationNode : public MqttActionNode
{

public:
    ConfigurationNode(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client)
        : MqttActionNode(name, config, mqtt_client, aas_client) {}
    static BT::PortsList providedPorts();
    BT::NodeStatus onStart();

    void initializeTopicsFromAAS() override;
    void callback(const std::string &topic_key, const nlohmann::json &msg, mqtt::properties props) override;
    std::shared_ptr<std::deque<std::string>> shared_queue = std::make_shared<std::deque<std::string>>();
};
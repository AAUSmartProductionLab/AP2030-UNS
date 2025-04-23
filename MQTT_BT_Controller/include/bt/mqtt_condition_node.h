#pragma once

#include <behaviortree_cpp/behavior_tree.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/node_message_distributor.h"

using nlohmann::json;

class MqttConditionNode : public BT::ConditionNode, public MqttSubBase
{
protected:
    json latest_msg_;

public:
    MqttConditionNode(const std::string &name,
                      const BT::NodeConfig &config,
                      MqttClient &mqtt_client,
                      const std::string &response_topic,
                      const std::string &response_schema_path);

    ~MqttConditionNode() override;

    static BT::PortsList providedPorts();

    // Override callback to store the latest message
    void callback(const json &msg, mqtt::properties props) override;

    virtual BT::NodeStatus tick() override;

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &node_message_distributor,
        MqttClient &mqtt_client,
        const std::string &node_name,
        const std::string &response_topic,
        const std::string &response_schema_path,
        const int &subqos = 0)
    {
        // Store configuration in a static map that persists throughout program execution
        static std::unordered_map<std::string, std::tuple<std::string, std::string>> node_configs;
        node_configs[node_name] = std::make_tuple(response_topic, response_schema_path);

        MqttConditionNode::setNodeMessageDistributor(&node_message_distributor);
        node_message_distributor.registerNodeType<DerivedNode>(response_topic,subqos);

        MqttClient *mqtt_client_ptr = &mqtt_client;
        // Register a builder that captures the configuration
        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr, node_name](const std::string &name, const BT::NodeConfig &config)
            {
                // Get the stored configuration
                auto &[resp_topic, resp_schema] = node_configs[node_name];

                auto node = std::make_unique<DerivedNode>(name, config, *mqtt_client_ptr, resp_topic, resp_schema);
                return node;
            });
    }
};

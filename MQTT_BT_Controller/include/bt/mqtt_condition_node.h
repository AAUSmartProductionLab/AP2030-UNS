#pragma once

#include <behaviortree_cpp/behavior_tree.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/subscription_manager.h"

using nlohmann::json;

class MqttConditionNode : public BT::ConditionNode, public MqttSubBase
{
protected:
    json latest_msg_;

public:
    MqttConditionNode(const std::string &name,
                      const BT::NodeConfig &config,
                      Proxy &proxy,
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
        SubscriptionManager &subscription_manager,
        Proxy &proxy,
        const std::string &node_name,
        const std::string &response_topic,
        const std::string &response_schema_path)
    {
        // Store configuration in a static map that persists throughout program execution
        static std::unordered_map<std::string, std::tuple<std::string, std::string>> node_configs;
        node_configs[node_name] = std::make_tuple(response_topic, response_schema_path);

        MqttConditionNode::setSubscriptionManager(&subscription_manager);
        subscription_manager.registerNodeType<DerivedNode>(response_topic);

        Proxy *proxy_ptr = &proxy;
        // Register a builder that captures the configuration
        factory.registerBuilder<DerivedNode>(
            node_name,
            [proxy_ptr, node_name](const std::string &name, const BT::NodeConfig &config)
            {
                // Get the stored configuration
                auto &[resp_topic, resp_schema] = node_configs[node_name];

                auto node = std::make_unique<DerivedNode>(name, config, *proxy_ptr, resp_topic, resp_schema);
                return node;
            });
    }
};

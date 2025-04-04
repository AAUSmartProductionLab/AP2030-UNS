#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/mqtt_pub_base.h"
#include "mqtt/subscription_manager.h"

class Proxy;

using nlohmann::json;

class MqttActionNode : public BT::StatefulActionNode, public MqttPubBase, public MqttSubBase
{

    // Mutex for thread safety

public:
    MqttActionNode(const std::string &name,
                   const BT::NodeConfig &config,
                   Proxy &proxy,
                   const std::string &request_topic,
                   const std::string &response_topic,
                   const std::string &request_schema_path,
                   const std::string &response_schema_path,
                   const bool &retain = false,
                   const int &qos = 0);

    virtual ~MqttActionNode();

    // Default ports implementation
    static BT::PortsList providedPorts();

    // Create message to be implemented by derived classes
    virtual json createMessage() = 0;

    // Override the virtual callback method from base class
    virtual void callback(const json &msg, mqtt::properties props) override;

    // BT::StatefulActionNode interface implementation
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        SubscriptionManager &subscription_manager,
        Proxy &proxy,
        const std::string &node_name,
        const std::string &request_topic,
        const std::string &response_topic,
        const std::string &request_schema_path,
        const std::string &response_schema_path)
    {
        // Store configuration in a static map that persists throughout program execution
        static std::unordered_map<std::string, std::tuple<std::string, std::string, std::string, std::string>> node_configs;
        node_configs[node_name] = std::make_tuple(request_topic, response_topic, request_schema_path, response_schema_path);

        MqttActionNode::setSubscriptionManager(&subscription_manager);
        subscription_manager.registerNodeType<DerivedNode>(response_topic);
        Proxy *proxy_ptr = &proxy;
        // Register a builder that captures the configuration
        factory.registerBuilder<DerivedNode>(
            node_name,
            [proxy_ptr, node_name](const std::string &name, const BT::NodeConfig &config)
            {
                // Get the stored configuration
                auto &[req_topic, resp_topic, req_schema, resp_schema] = node_configs[node_name];

                // Create the node with proper arguments
                auto node = std::make_unique<DerivedNode>(name, config, *proxy_ptr, req_topic, resp_topic, req_schema, resp_schema);
                return node;
            });
    }
};
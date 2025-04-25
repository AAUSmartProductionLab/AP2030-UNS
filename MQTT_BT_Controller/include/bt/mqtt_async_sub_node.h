#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/mqtt_pub_base.h"
#include "mqtt/node_message_distributor.h"

class MqttClient;

using nlohmann::json;

class MqttAsyncSubNode : public BT::StatefulActionNode, public MqttSubBase
{

public:
    MqttAsyncSubNode(const std::string &name,
                     const BT::NodeConfig &config,
                     MqttClient &mqtt_client,
                     const std::string &response_topic,
                     const std::string &response_schema_path,
                     const bool &retain = false,
                     const int &qos = 0);

    virtual ~MqttAsyncSubNode();

    // Default ports implementation
    static BT::PortsList providedPorts();

    // Override the virtual callback method from base class
    virtual void callback(const json &msg, mqtt::properties props) override;
    bool isInterestedIn(const json &msg) override;

    // BT::StatefulActionNode interface implementation
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;

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

        MqttAsyncSubNode::setNodeMessageDistributor(&node_message_distributor);
        node_message_distributor.registerNodeType<DerivedNode>(response_topic, subqos);
        MqttClient *mqtt_client_ptr = &mqtt_client;
        // Register a builder that captures the configuration
        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr, node_name](const std::string &name, const BT::NodeConfig &config)
            {
                // Get the stored configuration
                auto &[resp_topic, resp_schema] = node_configs[node_name];

                // Create the node with proper arguments
                auto node = std::make_unique<DerivedNode>(name, config, *mqtt_client_ptr, resp_topic, resp_schema);
                return node;
            });
    }
};
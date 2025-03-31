#pragma once

#include <behaviortree_cpp/behavior_tree.h>
#include <behaviortree_cpp/bt_factory.h> // Add this include
#include <nlohmann/json.hpp>
#include <mutex>
#include <atomic>
#include "mqtt/proxy.h"
#include "mqtt/subscription_manager.h"
#include "mqtt/subscription_manager_client.h"

using json = nlohmann::json;

class MqttConditionNode : public BT::ConditionNode, public SubscriptionManagerClient
{
protected:
    Proxy &proxy_;
    std::string uns_topic_;
    std::string response_schema_path_;
    std::string field_name_;

    json latest_msg_;
    std::mutex value_mutex_;
    static SubscriptionManager *subscription_manager_;

public:
    MqttConditionNode(const std::string &name,
                      const BT::NodeConfig &config,
                      Proxy &proxy,
                      const std::string &uns_topic,
                      const std::string &response_schema_path);

    ~MqttConditionNode() override;

    // Static method to set the subscription manager
    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        SubscriptionManager &subscription_manager,
        const std::string &node_name,
        const std::string &topic,
        const std::string &response_schema_path,
        Proxy &proxy)
    {
        // Set the subscription manager for all node instances
        setSubscriptionManager(&subscription_manager);

        // Register with subscription manager
        subscription_manager.registerNodeType<DerivedNode>(topic, response_schema_path);

        // Register with behavior tree factory
        factory.registerNodeType<DerivedNode>(node_name, std::ref(proxy));
    }

    static void setSubscriptionManager(SubscriptionManager *manager);
    static BT::PortsList providedPorts();

    // From SubscriptionManagerClient
    void handleMessage(const json &msg, mqtt::properties props) override;

    virtual bool isInterestedIn(const std::string &field, const json &value);

    // From BT::ConditionNode
    void callback(const json &msg, mqtt::properties props);

    virtual BT::NodeStatus tick() = 0;

    // Static methods
};
#pragma once

#include <behaviortree_cpp/behavior_tree.h>
#include <nlohmann/json.hpp>
#include <mutex>
#include <atomic>
#include "mqtt/proxy.h"
#include "mqtt/subscription_manager_client.h"

using json = nlohmann::json;

class SubscriptionManager;

class MqttValueComparisonCondition : public BT::ConditionNode, public SubscriptionManagerClient
{
protected:
    Proxy &proxy_;
    std::string uns_topic_;
    std::string response_schema_path_;
    std::string field_name_;

    json latest_value_;
    std::mutex value_mutex_;
    static SubscriptionManager *subscription_manager_;

public:
    MqttValueComparisonCondition(const std::string &name,
                                 const BT::NodeConfig &config,
                                 Proxy &proxy,
                                 const std::string &uns_topic,
                                 const std::string &response_schema_path);

    ~MqttValueComparisonCondition() override;

    // From BT::ConditionNode
    BT::NodeStatus tick() override;

    // From SubscriptionManagerClient
    void handleMessage(const json &msg, mqtt::properties props) override;
    bool isInterestedIn(const std::string &field, const json &value) override;

    // Static methods
    static BT::PortsList providedPorts();
    static void setSubscriptionManager(SubscriptionManager *manager);
};
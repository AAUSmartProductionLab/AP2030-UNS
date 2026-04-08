#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include <deque>
#include "aas/aas_client.h"

class ConfigurationNode : public BT::StatefulActionNode
{

public:
    ConfigurationNode(
        const std::string &name,
        const BT::NodeConfig &config,
        AASClient &aas_client)
        : BT::StatefulActionNode(name, config), aas_client_(aas_client) {}

    static BT::PortsList providedPorts();
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override { return BT::NodeStatus::RUNNING; }
    void onHalted() override {}

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        AASClient &aas_client,
        const std::string &node_name)
    {
        factory.registerBuilder<DerivedNode>(
            node_name,
            [&aas_client](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(name, config, aas_client);
            });
    }

private:
    AASClient &aas_client_;
    std::shared_ptr<std::deque<std::string>> shared_queue = std::make_shared<std::deque<std::string>>();
};
#pragma once

#include <behaviortree_cpp/behavior_tree.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/node_message_distributor.h"
#include "utils.h"
#include "aas/aas_client.h"

class MqttSyncConditionNode : public BT::ConditionNode, public MqttSubBase
{
protected:
    json latest_msg_;
    AASClient &aas_client_;
    json station_config_;

public:
    MqttSyncConditionNode(const std::string &name,
                          const BT::NodeConfig &config,
                          MqttClient &mqtt_client,
                          AASClient &aas_client,
                          const json &station_config);

    ~MqttSyncConditionNode() override;
    void initialize();

    static BT::PortsList providedPorts();

    // Override callback to store the latest message
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;

    virtual BT::NodeStatus tick() override;
    virtual void initializeTopicsFromAAS();
    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &distributor,
        MqttClient &mqtt_client,
        AASClient &aas_client,
        const json &station_config,
        const std::string &node_name)
    {
        MqttSubBase::setNodeMessageDistributor(&distributor);
        factory.registerBuilder<DerivedNode>(
            node_name,
            [&mqtt_client, &aas_client, &station_config](const std::string &name, const BT::NodeConfig &config)
            {
                auto node = std::make_unique<DerivedNode>(name, config, mqtt_client, aas_client, station_config);
                node->initialize(); // Call after construction is complete
                return node;
            });
    }
    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};

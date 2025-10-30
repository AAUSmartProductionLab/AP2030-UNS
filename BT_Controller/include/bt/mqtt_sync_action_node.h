#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <nlohmann/json.hpp>
#include "aas/aas_client.h"
#include "mqtt/node_message_distributor.h"

class MqttSyncActionNode : public BT::SyncActionNode, public MqttPubBase, public MqttSubBase
{
protected:
    std::string current_uuid_;

    AASClient &aas_client_;

public:
    MqttSyncActionNode(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client);
    virtual ~MqttSyncActionNode();
    void initialize();

    // Mqtt AAS Stuff
    virtual void initializeTopicsFromAAS();
    virtual json createMessage();
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;
    // BT Stuff
    static BT::PortsList providedPorts();
    BT::NodeStatus tick() override;

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &distributor,
        MqttClient &mqtt_client,
        AASClient &aas_client,
        const std::string &node_name)
    {
        MqttSubBase::setNodeMessageDistributor(&distributor);
        factory.registerBuilder<DerivedNode>(
            node_name,
            [&mqtt_client, &aas_client](const std::string &name, const BT::NodeConfig &config)
            {
                auto node = std::make_unique<DerivedNode>(name, config, mqtt_client, aas_client);
                node->initialize(); // Call after construction is complete
                return node;
            });
    }

    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};
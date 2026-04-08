#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/mqtt_pub_base.h"
#include "mqtt/node_message_distributor.h"
#include "aas/aas_client.h"
#include <map>

class MqttActionNode : public BT::StatefulActionNode, public MqttPubBase, public MqttSubBase
{
protected:
    std::string current_uuid_;

    AASClient &aas_client_;
    bool topics_initialized_ = false;

    /// @brief Called from tick() to perform lazy initialization if needed
    /// @return true if initialization is complete, false if still pending
    bool ensureInitialized();

public:
    MqttActionNode(const std::string &name,
                   const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   AASClient &aas_client) : BT::StatefulActionNode(name, config),
                                                           MqttPubBase(mqtt_client),
                                                           MqttSubBase(mqtt_client),
                                                           aas_client_(aas_client)
    {
    }

    virtual ~MqttActionNode();
    void initialize();

    // Mqtt AAS Stuff
    virtual void initializeTopicsFromAAS() {};
    virtual nlohmann::json createMessage();
    virtual void callback(const std::string &topic_key, const nlohmann::json &msg, mqtt::properties props) override;
    // BT Stuff
    static BT::PortsList providedPorts() { return {}; };
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;

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
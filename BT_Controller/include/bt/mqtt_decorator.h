#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
#include <utils.h>

class MqttDecorator : public BT::DecoratorNode, public MqttPubBase, public MqttSubBase
{
protected:
    AASClient &aas_client_;
    json station_config_;

public:
    MqttDecorator(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client,
        const json &station_config);

    virtual ~MqttDecorator();
    void initialize();

    // Mqtt AAS Stuff
    virtual void initializeTopicsFromAAS();
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;
    // BT Stuff
    static BT::PortsList providedPorts();
    virtual void halt() override;

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
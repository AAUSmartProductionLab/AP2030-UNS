#pragma once

#include <behaviortree_cpp/behavior_tree.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/node_message_distributor.h"

using nlohmann::json;

class MqttSyncSubNode : public BT::ConditionNode, public MqttSubBase
{
protected:
    json latest_msg_;

public:
    MqttSyncSubNode(const std::string &name,
                    const BT::NodeConfig &config,
                    MqttClient &mqtt_client,
                    const std::string &response_topic,
                    const std::string &response_schema_path,
                    const int &subqos);

    ~MqttSyncSubNode() override;

    static BT::PortsList providedPorts();

    // Override callback to store the latest message
    void callback(const json &msg, mqtt::properties props) override;

    virtual BT::NodeStatus tick() override;

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &node_message_distributor,
        MqttClient &mqtt_client,
        const std::string &node_name,
        const std::string &response_topic,
        const std::string &response_schema_path,
        const int &subqos)
    {
        MqttSyncSubNode::setNodeMessageDistributor(&node_message_distributor);

        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr = &mqtt_client,
             response_topic,
             response_schema_path,
             subqos](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name,
                    config,
                    *mqtt_client_ptr,
                    response_topic,
                    response_schema_path,
                    subqos);
            });
    }
    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};

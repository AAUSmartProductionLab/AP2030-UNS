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
                     const mqtt_utils::Topic &response_topic);

    virtual ~MqttAsyncSubNode();

    // Default ports implementation
    static BT::PortsList providedPorts();

    // Override the virtual callback method from base class
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;

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
        const mqtt_utils::Topic &response_topic)
    {
        MqttAsyncSubNode::setNodeMessageDistributor(&node_message_distributor);

        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr = &mqtt_client,
             response_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name,
                    config,
                    *mqtt_client_ptr,
                    response_topic);
            });
    }
    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};
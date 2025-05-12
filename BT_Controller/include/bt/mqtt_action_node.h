#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/mqtt_pub_base.h"
#include "mqtt/node_message_distributor.h"

class MqttClient;

using nlohmann::json;

class MqttActionNode : public BT::StatefulActionNode, public MqttPubBase, public MqttSubBase
{
protected:
    std::string current_uuid_;

public:
    MqttActionNode(const std::string &name,
                   const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   const mqtt_utils::Topic &request_topic,
                   const mqtt_utils::Topic &response_topic);

    MqttActionNode(const std::string &name, const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   const mqtt_utils::Topic &request_topic,
                   const mqtt_utils::Topic &response_topic,
                   const mqtt_utils::Topic &halt_topic);

    virtual ~MqttActionNode();

    // Default ports implementation
    static BT::PortsList providedPorts();

    // Create message to be implemented by derived classes
    virtual json createMessage() = 0;

    // Override the virtual callback method from base class
    virtual void callback(const json &msg, mqtt::properties props) override;

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
        const mqtt_utils::Topic &request_topic,
        const mqtt_utils::Topic &response_topic)
    {
        MqttActionNode::setNodeMessageDistributor(&node_message_distributor);

        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr = &mqtt_client,
             request_topic,
             response_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name, config, *mqtt_client_ptr,
                    request_topic, response_topic);
            });
    }

    // Special registration for nodes that need halt_topic
    template <typename DerivedNode>
    static void registerNodeTypeWithHalt(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &node_message_distributor,
        MqttClient &mqtt_client,
        const std::string &node_name,
        const mqtt_utils::Topic &request_topic,
        const mqtt_utils::Topic &response_topic,
        const mqtt_utils::Topic &halt_topic)
    {
        MqttActionNode::setNodeMessageDistributor(&node_message_distributor);

        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr = &mqtt_client,
             request_topic,
             response_topic,
             halt_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name, config, *mqtt_client_ptr,
                    request_topic, response_topic, halt_topic);
            });
    }
    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};
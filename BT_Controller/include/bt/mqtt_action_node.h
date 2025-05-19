#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "mqtt/mqtt_sub_base.h"
#include "mqtt/mqtt_pub_base.h"
#include "mqtt/node_message_distributor.h"
#include <map> // Ensure this is included

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
                   const mqtt_utils::Topic &request_topic_pattern,
                   const mqtt_utils::Topic &response_topic_pattern)
        : BT::StatefulActionNode(name, config),
          MqttPubBase(mqtt_client, {{"request", request_topic_pattern}}),
          MqttSubBase(mqtt_client, {{"response", response_topic_pattern}})
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }
    MqttActionNode(const std::string &name, const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   const mqtt_utils::Topic &request_topic_pattern,
                   const mqtt_utils::Topic &response_topic_pattern,
                   const mqtt_utils::Topic &halt_topic_pattern)
        : BT::StatefulActionNode(name, config),
          MqttPubBase(mqtt_client, {{"request", request_topic_pattern},
                                    {"halt", halt_topic_pattern}}),
          MqttSubBase(mqtt_client, {{"response", response_topic_pattern}})
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }

    virtual ~MqttActionNode()
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->unregisterInstance(this);
        }
    }

    static BT::PortsList providedPorts();
    virtual json createMessage() = 0;
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override; // Make it pure virtual if MqttActionNode itself doesn't provide a generic implementation

    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &distributor,
        MqttClient &mqtt_client,
        const std::string &node_name,
        const mqtt_utils::Topic &request_topic,
        const mqtt_utils::Topic &response_topic)
    {
        MqttSubBase::setNodeMessageDistributor(&distributor);
        factory.registerBuilder<DerivedNode>(
            node_name,
            [&mqtt_client, request_topic, response_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(name, config, mqtt_client, request_topic, response_topic);
            });
    }

    template <typename DerivedNode>
    static void registerNodeTypeWithHalt(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &distributor,
        MqttClient &mqtt_client,
        const std::string &node_name,
        const mqtt_utils::Topic &request_topic,
        const mqtt_utils::Topic &response_topic,
        const mqtt_utils::Topic &halt_topic)
    {
        MqttSubBase::setNodeMessageDistributor(&distributor);
        factory.registerBuilder<DerivedNode>(
            node_name,
            [&mqtt_client, request_topic, response_topic, halt_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(name, config, mqtt_client, request_topic, response_topic, halt_topic);
            });
    }
    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};
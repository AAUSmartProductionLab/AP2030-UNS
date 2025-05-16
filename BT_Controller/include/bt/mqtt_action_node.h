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
    // Constructor for nodes WITHOUT a separate halt topic (uses "request" and "response" keys)
    MqttActionNode(const std::string &name,
                   const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   const mqtt_utils::Topic &request_topic_pattern,  // Pattern for publishing requests
                   const mqtt_utils::Topic &response_topic_pattern) // Pattern for subscribing to responses
        : BT::StatefulActionNode(name, config),
          MqttPubBase(mqtt_client, {{"request", request_topic_pattern}}),
          MqttSubBase(mqtt_client, {{"response", response_topic_pattern}})
    {
        // Initialize node_message_distributor_ if not already done by MqttSubBase static setter
        // MqttSubBase::setNodeMessageDistributor(distributor); // If passed in
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }

    // Constructor for nodes WITH a separate halt topic (uses "request", "halt", and "response" keys)
    MqttActionNode(const std::string &name, const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   const mqtt_utils::Topic &request_topic_pattern,  // Pattern for publishing requests
                   const mqtt_utils::Topic &response_topic_pattern, // Pattern for subscribing to responses
                   const mqtt_utils::Topic &halt_topic_pattern)     // Pattern for publishing halt messages
        : BT::StatefulActionNode(name, config),
          MqttPubBase(mqtt_client, {{"request", request_topic_pattern},
                                    {"halt", halt_topic_pattern}}),
          MqttSubBase(mqtt_client, {{"response", response_topic_pattern}})
    {
        // MqttSubBase::setNodeMessageDistributor(distributor); // If passed in
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

    // Default ports implementation
    static BT::PortsList providedPorts();

    // Create message to be implemented by derived classes
    virtual json createMessage() = 0;

    // Override the virtual callback method from base class
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override; // Make it pure virtual if MqttActionNode itself doesn't provide a generic implementation

    // BT::StatefulActionNode interface implementation
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        NodeMessageDistributor &distributor, // Keep if used
        MqttClient &mqtt_client,
        const std::string &node_name,
        const mqtt_utils::Topic &request_topic,
        const mqtt_utils::Topic &response_topic)
    {
        MqttSubBase::setNodeMessageDistributor(&distributor); // Ensure distributor is set before node creation
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
        NodeMessageDistributor &distributor, // Keep if used
        MqttClient &mqtt_client,
        const std::string &node_name,
        const mqtt_utils::Topic &request_topic,
        const mqtt_utils::Topic &response_topic,
        const mqtt_utils::Topic &halt_topic)
    {
        MqttSubBase::setNodeMessageDistributor(&distributor); // Ensure distributor is set before node creation
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
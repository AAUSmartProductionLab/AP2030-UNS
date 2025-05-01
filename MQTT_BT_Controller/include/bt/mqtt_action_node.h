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
    std::string current_command_uuid_;

public:
    MqttActionNode(const std::string &name,
                   const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   const std::string &request_topic,
                   const std::string &response_topic,
                   const std::string &request_schema_path,
                   const std::string &response_schema_path,
                   const bool &retain,
                   const int &pubqos,
                   const int &subqos);

    virtual ~MqttActionNode();

    // Default ports implementation
    static BT::PortsList providedPorts();

    // Create message to be implemented by derived classes
    virtual json createMessage() = 0;

    // Override the virtual callback method from base class
    virtual void callback(const json &msg, mqtt::properties props) override;
    bool isInterestedIn(const json &msg) override;

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
        const std::string &request_topic,
        const std::string &response_topic,
        const std::string &request_schema_path,
        const std::string &response_schema_path,
        const bool &retain,
        const int &pubqos,
        const int &subqos)
    {
        MqttActionNode::setNodeMessageDistributor(&node_message_distributor);

        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr = &mqtt_client,
             request_topic,
             response_topic,
             request_schema_path,
             response_schema_path,
             retain,
             pubqos,
             subqos](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name,
                    config,
                    *mqtt_client_ptr,
                    request_topic,
                    response_topic,
                    request_schema_path,
                    response_schema_path,
                    retain,
                    pubqos,
                    subqos);
            });
    }
    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};
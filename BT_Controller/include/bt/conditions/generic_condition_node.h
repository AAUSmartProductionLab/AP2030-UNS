#pragma once

#include "bt/mqtt_sync_sub_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

class GenericConditionNode : public MqttSyncSubNode
{
public:
    GenericConditionNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                         const mqtt_utils::Topic &response_topic);
    virtual ~GenericConditionNode();
    static BT::PortsList providedPorts();

    BT::NodeStatus tick() override;
    virtual void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;
    bool compare(const json &msg, const std::string &field_name, const std::string &comparison_type,
                 const std::string &expected_value);
    std::string getFormattedTopic(const std::string &pattern);
};
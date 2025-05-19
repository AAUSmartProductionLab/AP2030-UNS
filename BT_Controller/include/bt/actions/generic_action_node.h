#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

class GenericActionNode : public MqttActionNode
{
public:
    GenericActionNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                      const mqtt_utils::Topic &request_topic,
                      const mqtt_utils::Topic &response_topic);

    virtual ~GenericActionNode();
    json createMessage() override;
};
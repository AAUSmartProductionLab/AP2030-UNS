#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class MoveShuttleToPosition : public MqttActionNode
{
private:
    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config);

public:
    MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                          const mqtt_utils::Topic &request_topic,
                          const mqtt_utils::Topic &response_topic,
                          const mqtt_utils::Topic &halt_topic);
    virtual ~MoveShuttleToPosition();
    static BT::PortsList providedPorts();
    void onHalted() override;
    json createMessage() override;
};
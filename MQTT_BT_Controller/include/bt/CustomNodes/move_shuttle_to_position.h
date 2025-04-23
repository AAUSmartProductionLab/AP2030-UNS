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
    static std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config);
public:
    MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                          const std::string &request_topic,
                          const std::string &response_topic,
                          const std::string &request_schema_path,
                          const std::string &response_schema_path,
                          const bool &retain = false,
                          const int &pubqos = 0);

    static BT::PortsList providedPorts();

    json createMessage() override;
};
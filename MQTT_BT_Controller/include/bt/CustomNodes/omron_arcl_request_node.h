#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class OmronArclRequest : public MqttActionNode
{

public:
    OmronArclRequest(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                     const std::string &request_topic,
                     const std::string &response_topic,
                     const std::string &request_schema_path,
                     const std::string &response_schema_path);

    static BT::PortsList providedPorts();

    json createMessage() override;

    // Override isInterestedIn to filter messages
    bool isInterestedIn(const json &msg) override;

    void callback(const json &msg, mqtt::properties props) override;
};

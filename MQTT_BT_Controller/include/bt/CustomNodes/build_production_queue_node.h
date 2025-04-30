#pragma once

#include "bt/mqtt_async_sub_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class BuildProductionQueueNode : public MqttAsyncSubNode
{
public:
    BuildProductionQueueNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                             const std::string &response_topic,
                             const std::string &response_schema_path,
                             const int &subqos);

    static BT::PortsList providedPorts();
    void callback(const json &msg, mqtt::properties props) override;
};
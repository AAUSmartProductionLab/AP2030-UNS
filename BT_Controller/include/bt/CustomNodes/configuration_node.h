#pragma once

#include "bt/mqtt_async_sub_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include <deque>

// Forward declarations
class MqttClient;
using nlohmann::json;

// MoveShuttleToPosition class declaration
class ConfigurationNode : public MqttAsyncSubNode
{
public:
    ConfigurationNode(const std::string &name, const BT::NodeConfig &config, MqttClient &bt_mqtt_client,
                      const mqtt_utils::Topic &response_topic);

    static BT::PortsList providedPorts();
    void callback(const json &msg, mqtt::properties props) override;
    std::shared_ptr<std::deque<std::string>> shared_queue;
    std::map<std::string, int> stationMap;
};
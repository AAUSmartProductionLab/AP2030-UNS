#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class Proxy;
using nlohmann::json;

// Position2D struct definition
struct Position2D
{
    double x;
    double y;
};

// Template specialization declaration
namespace BT
{
    template <>
    Position2D convertFromString(StringView str);
}

// MoveShuttleToPosition class declaration
class MoveShuttleToPosition : public MqttActionNode
{
private:
    std::string current_command_uuid_;

public:
    MoveShuttleToPosition(const std::string &name, const BT::NodeConfig &config, Proxy &bt_proxy);

    static BT::PortsList providedPorts();

    json createMessage();

    // Override isInterestedIn to filter messages
    bool isInterestedIn(const std::string &field, const json &value) override;

    void callback(const json &msg, mqtt::properties props) override;
};
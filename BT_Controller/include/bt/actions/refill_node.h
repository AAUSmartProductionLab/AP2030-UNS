#pragma once

#include "bt/mqtt_action_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include "utils.h"
#include <string>

// Forward declarations
class MqttClient;

class RefillNode : public MqttActionNode
{
private:
    double weight_ = 0.0;

public:
    RefillNode(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client)
        : MqttActionNode(name, config, mqtt_client, aas_client) {}

    void initializeTopicsFromAAS() override;
    static BT::PortsList providedPorts();
    json createMessage() override;
    std::string getFormattedTopic(const std::string &pattern);
    void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;
};
#pragma once

#include "bt/mqtt_decorator.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "aas/aas_client.h"
#include "mqtt/mqtt_pub_base.h"

class GetProductFromQueue : public MqttDecorator
{
private:
    bool child_running_ = false;
    BT::SharedQueue<std::string> queue_;

public:
    GetProductFromQueue(const std::string &name,
                        const BT::NodeConfig &config,
                        MqttClient &mqtt_client,
                        AASClient &aas_client)
        : MqttDecorator(name, config, mqtt_client, aas_client) {}

    void initializeTopicsFromAAS() override;

    BT::NodeStatus tick() override;
    static BT::PortsList providedPorts();
};
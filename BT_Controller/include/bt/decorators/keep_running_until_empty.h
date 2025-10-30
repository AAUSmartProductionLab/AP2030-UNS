#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include "bt/mqtt_decorator.h"
#include <string>

class KeepRunningUntilEmpty : public MqttDecorator
{
private:
    BT::SharedQueue<std::string> queue_ptr_from_bb_;

public:
    KeepRunningUntilEmpty(const std::string &name,
                          const BT::NodeConfig &config,
                          MqttClient &mqtt_client,
                          AASClient &aas_client,
                          const json &station_config)
        : MqttDecorator(name, config, mqtt_client, aas_client, station_config)
    {
    }

    BT::NodeStatus tick() override;
    void initializeTopicsFromAAS() override {}
    static BT::PortsList providedPorts();
};
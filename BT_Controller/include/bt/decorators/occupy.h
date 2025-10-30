#pragma once

#include "bt/mqtt_decorator.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
#include <utils.h>

class Occupy : public MqttDecorator
{
private:
    std::string current_uuid_;
    std::mutex mutex_;
    PackML::State current_phase_ = PackML::State::IDLE;

public:
    Occupy(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client,
        const json &station_config)
        : MqttDecorator(name, config, mqtt_client, aas_client, station_config)
    {
    }

    // Mqtt AAS Stuff
    void initializeTopicsFromAAS() override;
    void sendRegisterCommand();
    void sendUnregisterCommand();
    void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;

    // BT Stuff
    BT::NodeStatus tick() override;
    void halt() override;

    static BT::PortsList providedPorts();
};
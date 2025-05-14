#include "mqtt/mqtt_sub_base.h"
#include "mqtt/node_message_distributor.h"
#include "utils.h"
#include <iostream>

namespace fs = std::filesystem;
// Initialize the static member
NodeMessageDistributor *MqttSubBase::node_message_distributor_ = nullptr;

MqttSubBase::MqttSubBase(MqttClient &mqtt_client,
                         const mqtt_utils::Topic &response_topic)
    : mqtt_client_(mqtt_client),
      response_topic_(response_topic)
{
    response_topic_.initValidator();
}

void MqttSubBase::processMessage(const json &msg, mqtt::properties props)
{
    if (response_topic_.validateMessage(msg))
    {
        callback(msg, props);
    }
}

void MqttSubBase::setNodeMessageDistributor(NodeMessageDistributor *manager)
{
    node_message_distributor_ = manager;
}
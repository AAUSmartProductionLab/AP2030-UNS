#include "mqtt/mqtt_node_base.h"
#include "mqtt/subscription_manager.h"
#include <iostream>

// Initialize the static member
SubscriptionManager *MqttNodeBase::subscription_manager_ = nullptr;

MqttNodeBase::MqttNodeBase(Proxy &proxy,
                           const std::string &uns_topic,
                           const std::string &response_schema_path)
    : proxy_(proxy),
      uns_topic_(uns_topic),
      response_schema_path_(response_schema_path)
{
    // Registration happens in derived classes
}

void MqttNodeBase::handleMessage(const json &msg, mqtt::properties props)
{
    callback(msg, props);
}

bool MqttNodeBase::isInterestedIn(const std::string &field, const json &value)
{
    std::cout << "Base isInterestedIn called - this should be overridden!" << std::endl;
    return false;
}

void MqttNodeBase::setSubscriptionManager(SubscriptionManager *manager)
{
    subscription_manager_ = manager;
}
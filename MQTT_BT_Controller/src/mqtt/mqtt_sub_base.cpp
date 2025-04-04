#include "mqtt/mqtt_sub_base.h"
#include "mqtt/subscription_manager.h"
#include <iostream>

// Initialize the static member
SubscriptionManager *MqttSubBase::subscription_manager_ = nullptr;

MqttSubBase::MqttSubBase(Proxy &proxy,
                         const std::string &response_topic = "",
                         const std::string &response_schema_path = "")
    : proxy_(proxy),
      response_topic_(response_topic),
      response_schema_path_(response_schema_path)
{
    // Registration happens in derived classes
}

void MqttSubBase::handleMessage(const json &msg, mqtt::properties props)
{
    // TODO this must handle JSON validation
    callback(msg, props);
}

bool MqttSubBase::isInterestedIn(const std::string &field, const json &value)
{
    std::cout << "Base isInterestedIn called - this should be overridden!" << std::endl;
    return false;
}

void MqttSubBase::setSubscriptionManager(SubscriptionManager *manager)
{
    subscription_manager_ = manager;
}
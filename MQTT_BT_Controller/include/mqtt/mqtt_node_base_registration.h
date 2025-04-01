#pragma once

#include "mqtt/mqtt_node_base.h"
#include "mqtt/subscription_manager.h"
#include <behaviortree_cpp/bt_factory.h>

// Common registration template for all MqttBT nodes
//  This function registers the node type with both the BehaviorTreeFactory and the SubscriptionManager
//  It sets the subscription manager for all node instances and registers the node type with the subscription manager
template <typename DerivedNode>
void MqttNodeBase::registerNodeType(
    BT::BehaviorTreeFactory &factory,
    SubscriptionManager &subscription_manager,
    const std::string &node_name,
    const std::string &topic,
    const std::string &response_schema_path,
    Proxy &proxy)
{
    MqttNodeBase::setSubscriptionManager(&subscription_manager);

    subscription_manager.registerNodeType<DerivedNode>(topic, response_schema_path);

    factory.registerNodeType<DerivedNode>(node_name, std::ref(proxy));
}
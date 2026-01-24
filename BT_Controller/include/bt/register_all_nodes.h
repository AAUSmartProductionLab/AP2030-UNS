#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include "mqtt/mqtt_client.h"
#include "aas/aas_client.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"
#include "bt/mqtt_action_node.h"
#include "bt/mqtt_sync_action_node.h"
#include "bt/mqtt_sync_condition_node.h"
#include "bt/mqtt_decorator.h"
#include "bt/actions/move_to_position.h"
#include "bt/actions/generic_action_node.h"
#include "bt/actions/command_execute_node.h"
#include "bt/actions/configuration_node.h"
#include "bt/actions/pop_element_node.h"
#include "bt/actions/refill_node.h"
#include "bt/actions/retrieve_aas_properties_node.h"
#include "bt/conditions/generic_condition_node.h"
#include "bt/decorators/get_product_from_queue_node.h"
#include "bt/decorators/keep_running_until_empty.h"
#include "bt/decorators/occupy.h"
#include "bt/controls/bc_fallback_node.h"
void registerAllNodes(
    BT::BehaviorTreeFactory &factory,
    NodeMessageDistributor &node_message_distributor,
    MqttClient &mqtt_client,
    AASClient &aas_client)
{
    // Register the nodes with the behavior tree and the mqtt client
    MqttActionNode::registerNodeType<MoveToPosition>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        "moveToPosition");

    RetrieveAASPropertyNode::registerNodeType<RetrieveAASPropertyNode>(
        factory,
        aas_client,
        "Retrieve_AAS_Property");

    MqttActionNode::registerNodeType<CommandExecuteNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        "Command_Execution");

    RefillNode::registerNodeType<RefillNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        "Refill_Node");

    MqttSyncConditionNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        "Data_Condition");

    ConfigurationNode::registerNodeType<ConfigurationNode>(
        factory,
        aas_client,
        "Configure");

    MqttDecorator::registerNodeType<GetProductFromQueue>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        "GetProductFromQueue");

    MqttDecorator::registerNodeType<Occupy>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        "Occupy");

    MqttDecorator::registerNodeType<KeepRunningUntilEmpty>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        "KeepRunningUntilEmpty");

    MqttSyncActionNode::registerNodeType<PopElementNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        "PopElement");

    factory.registerNodeType<BT::BC_FallbackNode>("BC_Fallback");
    factory.registerNodeType<BT::BC_FallbackNode>("BC_Fallback_Async", true);
}
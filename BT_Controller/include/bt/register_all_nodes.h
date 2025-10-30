#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include "mqtt/mqtt_client.h"
#include "aas/aas_client.h"
#include "utils.h"
#include "mqtt/node_message_distributor.h"
#include "bt/mqtt_action_node.h"
#include "bt/mqtt_sync_action_node.h"
#include "bt/mqtt_decorator.h"
#include "bt/actions/move_to_position.h"
#include "bt/actions/generic_action_node.h"
#include "bt/actions/command_execute_node.h"
#include "bt/actions/configuration_node.h"
#include "bt/actions/pop_element_node.h"
#include "bt/actions/refill_node.h"
#include "bt/conditions/generic_condition_node.h"
#include "bt/decorators/get_product_from_queue_node.h"
#include "bt/decorators/keep_running_until_empty.h"
#include "bt/decorators/occupy.h"
#include "bt/controls/bc_fallback_node.h"
void registerAllNodes(
    BT::BehaviorTreeFactory &factory,
    NodeMessageDistributor &node_message_distributor,
    MqttClient &mqtt_client,
    AASClient &aas_client,
    json &station_config)
{
    // Define the topics for the nodes (may contain wildcards if replaced using bt entries)
    // mqtt_utils::Topic XYMotionCMD(
    //     unsTopicPrefix + "/+/CMD/XYMotion",
    //     "../../schemas/moveToPosition.schema.json",
    //     2,
    //     false);
    // mqtt_utils::Topic OmronARCLCMD(
    //     unsTopicPrefix + "/Omron/CMD/ARCL",
    //     "../../schemas/amrArclRequest.schema.json",
    //     2,
    //     false);
    // mqtt_utils::Topic StationRegistrationCMD(
    //     unsTopicPrefix + "/+/CMD/Register",
    //     "../../schemas/command.schema.json",
    //     2,
    //     false);
    // mqtt_utils::Topic StationUnregistrationCMD(
    //     unsTopicPrefix + "/+/CMD/Unregister",
    //     "../../schemas/command.schema.json",
    //     2,
    //     false);
    // mqtt_utils::Topic ExecuteCMD(
    //     unsTopicPrefix + "/+/CMD/+",
    //     "../../schemas/command.schema.json",
    //     2,
    //     false);
    // mqtt_utils::Topic OmronARCLState(
    //     unsTopicPrefix + "/Omron/DATA/State",
    //     "../../schemas/amrArclUpdate.schema.json",
    //     2);
    // mqtt_utils::Topic StationState(
    //     unsTopicPrefix + "/+/DATA/State",
    //     "../../schemas/stationState.schema.json",
    //     2);
    // mqtt_utils::Topic CommandResponse(
    //     unsTopicPrefix + "/+/DATA/+",
    //     "../../schemas/commandResponse.schema.json",
    //     2);
    // mqtt_utils::Topic StateData(
    //     unsTopicPrefix + "/+/DATA/State",
    //     "../../schemas/state.schema.json",
    //     2);
    // mqtt_utils::Topic WeightData(
    //     unsTopicPrefix + "/+/DATA/Weight",
    //     "../../schemas/data.schema.json",
    //     2);
    // mqtt_utils::Topic GenericConditonDATA(
    //     unsTopicPrefix + "/+/DATA/+",
    //     "../../schemas/data.schema.json",
    //     2);
    // mqtt_utils::Topic ConfigurationDATA(
    //     unsTopicPrefix + "/Configuration/DATA/#",
    //     "../../schemas/config.schema.json",
    //     2);
    // mqtt_utils::Topic ProductAssociation(
    //     unsTopicPrefix + "/+/DATA/ProductId",
    //     "../../schemas/productId.schema.json",
    //     2,
    //     true);

    // Register the nodes with the behavior tree and the mqtt client
    MqttActionNode::registerNodeType<MoveToPosition>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "MoveToPosition");

    MqttActionNode::registerNodeType<CommandExecuteNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "Command_Execution");

    RefillNode::registerNodeType<RefillNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "Refill_Node");

    MqttActionNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "Data_Condition");

    MqttActionNode::registerNodeType<ConfigurationNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "Configure");

    MqttDecorator::registerNodeType<GetProductFromQueue>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "GetProductFromQueue");

    MqttDecorator::registerNodeType<Occupy>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "Occupy");

    MqttDecorator::registerNodeType<KeepRunningUntilEmpty>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "KeepRunningUntilEmpty");

    MqttSyncActionNode::registerNodeType<PopElementNode>(
        factory,
        node_message_distributor,
        mqtt_client,
        aas_client,
        station_config,
        "PopElement");

    factory.registerNodeType<BT::BC_FallbackNode>("BC_Fallback");
    factory.registerNodeType<BT::BC_FallbackNode>("BC_Fallback_Async", true);
}
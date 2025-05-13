#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include "mqtt/mqtt_client.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"
#include "bt/mqtt_action_node.h"
#include "bt/actions/move_shuttle_to_position.h"
#include "bt/actions/generic_action_node.h"
#include "bt/actions/omron_arcl_request_node.h"
#include "bt/actions/station_start_node.h"
#include "bt/actions/station_complete_node.h"
#include "bt/actions/station_execute_node.h"
#include "bt/actions/configuration_node.h"
#include "bt/conditions/generic_condition_node.h"
#include "bt/decorators/get_product_from_queue_node.h"
#include "bt/controls/bc_fallback_node.h"

void registerAllNodes(
    BT::BehaviorTreeFactory &factory,
    NodeMessageDistributor &node_message_distributor,
    MqttClient &bt_mqtt_client,
    const std::string &unsTopicPrefix)
{
    // Define the topics for the nodes (may contain wildcards if replaced using bt entries)
    mqtt_utils::Topic XYMotionCMD(
        unsTopicPrefix + "/+/CMD/XYMotion",
        "../../schemas/moveToPosition.schema.json",
        2,
        false);
    mqtt_utils::Topic OmronARCLCMD(
        unsTopicPrefix + "/Omron/CMD/ARCL",
        "../../schemas/amrArclRequest.schema.json",
        2,
        false);
    mqtt_utils::Topic StationRegistrationCMD(
        unsTopicPrefix + "/+/CMD/Start",
        "../../schemas/command.schema.json",
        2,
        false);
    mqtt_utils::Topic StationUnregistrationCMD(
        unsTopicPrefix + "/+/CMD/Complete",
        "../../schemas/command.schema.json",
        2,
        false);
    mqtt_utils::Topic StationExecuteCMD(
        unsTopicPrefix + "/+/CMD/+",
        "../../schemas/command.schema.json",
        2,
        false);
    mqtt_utils::Topic OmronARCLState(
        unsTopicPrefix + "/Omron/DATA/State",
        "../../schemas/amrArclUpdate.schema.json",
        2);
    mqtt_utils::Topic StationState(
        unsTopicPrefix + "/+/DATA/State",
        "../../schemas/stationState.schema.json",
        2);
    mqtt_utils::Topic StationCommandResponse(
        unsTopicPrefix + "/+/DATA/+",
        "../../schemas/commandResponse.schema.json",
        2);
    mqtt_utils::Topic StateData(
        unsTopicPrefix + "/+/DATA/State",
        "../../schemas/state.schema.json",
        2);
    mqtt_utils::Topic GenericConditonDATA(
        unsTopicPrefix + "/+/DATA/+",
        "../../schemas/data.schema.json",
        2);
    mqtt_utils::Topic ConfigurationDATA(
        unsTopicPrefix + "/Configuration/DATA/#",
        "../../schemas/config.schema.json",
        2);
    mqtt_utils::Topic ProductAssociation(
        unsTopicPrefix + "/+/DATA/ProductId",
        "../../schemas/productId.schema.json",
        2,
        true);

    // Register the nodes with the behavior tree and the mqtt client
    MqttActionNode::registerNodeTypeWithHalt<MoveShuttleToPosition>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "MoveShuttle",
        XYMotionCMD, StateData, XYMotionCMD);

    MqttActionNode::registerNodeType<OmronArclRequest>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "OmronArclRequest",
        OmronARCLCMD,
        OmronARCLState);

    MqttActionNode::registerNodeTypeWithHalt<StationStartNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Start",
        StationRegistrationCMD,
        StateData,
        StationUnregistrationCMD);

    MqttActionNode::registerNodeType<StationCompleteNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Complete",
        StationUnregistrationCMD,
        StateData);

    MqttActionNode::registerNodeType<StationExecuteNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Execution",
        StationExecuteCMD,
        StationCommandResponse);

    MqttSyncSubNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Data_Condition",
        GenericConditonDATA);

    MqttAsyncSubNode::registerNodeType<ConfigurationNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Configure",
        ConfigurationDATA);

    GetProductFromQueue::registerNodeType<GetProductFromQueue>(
        factory,
        bt_mqtt_client,
        "GetProductFromQueue",
        ProductAssociation);

    factory.registerNodeType<BT::BC_FallbackNode>("BC_Fallback");
    factory.registerNodeType<BT::BC_FallbackNode>("BC_Fallback_Async", true);
}
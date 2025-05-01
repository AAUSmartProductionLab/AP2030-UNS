#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include "mqtt/mqtt_client.h"
#include "mqtt/utils.h"
#include "mqtt/node_message_distributor.h"
#include "bt/mqtt_action_node.h"
#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "bt/CustomNodes/generic_condition_node.h"
#include "bt/CustomNodes/generic_action_node.h"
#include "bt/CustomNodes/omron_arcl_request_node.h"
#include "bt/CustomNodes/station_register_node.h"
#include "bt/CustomNodes/station_unregister_node.h"
#include "bt/CustomNodes/station_execute_node.h"
#include "bt/CustomNodes/build_production_queue_node.h"
#include "bt/CustomNodes/get_product_from_queue_node.h"

void registerAllNodes(
    BT::BehaviorTreeFactory &factory,
    NodeMessageDistributor &node_message_distributor,
    MqttClient &bt_mqtt_client,
    const std::string &unsTopicPrefix)
{
    // Define the topics for the nodes (may contain wildcards if replaced using bt entries)
    mqtt_utils::Topic XYMotionCMD(
        unsTopicPrefix + "/Planar/+/CMD/XYMotion",
        "../../schemas/moveToPosition.schema.json",
        2,
        false);
    mqtt_utils::Topic OmronARCLCMD(
        unsTopicPrefix + "/Omron/CMD/ARCL",
        "../../schemas/amrArclRequest.schema.json",
        2,
        false);
    mqtt_utils::Topic StationRegistrationCMD(
        unsTopicPrefix + "/+/CMD/Register",
        "../../schemas/command.schema.json",
        2,
        false);
    mqtt_utils::Topic StationUnregistrationCMD(
        unsTopicPrefix + "/+/CMD/Unregister",
        "../../schemas/command.schema.json",
        2,
        false);
    mqtt_utils::Topic StationExecuteCMD(
        unsTopicPrefix + "/+/CMD/+",
        "../../schemas/command.schema.json",
        2,
        false);
    mqtt_utils::Topic PlanarState(
        unsTopicPrefix + "/Planar/+/DATA/State",
        "../../schemas/state.schema.json",
        2);
    mqtt_utils::Topic OmronARCLState(
        unsTopicPrefix + "/Omron/DATA/State",
        "../../schemas/amrArclUpdate.schema.json",
        2);
    mqtt_utils::Topic StationState(
        unsTopicPrefix + "/+/DATA/State",
        "../../schemas/stationState.schema.json",
        2);
    mqtt_utils::Topic GenericConditonDATA(
        unsTopicPrefix + "/+/DATA/+",
        "../../schemas/data.schema.json",
        2);
    mqtt_utils::Topic ConfigurationDATA(
        unsTopicPrefix + "/Configurator/DATA/Order",
        "../../schemas/order.schema.json",
        2);

    // Register the nodes with the behavior tree and the mqtt client
    MqttActionNode::registerNodeType<MoveShuttleToPosition>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "MoveShuttle",
        XYMotionCMD, PlanarState);

    MqttActionNode::registerNodeType<OmronArclRequest>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "OmronArclRequest",
        OmronARCLCMD,
        OmronARCLState);

    MqttActionNode::registerNodeType<StationRegisterNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Registration",
        StationRegistrationCMD,
        StationState);

    MqttActionNode::registerNodeType<StationUnRegisterNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Unregistration",
        StationUnregistrationCMD,
        StationState);

    MqttActionNode::registerNodeType<StationExecuteNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Execution",
        StationExecuteCMD,
        StationState);

    MqttSyncSubNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Data_Condition",
        GenericConditonDATA);

    MqttAsyncSubNode::registerNodeType<BuildProductionQueueNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "BuildProductionQueue",
        ConfigurationDATA);

    MqttSyncSubNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_State_Condition",
        StationState);

    factory.registerNodeType<GetProductFromQueue>("GetProductFromQueue");
}
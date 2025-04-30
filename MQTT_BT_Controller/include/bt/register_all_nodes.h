#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include "mqtt/mqtt_client.h"
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
    // Register the nodes with the behavior tree and the mqtt client
    MqttActionNode::registerNodeType<MoveShuttleToPosition>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "MoveShuttle",
        unsTopicPrefix + "/Planar/+/CMD/XYMotion",
        unsTopicPrefix + "/Planar/+/DATA/State",
        "../../schemas/moveToPosition.schema.json",
        "../../schemas/state.schema.json",
        false,
        2,
        2);

    MqttActionNode::registerNodeType<OmronArclRequest>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "OmronArclRequest",
        unsTopicPrefix + "/Omron/CMD/ARCL",
        unsTopicPrefix + "/Omron/DATA/State",
        "../../schemas/amrArclRequest.schema.json",
        "../../schemas/amrArclUpdate.schema.json",
        false,
        2,
        2);

    MqttActionNode::registerNodeType<StationRegisterNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Registration",
        unsTopicPrefix + "/+/CMD/Register",
        unsTopicPrefix + "/+/DATA/State",
        "../../schemas/command.schema.json",
        "../../schemas/stationState.schema.json",
        false,
        2,
        2);

    MqttActionNode::registerNodeType<StationUnRegisterNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Unregistration",
        unsTopicPrefix + "/+/CMD/Unregister",
        unsTopicPrefix + "/+/DATA/State",
        "../../schemas/command.schema.json",
        "../../schemas/stationState.schema.json",
        false,
        2,
        2);

    MqttActionNode::registerNodeType<StationExecuteNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_Execution",
        unsTopicPrefix + "/+/CMD/+",
        unsTopicPrefix + "/+/DATA/State",
        "../../schemas/command.schema.json",
        "../../schemas/stationState.schema.json",
        false,
        2,
        2);

    MqttSyncSubNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Data_Condition",
        unsTopicPrefix + "/+/DATA/+",
        "../../schemas/data.schema.json",
        2);

    MqttAsyncSubNode::registerNodeType<BuildProductionQueueNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "BuildProductionQueue",
        unsTopicPrefix + "/Configurator/DATA/Order",
        "../../schemas/order.schema.json",
        2);

    MqttSyncSubNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Station_State_Condition",
        unsTopicPrefix + "/+/DATA/State",
        "../../schemas/stationState.schema.json",
        2);

    factory.registerNodeType<GetProductFromQueue>("GetProductFromQueue");
}
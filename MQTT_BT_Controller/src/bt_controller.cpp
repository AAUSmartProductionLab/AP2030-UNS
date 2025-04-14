#include <chrono>
#include <functional>
#include <iostream>
#include <fstream>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/xml_parsing.h>

#include "common_constants.h"

#include "mqtt/mqtt_client.h"
#include "bt/mqtt_action_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/utils.h"
#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "bt/CustomNodes/generic_condition_node.h"
#include "bt/CustomNodes/omron_arcl_request_node.h"
int main(int argc, char *argv[])
{
    std::string serverURI = (argc > 1) ? std::string{argv[1]} : BROKER_URI;
    std::string clientId = CLIENT_ID;
    int repetitions = 5;

    // MQTT initialization
    auto connOpts = mqtt::connect_options_builder::v5()
                        .clean_start(true) // if false the broker retains previous subscriptions
                        .properties({{mqtt::property::SESSION_EXPIRY_INTERVAL, 604800}})
                        .finalize();

    MqttClient bt_mqtt_client(serverURI, clientId, connOpts, repetitions);
    NodeMessageDistributor node_message_distributor(bt_mqtt_client);
    BT::BehaviorTreeFactory factory;

    // Register the nodes with the behavior tree and the mqtt client
    MqttActionNode::registerNodeType<MoveShuttleToPosition>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "MoveShuttleToPosition",
        UNS_TOPIC + "/Planar/Xbot1/CMD/XYMotion",
        UNS_TOPIC + "/Planar/Xbot1/DATA/State",
        "../../schemas/moveToPosition.schema.json",
        "../../schemas/state.schema.json");

    MqttActionNode::registerNodeType<OmronArclRequest>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "OmronArclRequest",
        UNS_TOPIC + "/Omron/CMD/ARCL",
        UNS_TOPIC + "/Omron/DATA/State",
        "../../schemas/amrArclRequest.schema.json",
        "../../schemas/amrArclUpdate.schema.json");

    MqttConditionNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "GenericConditionNode",
        UNS_TOPIC + "/Filling/DATA/Weight",
        "../../schemas/weigh.schema.json");

    auto tree = factory.createTreeFromFile("../src/bt/Description/tree.xml");
    BT::Groot2Publisher publisher(tree, 1667);

    while (true)
    {
        std::cout << "====== Starting behavior tree... ======" << std::endl;
        auto status = tree.tickOnce();
        while (status == BT::NodeStatus::RUNNING)
        {
            // The BT is event based but lets tick every few seconds any way
            auto status = tree.tickWhileRunning(std::chrono::milliseconds(2000));
        }
        std::cout << "Behavior tree execution completed with status: "
                  << (status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "FAILURE") << std::endl;

        // For now the behaviour tree is being looped
        std::cout << "====== Restarting behavior tree... ======" << std::endl;
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    return 0;
}
#include <chrono>
#include <functional>
#include <iostream>
#include <fstream>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/xml_parsing.h>

#include "common_constants.h"

#include "mqtt/proxy.h"
#include "bt/mqtt_action_node.h"
#include "mqtt/subscription_manager.h"
#include "mqtt/utils.h"
#include "mqtt/mqtt_node_base_registration.h"
#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "bt/CustomNodes/pmc_condition_node.h"
#include "bt/CustomNodes/omron_arcl_request_node.h"
int main(int argc, char *argv[])
{
    std::string serverURI = (argc > 1) ? std::string{argv[1]} : BROKER_URI;
    std::string clientId = CLIENT_ID;
    int repetitions = 5;

    // MQTT initialization
    auto connOpts = mqtt::connect_options_builder::v5()
                        .clean_start(false)
                        .properties({{mqtt::property::SESSION_EXPIRY_INTERVAL, 604800}})
                        .finalize();

    Proxy bt_proxy(serverURI, clientId, connOpts, repetitions);
    SubscriptionManager subscription_manager(bt_proxy);
    BT::BehaviorTreeFactory factory;

    // Register the nodes with the behavior tree and the mqtt client
    MqttNodeBase::registerNodeType<MoveShuttleToPosition>(
        factory,
        subscription_manager,
        "MoveShuttleToPosition",
        UNS_TOPIC + "/Planar",
        "../schemas/moveResponse.schema.json",
        bt_proxy);

    MqttNodeBase::registerNodeType<OmronArclRequest>(
        factory,
        subscription_manager,
        "OmronArclRequest",
        UNS_TOPIC + "/Omron",
        "../schemas/amrArclRequest.schema.json",
        bt_proxy);

    MqttNodeBase::registerNodeType<PMCConditionNode>(
        factory,
        subscription_manager,
        "PMCConditionNode",
        UNS_TOPIC + "/Planar",
        "../schemas/weigh.schema.json",
        bt_proxy);

    auto tree = factory.createTreeFromFile("../src/bt/Description/tree.xml");
    BT::Groot2Publisher publisher(tree);

    while (true)
    {
        std::cout << "====== Starting behavior tree... ======" << std::endl;
        auto status = tree.tickOnce();
        while (status == BT::NodeStatus::RUNNING)
        {
            // Use tickWhileRunning to allow the tree to tick continuously
            auto status = tree.tickWhileRunning(std::chrono::milliseconds(15000));
        }
        // When tree completes (SUCCESS or FAILURE), print the result
        std::cout << "Behavior tree execution completed with status: "
                  << (status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "FAILURE") << std::endl;

        std::cout << "====== Restarting behavior tree... ======" << std::endl;
        // Optional: Add a delay between tree executions
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    return 0;
}
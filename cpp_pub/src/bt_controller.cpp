#include <iostream>
#include <chrono>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include "behaviortree_cpp/xml_parsing.h"
#include <functional>
#include "mqtt/proxy.h"
#include "bt/mqtt_action_node.h"
#include "bt/tree_tick_requester.h"
#include "bt/CustomNodes/move_shuttle_to_position.h"
#include "mqtt/subscription_manager.h"
#include "mqtt/utils.h"
#include "common_constants.h"
#include <fstream>

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

    // Create Subscription Manager and gnive pointer to all nodes
    // TODO make this to be handled within registerNodeType or combine the node registration with the bt factory
    SubscriptionManager subscription_manager(bt_proxy);
    MqttActionNode::setSubscriptionManager(&subscription_manager);
    subscription_manager.registerNodeType<MoveShuttleToPosition>(
        UNS_TOPIC,
        "../schemas/moveResponse.schema.json");

    // BT initiliazation
    BT::BehaviorTreeFactory factory;
    factory.registerNodeType<MoveShuttleToPosition>("MoveShuttleToPosition", std::ref(bt_proxy));
    auto tree = factory.createTreeFromFile("../src/bt_tree.xml");
    BT::Groot2Publisher publisher(tree);

    while (true)
    {
        auto status = tree.tickOnce();
        while (status == BT::NodeStatus::RUNNING)
        {
            // Mostly event driven, but ticks at interval additionally.
            // For pure eventdriven use overload of waitForTickRequest
            TreeTickRequester::waitForTickRequest(std::chrono::milliseconds(5000));
            status = tree.tickOnce();
        }

        // When tree completes (SUCCESS or FAILURE), print the result
        std::cout << "Behavior tree execution completed with status: "
                  << (status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "FAILURE") << std::endl;

        std::cout << "====== Restarting behavior tree... ======" << std::endl;
        // Optional: Add a delay between tree executions
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    // To generate the model XML for the Groot2
    // std::string xml_models = BT::writeTreeNodesModelXML(factory);
    // auto saveXmlToFile = [](const std::string &xml_content, const std::string &filename)
    // {
    //     std::ofstream file(filename);
    //     if (file.is_open())
    //     {
    //         file << xml_content;
    //         file.close();
    //         std::cout << "Successfully saved XML models to " << filename << std::endl;
    //         return true;
    //     }
    //     else
    //     {
    //         std::cerr << "Failed to open file for writing: " << filename << std::endl;
    //         return false;
    //     }
    // };
    // saveXmlToFile(xml_models, "../models/tree_nodes_model.xml");

    return 0;
}
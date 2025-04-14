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
#include "bt/CustomNodes/generic_action_node.h"
#include "bt/CustomNodes/omron_arcl_request_node.h"

const std::string OUTPUT_FILE("../src/bt/Description/tree_nodes_model.xml");

/**
 * Saves a string to a file
 */
bool saveXmlToFile(const std::string &xml_content, const std::string &filename)
{
    std::ofstream file(filename);
    if (file.is_open())
    {
        file << xml_content;
        file.close();
        std::cout << "Successfully saved XML models to " << filename << std::endl;
        return true;
    }
    else
    {
        std::cerr << "Failed to open file for writing: " << filename << std::endl;
        return false;
    }
}

int main(int argc, char *argv[])
{
    bool generate_xml_models = false;
    std::string serverURI = BROKER_URI;
    std::string clientId = CLIENT_ID;
    int repetitions = 5;

    // Parse command line arguments
    for (int i = 1; i < argc; i++)
    {
        std::string arg = argv[i];
        if (arg == "--generate-models" || arg == "-g")
        {
            generate_xml_models = true;
        }
        else if (i == 1 && arg.find("--") == std::string::npos)
        {
            // Maintain backward compatibility for server URI as first argument
            serverURI = arg;
        }
    }

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
        "MoveShuttle",
        UNS_TOPIC + "/Planar/+/CMD/XYMotion",
        UNS_TOPIC + "/Planar/+/DATA/State",
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

    MqttActionNode::registerNodeType<GenericActionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Dispensing",
        UNS_TOPIC + "/Filling/CMD/Dispense",
        UNS_TOPIC + "/Filling/DATA/State",
        "../../schemas/command.schema.json",
        "../../schemas/state.schema.json");

    MqttActionNode::registerNodeType<GenericActionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "Stoppering",
        UNS_TOPIC + "/Stoppering/CMD/Stopper",
        UNS_TOPIC + "/Stoppering/DATA/State",
        "../../schemas/command.schema.json",
        "../../schemas/state.schema.json");

    MqttConditionNode::registerNodeType<GenericConditionNode>(
        factory,
        node_message_distributor,
        bt_mqtt_client,
        "GenericConditionNode",
        UNS_TOPIC + "/Filling/DATA/Weight",
        "../../schemas/weight.schema.json");

    // Check if we should generate XML models instead of running the tree
    if (generate_xml_models)
    {
        // Generate the XML models
        std::string xml_models = BT::writeTreeNodesModelXML(factory);

        // Save the XML models to a file
        if (saveXmlToFile(xml_models, OUTPUT_FILE))
        {
            std::cout << "XML models generation completed successfully!" << std::endl;
            return 0;
        }
        else
        {
            std::cerr << "Failed to save XML models!" << std::endl;
            return 1;
        }
    }
    else
    {
        factory.registerBehaviorTreeFromFile("../src/bt/Description/tree.xml");
        auto tree = factory.createTree("MainTree");
        BT::Groot2Publisher publisher(tree, 1667);

        while (true)
        {
            std::cout << "====== Starting behavior tree... ======" << std::endl;
            auto status = tree.tickOnce();
            while (status == BT::NodeStatus::RUNNING)
            {
                // The BT is event based so after mqtt messages it traverses immediately but lets tick every few ms any way
                auto status = tree.tickWhileRunning(std::chrono::milliseconds(100));
            }
            std::cout << "Behavior tree execution completed with status: "
                      << (status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "FAILURE") << std::endl;

            // For now the behaviour tree is being looped
            std::cout << "====== Restarting behavior tree... ======" << std::endl;
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }
    return 0;
}
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/xml_parsing.h>

#include "mqtt/mqtt_client.h"
#include "bt/mqtt_action_node.h"
#include "mqtt/node_message_distributor.h"
#include "utils.h"
#include "bt/register_all_nodes.h"
#include <csignal>
#include <atomic>
#include <chrono> // Required for std::chrono::milliseconds

// Global flag to signal shutdown
std::atomic<bool> g_shutdown_flag{false};

// Signal handler function
void signalHandler(int signum)
{
    std::cout << "Interrupt signal (" << signum << ") received.\n";
    g_shutdown_flag = true;
}

int main(int argc, char *argv[])
{
    // Default parameter values
    std::string configFile = "../config/controller_config.yaml";
    std::string serverURI = "192.168.0.140:1883";
    std::string clientId = "bt";
    std::string unsTopicPrefix = "NN/nybrovej/InnoLab";
    std::string bt_description_path = "../config/bt_description/tree.xml";
    std::string bt_nodes_path("../config/bt_description/tree_nodes_model.xml");
    int groot2_port = 1667;
    bool generate_xml_models = false;

    bt_utils::loadConfigFromYaml(configFile, generate_xml_models, serverURI, clientId, unsTopicPrefix, groot2_port,
                                 bt_description_path, bt_nodes_path);
    // Parse command line arguments
    for (int i = 1; i < argc; i++)
    {
        std::string arg = argv[i];
        if (arg == "-g")
        {
            generate_xml_models = true;
        }
    }
    auto connOpts = mqtt::connect_options_builder::v5()
                        .clean_start(true)
                        .properties({{mqtt::property::SESSION_EXPIRY_INTERVAL, 604800}})
                        .finalize();

    int repetitions = 5;
    MqttClient bt_mqtt_client(serverURI, clientId, connOpts, repetitions);
    NodeMessageDistributor node_message_distributor(bt_mqtt_client);
    BT::BehaviorTreeFactory factory;

    registerAllNodes(factory, node_message_distributor, bt_mqtt_client, unsTopicPrefix);
    std::signal(SIGINT, signalHandler);
    if (generate_xml_models)
    {
        std::string xml_models = BT::writeTreeNodesModelXML(factory);
        return bt_utils::saveXmlToFile(xml_models, bt_nodes_path);
    }
    else
    {
        factory.registerBehaviorTreeFromFile(bt_description_path);
        BT::Tree tree = factory.createTree("MainTree");

        node_message_distributor.subscribeToActiveNodes(tree);

        BT::Groot2Publisher publisher(tree, groot2_port);

        std::cout << "====== Starting behavior tree... Press Ctrl+C to exit. ======" << std::endl;
        BT::NodeStatus status = tree.tickOnce(); // Initial tick

        // Loop while the tree is running AND no shutdown signal
        while (status == BT::NodeStatus::RUNNING && !g_shutdown_flag.load())
        {
            status = tree.tickOnce();
            tree.sleep(std::chrono::milliseconds(100));
            if (g_shutdown_flag.load())
            {
                std::cout << "Tree halted with Crtl+C" << std::endl;
                break;
            }
        }

        std::cout << "Behavior tree execution completed with status: "
                  << (status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "FAILURE") << std::endl;
    }
    return 0;
}
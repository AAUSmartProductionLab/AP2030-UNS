#include <chrono>
#include <functional>
#include <iostream>
#include <fstream>
#include <filesystem>
#include <yaml-cpp/yaml.h>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/xml_parsing.h>

#include "mqtt/mqtt_client.h"
#include "bt/mqtt_action_node.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/utils.h"
#include "bt/register_all_nodes.h"

const std::string OUTPUT_FILE("../src/bt/Description/tree_nodes_model.xml");

/**
 * Saves a string to a file
 */
int saveXmlToFile(const std::string &xml_content, const std::string &filename)
{
    std::filesystem::path abs_path = std::filesystem::absolute(filename);
    std::cout << "Attempting to save to absolute path: " << abs_path << std::endl;

    std::ofstream file(filename);
    if (file.is_open())
    {
        file << xml_content;
        file.close();
        std::cout << "Successfully saved XML models to " << filename << std::endl;
        return 0;
    }
    else
    {
        std::cerr << "Failed to open file for writing: " << filename << std::endl;
        return 1;
    }
}
bool loadConfigFromYaml(const std::string &filename,
                        bool &generate_xml_models,
                        std::string &serverURI,
                        std::string &clientId,
                        std::string &unsTopicPrefix,
                        int &groot2_port,
                        std::string &bt_description_path)
{
    try
    {
        if (!std::filesystem::exists(filename))
        {
            std::cerr << "Config file not found: " << filename << std::endl;
            return false;
        }

        YAML::Node config = YAML::LoadFile(filename);

        if (config["broker_uri"])
        {
            serverURI = config["broker_uri"].as<std::string>();
        }
        if (config["client_id"])
        {
            clientId = config["client_id"].as<std::string>();
        }
        if (config["uns_topic"])
        {
            unsTopicPrefix = config["uns_topic"].as<std::string>();
        }
        if (config["generate_xml_models"])
        {
            generate_xml_models = config["generate_xml_models"].as<bool>();
        }
        if (config["groot2_port"])
        {
            groot2_port = config["groot2_port"].as<int>();
        }
        if (config["bt_description_path"])
        {
            bt_description_path = config["bt_description_path"].as<std::string>();
        }
        std::cout << "Configuration loaded from: " << filename << std::endl;
        return true;
    }
    catch (const YAML::Exception &e)
    {
        std::cerr << "Error parsing YAML config: " << e.what() << std::endl;
        return false;
    }
}
int main(int argc, char *argv[])
{
    std::string configFile = "../config/controller_config.yaml";
    std::string serverURI = "192.168.0.140:1883";
    std::string clientId = "bt";
    std::string unsTopicPrefix = "NN/nybrovej/InnoLab";
    std::string bt_description_path = "../config/bt_description/tree.xml";
    int groot2_port = 1667;
    bool generate_xml_models = false;

    loadConfigFromYaml(configFile, generate_xml_models, serverURI, clientId, unsTopicPrefix, groot2_port,
                       bt_description_path);
    std::cout << " ----------------------------------------------------------------------" << std::endl;
    std::cout << "Using configuration:" << std::endl
              << "  Broker URI: " << serverURI << std::endl
              << "  Client ID: " << clientId << std::endl
              << "  UNS Topic: " << unsTopicPrefix << std::endl
              << "  Generate XML Models: " << (generate_xml_models ? "Yes" : "No") << std::endl
              << "  Groot2 port: " << groot2_port << std::endl
              << "  BT Description Path: " << bt_description_path << std::endl
              << " ----------------------------------------------------------------------" << std::endl;

    auto connOpts = mqtt::connect_options_builder::v5()
                        .clean_start(true) // if false the broker retains previous subscriptions
                        .properties({{mqtt::property::SESSION_EXPIRY_INTERVAL, 604800}})
                        .finalize();

    int repetitions = 5;
    MqttClient bt_mqtt_client(serverURI, clientId, connOpts, repetitions);
    NodeMessageDistributor node_message_distributor(bt_mqtt_client);
    BT::BehaviorTreeFactory factory;

    // Register the nodes with the behavior tree and the mqtt client
    registerAllNodes(factory, node_message_distributor, bt_mqtt_client, unsTopicPrefix);

    if (generate_xml_models)
    {
        std::string xml_models = BT::writeTreeNodesModelXML(factory);
        return saveXmlToFile(xml_models, OUTPUT_FILE);
    }
    else
    {
        factory.registerBehaviorTreeFromFile(bt_description_path);
        auto tree = factory.createTree("MainTree");
        BT::Groot2Publisher publisher(tree, groot2_port);

        while (true)
        {
            std::cout << "====== Starting behavior tree... ======" << std::endl;
            auto status = tree.tickOnce();
            while (status == BT::NodeStatus::RUNNING)
            {
                // The BT is event based so after mqtt messages arrive it traverses immediately but lets tick every few ms any way
                status = tree.tickWhileRunning(std::chrono::milliseconds(100));
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
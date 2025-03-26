#include <iostream>
#include <functional>
#include <fstream>
#include <behaviortree_cpp/bt_factory.h>
#include "behaviortree_cpp/xml_parsing.h"
#include "mqtt/proxy.h"
#include "bt/mqtt_action_node.h"
#include "bt/CustomNodes/move_shuttle_to_position.h"

// Constants
const std::string BROKER_URI("192.168.0.104:1883");
const std::string CLIENT_ID("model_generator");
const std::string OUTPUT_FILE("../models/tree_nodes_model.xml");

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

int main()
{
    // Create a dummy MQTT proxy for node initialization
    auto connOpts = mqtt::connect_options_builder::v5()
                        .clean_start(false)
                        .properties({{mqtt::property::SESSION_EXPIRY_INTERVAL, 604800}})
                        .finalize();

    Proxy dummy_proxy(BROKER_URI, CLIENT_ID, connOpts, 1);

    // Initialize the behavior tree factory
    BT::BehaviorTreeFactory factory;

    // Register all custom nodes
    factory.registerNodeType<MoveShuttleToPosition>("MoveShuttleToPosition", std::ref(dummy_proxy));

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
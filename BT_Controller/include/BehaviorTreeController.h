#pragma once

#include <string>
#include <atomic>
#include <memory>
#include <optional>

#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/basic_types.h>

#include "utils.h"

// Forward declarations for types used as pointers or in unique_ptr
class MqttClient;
class NodeMessageDistributor;
namespace BT
{
    class Groot2Publisher;
}

class BehaviorTreeController
{
public:
    struct BtControllerParameters
    {
        std::string configFile = "../config/controller_config.yaml";
        std::string serverURI = "192.168.0.104:1883";
        std::string clientId = "bt";
        std::string unsTopicPrefix = "NN/nybrovej/InnoLab";
        std::string bt_description_path = "../config/bt_description/tree.xml";
        std::string bt_nodes_path = "../config/bt_description/tree_nodes_model.xml";
        int groot2_port = 1667;
        bool generate_xml_models = false;

        // MQTT Control Topics
        std::string start_topic;
        std::string stop_topic;
        std::string halt_topic;

        // MQTT State Publication Config
        mqtt_utils::Topic state_publication_config;
    };

    BehaviorTreeController(int argc, char *argv[]);
    ~BehaviorTreeController();

    void requestShutdown();
    void onSigint();
    int run();

private:
    BtControllerParameters app_params_;
    std::unique_ptr<MqttClient> mqtt_client_;
    std::unique_ptr<NodeMessageDistributor> node_message_distributor_;
    BT::BehaviorTreeFactory bt_factory_;
    BT::Tree bt_tree_;
    std::unique_ptr<BT::Groot2Publisher> bt_publisher_;

    std::atomic<bool> mqtt_start_bt_flag_;
    std::atomic<bool> mqtt_halt_bt_flag_;
    std::atomic<bool> shutdown_flag_;
    std::atomic<bool> sigint_received_;

    PackML::State current_packml_state_;
    BT::NodeStatus current_bt_tick_status_;

    void loadAppConfiguration(int argc, char *argv[]);
    void initializeMqttControlInterface();
    bool handleGenerateXmlModelsOption();
    void setStateAndPublish(PackML::State new_packml_state, std::optional<BT::NodeStatus> new_bt_tick_status_opt = std::nullopt);
    void publishCurrentState();
    void processBehaviorTreeStart();
    void manageRunningBehaviorTree();
};

// Global instance pointer, defined in the .cpp file
extern BehaviorTreeController *g_controller_instance;

// Signal handler function declaration, defined in the .cpp file
void signalHandler(int signum);
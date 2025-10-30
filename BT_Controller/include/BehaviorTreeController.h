#pragma once

#include <string>
#include <atomic>
#include <memory>
#include <optional>
#include "mqtt/mqtt_client.h"
#include "mqtt/node_message_distributor.h"
#include "aas/aas_client.h"

#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/basic_types.h>
#include "utils.h"

class BehaviorTreeController;
extern BehaviorTreeController *g_controller_instance;
void signalHandler(int signum);

namespace BT
{
    class Groot2Publisher;
}

struct BtControllerParameters
{
    std::string configFile = "../config/controller_config.yaml";
    bool generate_xml_models = false;
    std::string serverURI;
    std::string clientId;
    std::string unsTopicPrefix;
    std::string aasServerUrl;
    int groot2_port;
    std::string bt_description_path;
    std::string bt_nodes_path;
    std::string start_topic;
    std::string stop_topic;
    std::string halt_topic;
    std::string config_topic;
    mqtt_utils::Topic state_publication_config;
};

class BehaviorTreeController
{
public:
    BehaviorTreeController(int argc, char *argv[]);
    ~BehaviorTreeController();

    int run();
    void requestShutdown();
    void onSigint();

private:
    BtControllerParameters app_params_;
    std::unique_ptr<MqttClient> mqtt_client_;
    std::unique_ptr<NodeMessageDistributor> node_message_distributor_;
    std::function<void(const std::string &, const nlohmann::json &, mqtt::properties)> main_mqtt_message_handler_;

    std::unique_ptr<AASClient> aas_client_;
    BT::BehaviorTreeFactory bt_factory_;
    BT::Tree bt_tree_;
    std::unique_ptr<BT::Groot2Publisher> bt_publisher_;

    std::atomic<bool> mqtt_start_bt_flag_;
    std::atomic<bool> mqtt_halt_bt_flag_;
    std::atomic<bool> shutdown_flag_;
    std::atomic<bool> sigint_received_;
    std::atomic<bool> station_config_received_;
    std::atomic<bool> nodes_registered_;

    PackML::State current_packml_state_;
    BT::NodeStatus current_bt_tick_status_;

    nlohmann::json station_config_;
    std::mutex station_config_mutex_;
    mqtt_utils::Topic station_config_topic_;

    void setupMainMqttMessageHandler();

    void loadAppConfiguration(int argc, char *argv[]);
    void initializeMqttControlInterface();
    bool handleGenerateXmlModelsOption();

    void setStateAndPublish(PackML::State new_packml_state, std::optional<BT::NodeStatus> new_bt_tick_status_opt = std::nullopt);
    void publishCurrentState();

    void processBehaviorTreeStart();
    void manageRunningBehaviorTree();

    // New methods for station configuration management
    void handleStationConfigUpdate(const nlohmann::json &new_config);
    bool registerNodesWithStationConfig();
    void unregisterAllNodes();
};
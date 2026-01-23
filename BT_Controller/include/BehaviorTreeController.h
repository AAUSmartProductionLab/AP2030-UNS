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
    std::string aasRegistryUrl;
    int groot2_port;
    std::string bt_description_path;
    std::string bt_nodes_path;
    std::string start_topic;
    std::string stop_topic;
    std::string suspend_topic;
    std::string unsuspend_topic;
    std::string reset_topic;
    
    // Response topics for command acknowledgments
    std::string start_response_topic;
    std::string stop_response_topic;
    std::string suspend_response_topic;
    std::string unsuspend_response_topic;
    std::string reset_response_topic;
    
    mqtt_utils::Topic state_publication_config;

    // Registration Service Configuration
    std::string registration_config_path;      // Path to orchestrator's AAS description YAML
    std::string registration_topic_pattern;    // MQTT topic pattern for registration
    std::string registration_topic;            // Resolved registration topic
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
    std::unique_ptr<BT::BehaviorTreeFactory> bt_factory_;
    BT::Tree bt_tree_;
    std::unique_ptr<BT::Groot2Publisher> bt_publisher_;

    std::atomic<bool> mqtt_start_bt_flag_;
    std::atomic<bool> mqtt_suspend_bt_flag_;
    std::atomic<bool> mqtt_unsuspend_bt_flag_;
    std::atomic<bool> mqtt_reset_bt_flag_;
    std::atomic<bool> shutdown_flag_;
    std::atomic<bool> sigint_received_;
    std::atomic<bool> nodes_registered_;

    // Process AAS ID received from Start command
    std::string process_aas_id_;
    std::mutex process_aas_id_mutex_;

    // Pending command UUIDs for responses
    std::string pending_start_uuid_;
    std::string pending_stop_uuid_;
    std::string pending_suspend_uuid_;
    std::string pending_unsuspend_uuid_;
    std::string pending_reset_uuid_;
    std::mutex pending_command_mutex_;

    PackML::State current_packml_state_;
    BT::NodeStatus current_bt_tick_status_;

    // Equipment mapping: asset name -> AAS ID/URL
    std::map<std::string, std::string> equipment_aas_mapping_;
    std::mutex equipment_mapping_mutex_;

    void setupMainMqttMessageHandler();

    void loadAppConfiguration(int argc, char *argv[]);
    void initializeMqttControlInterface();
    bool handleGenerateXmlModelsOption();

    void setStateAndPublish(PackML::State new_packml_state, std::optional<BT::NodeStatus> new_bt_tick_status_opt = std::nullopt);
    void publishCurrentState();
    void publishCommandResponse(const std::string& response_topic, const std::string& uuid, bool success);

    void processBehaviorTreeStart();
    void processStartingState();
    void processBehaviorTreeUnsuspend();
    void processResettingState();
    void manageRunningBehaviorTree();

    // Methods for node registration
    bool registerNodesWithAASConfig();
    void unregisterAllNodes();

    // Methods for AAS structure fetching from process AAS
    bool fetchAndBuildEquipmentMapping(BT::Blackboard::Ptr blackboard = nullptr);
    void populateBlackboard(BT::Blackboard::Ptr blackboard);

    // Methods for AAS registration
    bool publishConfigToRegistrationService();
};
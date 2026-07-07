#pragma once

#include <string>
#include <atomic>
#include <memory>
#include <optional>
#include <chrono>
#include <unordered_map>

#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/basic_types.h>
#include "backends/backend_registry.h"
#include "utils.h"

class ControllerRestApi;

class BehaviorTreeController;
extern BehaviorTreeController *g_controller_instance;
void signalHandler(int signum);

namespace BT
{
    class Groot2Publisher;
    class TreeObserver;
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
    std::string bt_description_base_url = "https://aausmartproductionlab.github.io/AP2030-UNS/BTDescriptions/";
    std::string bt_local_descriptions_dir; // override via BT_LOCAL_DESCRIPTIONS_DIR env var
    std::string bt_nodes_path;

    // Registration Service Configuration
    std::string registration_config_path;   // Path to orchestrator's AAS description YAML
    std::string registration_topic_pattern; // MQTT topic pattern for registration
    std::string registration_topic;         // Resolved registration topic

    // Runtime metrics
    std::string metrics_dir = "/data/run_metrics";
    std::string metrics_topic_prefix = "NN/Nybrovej/InnoLab/Stats";

    // Interface mode: AAS = AAS, Native = from AID submodel
    InterfaceMode interface_mode = InterfaceMode::AAS;

    // REST API port (0 = disabled)
    int rest_api_port = 8090;

    // KG backend configuration (read from env)
    std::string kg_query_url;
    std::string kg_update_url;
    std::string kg_graph;
};

class BehaviorTreeController
{
public:
    BehaviorTreeController(int argc, char *argv[]);
    ~BehaviorTreeController();

    int run();

    // ── PackML trigger methods (called by REST API / signal handler)
    void Abort();
    void Clear();
    void Stop();
    void Reset();
    void Start(const std::string &process_id);
    void Hold();
    void Unhold();
    void Suspend();
    void Unsuspend();
    bool isRunning() const;

private:
    BtControllerParameters app_params_;
    std::unique_ptr<BT::BehaviorTreeFactory> bt_factory_;

    // BT infrastructure owned by controller.
    std::unique_ptr<ControllerRestApi> rest_api_;
    BT::Tree bt_tree_;
    std::unique_ptr<BT::Groot2Publisher> bt_publisher_;
    std::unique_ptr<BT::TreeObserver> bt_observer_;

    std::atomic<bool> nodes_registered_;

    // Process AAS ID received from Start command
    std::string process_aas_id_;
    std::mutex process_aas_id_mutex_;

    // Runtime metrics correlation + timing
    std::string current_run_id_;
    std::mutex metrics_mutex_;
    std::chrono::steady_clock::time_point execute_started_at_;
    std::atomic<bool> execute_timer_active_{false};
    std::unordered_map<uint16_t, std::string> node_category_by_uid_;

    PackML::State current_packml_state_;
    BT::NodeStatus current_bt_tick_status_;

    void loadAppConfiguration(int argc, char *argv[]);
    bool handleGenerateXmlModelsOption();

    // ── PackML command flags (set by REST API / SIGINT) ─────────
    std::atomic<bool> start_command_;
    std::atomic<bool> reset_command_;
    std::atomic<bool> stop_command_;
    std::atomic<bool> abort_command_;
    std::atomic<bool> clear_command_;
    std::atomic<bool> hold_command_;
    std::atomic<bool> unhold_command_;
    std::atomic<bool> suspend_command_;
    std::atomic<bool> unsuspend_command_;

    // ── PackML state methods ────────────────────────────────────
    void Starting();     // IDLE → STARTING → EXECUTE
    void Execute();      // tick loop, → COMPLETE / STOPPED / HELD / SUSPENDED
    void Completing();   // publish metrics, → COMPLETE
    void Complete();     // terminal, waits for Reset
    void Resetting();    // cleanup, → IDLE
    void Stopping();     // halt tree, → STOPPED
    void Aborting();     // halt tree (SIGINT), → ABORTED
    void Clearing();     // cleanup after abort, → STOPPED
    void Holding();      // halt tree, → HELD
    void Unholding();    // (tree already halted), → EXECUTE
    void Suspending();   // halt tree, → SUSPENDED
    void Unsuspending(); // (tree already halted), → EXECUTE

    // ── BT initialization pipeline helpers ──────────────────────
    bool setupEquipmentAndNodes(const std::string &process_id);
    bool createBehaviorTree(const std::string &process_id);
    bool validateAndFinalizeTree();

    // Methods for node registration
    bool registerNodesWithAASConfig();
    void unregisterAllNodes();

    // Pre-fetch asset interfaces (for fast node initialization)
    bool prefetchAssetInterfaces();

    // Methods for AAS registration
    bool publishConfigToRegistrationService();

    // Runtime metrics helpers
    void resetRunMetricsState();
    void initializeRunMetrics(const std::string &run_id);
    void publishRunMetrics(BT::NodeStatus final_status);
};
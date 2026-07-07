/// Core controller: construction, configuration, entry point.
/// PackML state machine → BehaviorTreeController_PackML.cpp
/// Metrics + registration   → BehaviorTreeController_metrics.cpp
/// Node lifecycle           → BehaviorTreeController_nodes.cpp
/// Equipment mapping        → kept in _startup (startup infrastructure)

#include "BehaviorTreeController.h"

#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/loggers/bt_observer.h>
#include <behaviortree_cpp/xml_parsing.h>

#include "backends/controller_rest_api.h"
#include "bt/register_all_nodes.h"
#include "bt/execution_refs.h"
#include "backends/backend_registry.h"
#include "utils.h"

#include <csignal>
#include <iostream>

BehaviorTreeController *g_controller_instance = nullptr;

// ── Construction ──────────────────────────────────────────────────────

BehaviorTreeController::BehaviorTreeController(int argc, char *argv[])
    : start_command_{false},
      reset_command_{false},
      stop_command_{false},
      abort_command_{false},
      clear_command_{false},
      hold_command_{false},
      unhold_command_{false},
      suspend_command_{false},
      unsuspend_command_{false},
      nodes_registered_{false},
      current_packml_state_{PackML::State::STOPPED},
      current_bt_tick_status_{BT::NodeStatus::IDLE}
{
    g_controller_instance = this;
    loadAppConfiguration(argc, argv);

    // Hand the config to the registry — it creates all backend infrastructure
    // (MqttInfra, AAS bridge, KG client) internally.
    BackendRegistry::instance().configure(app_params_);

    // REST API.
    {
        if (app_params_.rest_api_port > 0)
        {
            rest_api_ = std::make_unique<ControllerRestApi>(app_params_.rest_api_port, this);
        }
    }

    bt_factory_ = std::make_unique<BT::BehaviorTreeFactory>();

    std::signal(SIGINT, signalHandler);
}

BehaviorTreeController::~BehaviorTreeController()
{
    if (bt_tree_.rootNode() && bt_tree_.rootNode()->status() == BT::NodeStatus::RUNNING)
        bt_tree_.haltTree();

    g_controller_instance = nullptr;
}

// ── Configuration ─────────────────────────────────────────────────────

void BehaviorTreeController::loadAppConfiguration(int argc, char *argv[])
{
    bt_utils::loadConfigFromYaml(
        app_params_.configFile, app_params_.generate_xml_models,
        app_params_.serverURI, app_params_.clientId, app_params_.unsTopicPrefix,
        app_params_.aasServerUrl, app_params_.aasRegistryUrl,
        app_params_.groot2_port, app_params_.bt_description_path,
        app_params_.bt_nodes_path, app_params_.registration_config_path,
        app_params_.registration_topic_pattern);

    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "-g")
        {
            app_params_.generate_xml_models = true;
            break;
        }

    if (!app_params_.registration_topic_pattern.empty())
    {
        app_params_.registration_topic = app_params_.registration_topic_pattern;
        size_t pos = app_params_.registration_topic.find("{client_id}");
        if (pos != std::string::npos)
            app_params_.registration_topic.replace(pos, 11, app_params_.clientId);
        std::cout << "  Registration Topic: " << app_params_.registration_topic << std::endl;
    }

    app_params_.metrics_dir = envOrDefault("BT_METRICS_DIR", app_params_.metrics_dir);
    app_params_.metrics_topic_prefix = envOrDefault("METRICS_TOPIC_PREFIX", app_params_.metrics_topic_prefix);
    std::cout << "  Metrics Dir: " << app_params_.metrics_dir << std::endl
              << "  Metrics Topic Prefix: " << app_params_.metrics_topic_prefix << std::endl;

    app_params_.rest_api_port = std::stoi(envOrDefault("BT_REST_API_PORT", std::to_string(app_params_.rest_api_port)));

    app_params_.kg_query_url = envOrDefault("FUSEKI_QUERY_URL", "http://kg-fuseki:3030/kg/sparql");
    app_params_.kg_update_url = envOrDefault("FUSEKI_UPDATE_URL", "");
    app_params_.kg_graph = envOrDefault("KG_ABOX_GRAPH", "urn:kg:abox");

    app_params_.bt_local_descriptions_dir = envOrDefault("BT_LOCAL_DESCRIPTIONS_DIR", "");
}

bool BehaviorTreeController::handleGenerateXmlModelsOption()
{
    if (!app_params_.generate_xml_models)
        return false;
    std::cout << "Generating XML models requires station configuration..." << std::endl;
    if (!nodes_registered_)
    {
        registerNodesWithAASConfig();
    }
    std::string xml_models = BT::writeTreeNodesModelXML(*bt_factory_);
    bt_utils::saveXmlToFile(xml_models, app_params_.bt_nodes_path);
    std::cout << "XML models saved to: " << app_params_.bt_nodes_path << std::endl;
    return true;
}

// ── Entry point ───────────────────────────────────────────────────────

void signalHandler(int signum)
{
    if (g_controller_instance)
    {
        g_controller_instance->Abort();
    }
}

int main(int argc, char *argv[])
{
    std::cout << "Starting Behavior Tree Controller..." << std::endl;
    BehaviorTreeController controller(argc, argv);
    return controller.run();
}

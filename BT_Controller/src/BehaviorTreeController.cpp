#include "BehaviorTreeController.h"

#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/xml_parsing.h>

#include "mqtt/mqtt_client.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_sub_base.h"
#include "bt/register_all_nodes.h"
#include "utils.h"

#include <csignal>
#include <chrono>
#include <thread>
#include <iostream>
#include <algorithm>

BehaviorTreeController *g_controller_instance = nullptr;

BehaviorTreeController::BehaviorTreeController(int argc, char *argv[])
    : mqtt_start_bt_flag_{false},
      mqtt_halt_bt_flag_{false},
      shutdown_flag_{false},
      sigint_received_{false},
      station_config_received_{false},
      nodes_registered_{false},
      current_packml_state_{PackML::State::IDLE},
      current_bt_tick_status_{BT::NodeStatus::IDLE}
{
    g_controller_instance = this;
    loadAppConfiguration(argc, argv);

    auto connOpts = mqtt::connect_options_builder::v5()
                        .clean_start(true)
                        .properties({{mqtt::property::SESSION_EXPIRY_INTERVAL, 604800}})
                        .finalize();

    mqtt_client_ = std::make_unique<MqttClient>(app_params_.serverURI, app_params_.clientId, connOpts, 5);
    node_message_distributor_ = std::make_unique<NodeMessageDistributor>(*mqtt_client_);

    // Initialize AAS client
    aas_client_ = std::make_unique<AASClient>(app_params_.aasServerUrl);

    // Don't register nodes yet - wait for station config
    std::signal(SIGINT, signalHandler);
}

BehaviorTreeController::~BehaviorTreeController()
{
    if (bt_tree_.rootNode() && bt_tree_.rootNode()->status() == BT::NodeStatus::RUNNING)
    {
        bt_tree_.haltTree();
    }

    if (node_message_distributor_ && mqtt_client_)
    {
        std::vector<std::string> topics_to_unsubscribe = node_message_distributor_->getActiveTopicPatterns();
        for (const auto &topic : topics_to_unsubscribe)
        {
            try
            {
                mqtt_client_->unsubscribe_topic(topic);
            }
            catch (const std::exception &)
            {
                // Exception during unsubscribe in destructor is ignored
            }
        }
    }

    g_controller_instance = nullptr;
}

void BehaviorTreeController::requestShutdown()
{
    shutdown_flag_ = true;
}

void BehaviorTreeController::onSigint()
{
    shutdown_flag_ = true;
    sigint_received_ = true;
}

bool BehaviorTreeController::isStationConfigValid(const json &config)
{
    // Validate the station configuration structure
    if (!config.contains("Stations") || !config["Stations"].is_object())
    {
        std::cerr << "Invalid station config: missing 'Stations' object" << std::endl;
        return false;
    }

    // Additional validation can be added here
    const auto &stations = config["Stations"];
    if (stations.empty())
    {
        std::cerr << "Invalid station config: no stations defined" << std::endl;
        return false;
    }

    std::cout << "Station config validation passed. Found "
              << stations.size() << " stations." << std::endl;
    return true;
}

void BehaviorTreeController::handleStationConfigUpdate(const json &new_config)
{
    // Only allow configuration updates when in IDLE state
    if (current_packml_state_ != PackML::State::IDLE)
    {
        std::cout << "Station configuration update ignored. Controller must be in IDLE state. "
                  << "Current state: " << PackML::stateToString(current_packml_state_) << std::endl;
        return;
    }

    std::cout << "Received station configuration update..." << std::endl;

    // Validate the new configuration
    if (!isStationConfigValid(new_config))
    {
        std::cerr << "Invalid station configuration received. Update rejected." << std::endl;
        return;
    }

    {
        std::lock_guard<std::mutex> lock(station_config_mutex_);

        // Check if configuration actually changed
        if (station_config_received_ && station_config_ == new_config)
        {
            std::cout << "Station configuration unchanged. No update needed." << std::endl;
            return;
        }

        // Store the new configuration
        station_config_ = new_config;
        station_config_received_ = true;
    }

    std::cout << "New station configuration accepted:" << std::endl;
    std::cout << new_config.dump(2) << std::endl;

    // Unregister existing nodes if any
    if (nodes_registered_)
    {
        std::cout << "Unregistering existing nodes..." << std::endl;
        unregisterAllNodes();
    }

    // Register nodes with the new configuration
    std::cout << "Registering nodes with new station configuration..." << std::endl;
    if (registerNodesWithStationConfig())
    {
        std::cout << "Nodes successfully registered with new configuration." << std::endl;
        nodes_registered_ = true;
    }
    else
    {
        std::cerr << "Failed to register nodes with new station configuration!" << std::endl;
        nodes_registered_ = false;
    }
}

bool BehaviorTreeController::registerNodesWithStationConfig()
{
    try
    {
        json config_copy;
        {
            std::lock_guard<std::mutex> lock(station_config_mutex_);
            config_copy = station_config_;
        }

        // Clear the factory to remove old node registrations
        bt_factory_.clearRegisteredBehaviorTrees();

        // Register all nodes with the current station configuration
        registerAllNodes(bt_factory_, *node_message_distributor_, *mqtt_client_,
                         *aas_client_, config_copy);

        // Set the node message distributor for base classes
        MqttSubBase::setNodeMessageDistributor(node_message_distributor_.get());

        return true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception during node registration: " << e.what() << std::endl;
        return false;
    }
}

void BehaviorTreeController::unregisterAllNodes()
{
    // Clear all registered behavior trees and node types
    bt_factory_.clearRegisteredBehaviorTrees();

    // Reset node message distributor
    if (node_message_distributor_ && mqtt_client_)
    {
        std::vector<std::string> topics_to_unsubscribe =
            node_message_distributor_->getActiveTopicPatterns();

        for (const auto &topic : topics_to_unsubscribe)
        {
            try
            {
                mqtt_client_->unsubscribe_topic(topic);
            }
            catch (const std::exception &e)
            {
                std::cerr << "Exception during unsubscribe: " << e.what() << std::endl;
            }
        }
    }

    // Recreate node message distributor to clear all registrations
    node_message_distributor_ = std::make_unique<NodeMessageDistributor>(*mqtt_client_);

    nodes_registered_ = false;
    std::cout << "All nodes unregistered." << std::endl;
}

int BehaviorTreeController::run()
{
    if (handleGenerateXmlModelsOption())
    {
        return 0;
    }

    initializeMqttControlInterface();

    while (true)
    {
        if (shutdown_flag_.load() && !mqtt_start_bt_flag_.load())
        {
            if (current_packml_state_ != PackML::State::EXECUTE)
            {
                if (current_packml_state_ != PackML::State::STOPPED && current_packml_state_ != PackML::State::IDLE)
                {
                    setStateAndPublish(PackML::State::STOPPED);
                }
                if (current_packml_state_ == PackML::State::STOPPED)
                {
                    setStateAndPublish(PackML::State::IDLE);
                }
                if (current_packml_state_ == PackML::State::IDLE && shutdown_flag_.load())
                {
                    if (sigint_received_.load())
                    {
                        break;
                    }
                    else
                    {
                        shutdown_flag_ = false;
                    }
                }
            }
        }

        if (mqtt_start_bt_flag_.load())
        {
            if (!sigint_received_.load())
            {
                processBehaviorTreeStart();
            }
            mqtt_start_bt_flag_ = false;
        }

        if (current_packml_state_ == PackML::State::EXECUTE)
        {
            manageRunningBehaviorTree();
        }
        else
        {
            if (sigint_received_.load() && current_packml_state_ == PackML::State::IDLE && shutdown_flag_.load())
            {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
            else
            {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        }
    }
    return 0;
}

void BehaviorTreeController::loadAppConfiguration(int argc, char *argv[])
{
    bt_utils::loadConfigFromYaml(
        app_params_.configFile,
        app_params_.generate_xml_models,
        app_params_.serverURI,
        app_params_.clientId,
        app_params_.unsTopicPrefix,
        app_params_.aasServerUrl,
        app_params_.groot2_port,
        app_params_.bt_description_path,
        app_params_.bt_nodes_path);

    for (int i = 1; i < argc; ++i)
    {
        if (std::string(argv[i]) == "-g")
        {
            app_params_.generate_xml_models = true;
            break;
        }
    }

    app_params_.start_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/CMD/Start";
    app_params_.stop_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/CMD/Stop";
    app_params_.halt_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/CMD/Suspend";
    app_params_.config_topic = app_params_.unsTopicPrefix + "/Planar/Stations";

    std::string state_topic_str = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/DATA/State";
    std::string schema_path = "../../schemas/state.schema.json";
    app_params_.state_publication_config = mqtt_utils::Topic(state_topic_str, schema_path, 2, true);
    app_params_.state_publication_config.initValidator();
}

void BehaviorTreeController::initializeMqttControlInterface()
{
    if (!mqtt_client_)
    {
        std::cerr << "Error: mqtt_client_ is null in initializeMqttControlInterface." << std::endl;
        return;
    }

    auto main_mqtt_message_handler =
        [this](const std::string &topic, const json &payload, mqtt::properties props)
    {
        if (topic == this->app_params_.start_topic)
        {
            if (!this->sigint_received_.load())
            {
                // Only allow start if nodes are registered
                if (!this->nodes_registered_.load())
                {
                    std::cerr << "Cannot start: No station configuration received yet!" << std::endl;
                    std::cerr << "Please send station configuration to: "
                              << this->app_params_.config_topic << std::endl;
                    return;
                }
                this->shutdown_flag_ = false;
                this->mqtt_halt_bt_flag_ = false;
                this->mqtt_start_bt_flag_ = true;
            }
        }
        else if (topic == this->app_params_.stop_topic)
        {
            this->requestShutdown();
        }
        else if (topic == this->app_params_.halt_topic)
        {
            this->mqtt_halt_bt_flag_ = true;
        }
        else if (topic == this->app_params_.config_topic)
        {
            this->handleStationConfigUpdate(payload);
        }
        else
        {
            if (this->node_message_distributor_)
            {
                this->node_message_distributor_->handle_incoming_message(topic, payload, props);
            }
            else
            {
                std::cerr << "MQTT message for NMD, but NodeMessageDistributor is null. Topic: "
                          << topic << std::endl;
            }
        }
    };

    mqtt_client_->set_message_handler(main_mqtt_message_handler);

    mqtt_client_->subscribe_topic(app_params_.start_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.stop_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.halt_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.config_topic, 2);

    std::cout << "MQTT control interface initialized." << std::endl;
    std::cout << "Waiting for station configuration on topic: "
              << app_params_.config_topic << std::endl;

    publishCurrentState();
}

bool BehaviorTreeController::handleGenerateXmlModelsOption()
{
    if (app_params_.generate_xml_models)
    {
        // For XML generation, we need a dummy configuration
        std::cout << "Generating XML models requires station configuration..." << std::endl;

        if (!station_config_received_)
        {
            std::cerr << "Warning: No station configuration available for XML generation." << std::endl;
            std::cerr << "Using empty configuration." << std::endl;
            station_config_ = json::object();
            station_config_["Stations"] = json::object();
        }

        if (!nodes_registered_)
        {
            registerNodesWithStationConfig();
        }

        std::string xml_models = BT::writeTreeNodesModelXML(bt_factory_);
        bt_utils::saveXmlToFile(xml_models, app_params_.bt_nodes_path);
        std::cout << "XML models saved to: " << app_params_.bt_nodes_path << std::endl;
        return true;
    }
    return false;
}

void BehaviorTreeController::setStateAndPublish(PackML::State new_packml_state,
                                                std::optional<BT::NodeStatus> new_bt_tick_status_opt)
{
    bool state_changed = false;

    if (current_packml_state_ != new_packml_state)
    {
        current_packml_state_ = new_packml_state;
        state_changed = true;

        // Log state transitions
        std::cout << "State transition to: " << PackML::stateToString(new_packml_state) << std::endl;
    }

    if (new_bt_tick_status_opt.has_value() && current_bt_tick_status_ != new_bt_tick_status_opt.value())
    {
        current_bt_tick_status_ = new_bt_tick_status_opt.value();
        state_changed = true;
    }

    if (current_packml_state_ != PackML::State::EXECUTE && current_packml_state_ != PackML::State::COMPLETE)
    {
        if (current_bt_tick_status_ != BT::NodeStatus::IDLE)
        {
            current_bt_tick_status_ = BT::NodeStatus::IDLE;
            state_changed = true;
        }
    }

    if (state_changed)
    {
        publishCurrentState();
    }
}

void BehaviorTreeController::publishCurrentState()
{
    if (!mqtt_client_ || !mqtt_client_->is_connected())
    {
        return;
    }
    json state_json;
    state_json["State"] = PackML::stateToString(current_packml_state_);
    state_json["TimeStamp"] = bt_utils::getCurrentTimestampISO();

    if (app_params_.state_publication_config.validateMessage(state_json))
    {
        mqtt_client_->publish_message(
            app_params_.state_publication_config.getTopic(),
            state_json,
            app_params_.state_publication_config.getQos(),
            app_params_.state_publication_config.getRetain());
    }
    else
    {
        std::cerr << "Error: Controller State JSON failed validation for topic '"
                  << app_params_.state_publication_config.getTopic()
                  << "'. Not publishing. Payload: " << state_json.dump(2) << std::endl;
    }
}

void BehaviorTreeController::processBehaviorTreeStart()
{
    if (current_packml_state_ == PackML::State::EXECUTE)
    {
        return;
    }

    // Check if nodes are registered with station configuration
    if (!nodes_registered_.load())
    {
        std::cerr << "Cannot start behavior tree: No station configuration loaded!" << std::endl;
        std::cerr << "Please send station configuration to: "
                  << app_params_.config_topic << std::endl;
        mqtt_start_bt_flag_ = false;
        return;
    }

    auto main_mqtt_message_handler =
        [this](const std::string &topic, const json &payload, mqtt::properties props)
    {
        if (topic == this->app_params_.start_topic)
        {
            if (!this->sigint_received_.load() && this->nodes_registered_.load())
            {
                this->shutdown_flag_ = false;
                this->mqtt_halt_bt_flag_ = false;
                this->mqtt_start_bt_flag_ = true;
            }
        }
        else if (topic == this->app_params_.stop_topic)
        {
            this->requestShutdown();
        }
        else if (topic == this->app_params_.halt_topic)
        {
            this->mqtt_halt_bt_flag_ = true;
        }
        else if (topic == this->app_params_.config_topic)
        {
            this->handleStationConfigUpdate(payload);
        }
        else
        {
            if (this->node_message_distributor_)
            {
                this->node_message_distributor_->handle_incoming_message(topic, payload, props);
            }
        }
    };

    if (current_packml_state_ == PackML::State::SUSPENDED && bt_tree_.rootNode())
    {
        std::cout << "Resuming suspended behavior tree." << std::endl;
        if (mqtt_client_)
        {
            mqtt_client_->set_message_handler(main_mqtt_message_handler);
        }
    }
    else
    {
        if (mqtt_client_)
        {
            mqtt_client_->set_message_handler(nullptr);
        }

        if (node_message_distributor_ && mqtt_client_)
        {
            std::vector<std::string> old_topics = node_message_distributor_->getActiveTopicPatterns();
            if (!old_topics.empty())
            {
                std::cout << "Unsubscribing from " << old_topics.size() << " old topics..." << std::endl;
                for (const auto &topic_str : old_topics)
                {
                    try
                    {
                        mqtt_client_->unsubscribe_topic(topic_str);
                    }
                    catch (const std::exception &e)
                    {
                        std::cerr << "Exception during unsubscribe: " << e.what() << std::endl;
                    }
                }
            }
        }

        if (bt_tree_.rootNode())
        {
            bt_tree_.haltTree();
            bt_publisher_.reset();
        }

        // Recreate node message distributor for fresh start
        node_message_distributor_ = std::make_unique<NodeMessageDistributor>(*mqtt_client_);
        MqttSubBase::setNodeMessageDistributor(node_message_distributor_.get());

        try
        {
            bt_factory_.registerBehaviorTreeFromFile(app_params_.bt_description_path);
            bt_tree_ = bt_factory_.createTree("MainTree");
        }
        catch (const BT::RuntimeError &e)
        {
            std::cerr << "BT Runtime Error during tree creation: " << e.what() << std::endl;
            if (mqtt_client_)
            {
                initializeMqttControlInterface();
            }
            setStateAndPublish(PackML::State::ABORTED);
            mqtt_start_bt_flag_ = false;
            return;
        }

        if (mqtt_client_)
        {
            mqtt_client_->set_message_handler(main_mqtt_message_handler);
        }

        bool subscriptions_successful = false;
        if (node_message_distributor_ && bt_tree_.rootNode())
        {
            std::cout << "Attempting to subscribe to active node topics..." << std::endl;
            subscriptions_successful = node_message_distributor_->subscribeToActiveNodes(
                bt_tree_, std::chrono::seconds(5));
        }

        if (!subscriptions_successful)
        {
            std::cerr << "Failed to establish all necessary MQTT subscriptions. Aborting start." << std::endl;
            if (mqtt_client_)
            {
                mqtt_client_->set_message_handler(nullptr);
                initializeMqttControlInterface();
            }
            if (bt_tree_.rootNode())
            {
                bt_tree_.haltTree();
            }
            bt_publisher_.reset();
            mqtt_start_bt_flag_ = false;
            setStateAndPublish(PackML::State::ABORTED);
            return;
        }

        std::cout << "All MQTT subscriptions for active nodes established." << std::endl;

        bt_publisher_ = std::make_unique<BT::Groot2Publisher>(bt_tree_, app_params_.groot2_port);
    }

    shutdown_flag_ = false;
    mqtt_halt_bt_flag_ = false;
    std::cout << "====== Behavior tree starting/resuming... ======" << std::endl;
    setStateAndPublish(PackML::State::EXECUTE, BT::NodeStatus::IDLE);
}

void BehaviorTreeController::manageRunningBehaviorTree()
{
    if (!bt_tree_.rootNode())
    {
        std::cerr << "Error: BT is in EXECUTE state but tree.rootNode() is null. "
                  << "Transitioning to IDLE." << std::endl;
        setStateAndPublish(PackML::State::IDLE);
        return;
    }

    if (shutdown_flag_.load())
    {
        std::cout << "Stop/Shutdown command active during EXECUTE. "
                  << "Halting tree and transitioning to STOPPED..." << std::endl;
        bt_tree_.haltTree();
        setStateAndPublish(PackML::State::STOPPED);
    }
    else if (mqtt_halt_bt_flag_.load())
    {
        std::cout << "HALT command active during EXECUTE. "
                  << "Halting tree and transitioning to SUSPENDED..." << std::endl;
        bt_tree_.haltTree();
        mqtt_halt_bt_flag_ = false;
        setStateAndPublish(PackML::State::SUSPENDED);
    }
    else
    {
        BT::NodeStatus tick_result = bt_tree_.tickOnce();
        bt_tree_.sleep(std::chrono::milliseconds(100));

        if (BT::isStatusCompleted(tick_result))
        {
            std::cout << "Behavior tree execution completed with status: "
                      << BT::toStr(tick_result) << std::endl;
            setStateAndPublish(PackML::State::COMPLETE, tick_result);
        }
        else
        {
            if (current_bt_tick_status_ != tick_result ||
                current_packml_state_ != PackML::State::EXECUTE)
            {
                setStateAndPublish(PackML::State::EXECUTE, tick_result);
            }
        }
    }
}

void signalHandler(int signum)
{
    if (g_controller_instance)
    {
        g_controller_instance->onSigint();
    }
}

int main(int argc, char *argv[])
{
    std::cout << "Starting Behavior Tree Controller..." << std::endl;
    BehaviorTreeController controller(argc, argv);
    return controller.run();
}
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

    registerAllNodes(bt_factory_, *node_message_distributor_, *mqtt_client_, app_params_.unsTopicPrefix);
    MqttSubBase::setNodeMessageDistributor(node_message_distributor_.get());

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

    // Removed explicit mqtt_client_->disconnect() call.
    // MqttClient's destructor will handle disconnection.
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

        if (current_packml_state_ != PackML::State::EXECUTE)
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
    bt_utils::loadConfigFromYaml(app_params_.configFile, app_params_.generate_xml_models, app_params_.serverURI,
                                 app_params_.clientId, app_params_.unsTopicPrefix, app_params_.groot2_port,
                                 app_params_.bt_description_path, app_params_.bt_nodes_path);

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

    std::string state_topic_str = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/DATA/State";
    std::string schema_path = "../../schemas/state.schema.json";
    app_params_.state_publication_config = mqtt_utils::Topic(state_topic_str, schema_path, 2, true); // QoS 2, Retained
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
        else
        {
            if (this->node_message_distributor_)
            {
                this->node_message_distributor_->handle_incoming_message(topic, payload, props);
            }
            else
            {
                std::cerr << "MQTT message for NMD, but NodeMessageDistributor is null. Topic: " << topic << std::endl;
            }
        }
    };

    mqtt_client_->set_message_handler(main_mqtt_message_handler);

    mqtt_client_->subscribe_topic(app_params_.start_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.stop_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.halt_topic, 2);

    publishCurrentState();
}

bool BehaviorTreeController::handleGenerateXmlModelsOption()
{
    if (app_params_.generate_xml_models)
    {
        std::string xml_models = BT::writeTreeNodesModelXML(bt_factory_);
        bt_utils::saveXmlToFile(xml_models, app_params_.bt_nodes_path);
        std::cout << "XML models saved to: " << app_params_.bt_nodes_path << std::endl;
        return true;
    }
    return false;
}

void BehaviorTreeController::setStateAndPublish(PackML::State new_packml_state, std::optional<BT::NodeStatus> new_bt_tick_status_opt)
{
    bool state_changed = false;

    if (current_packml_state_ != new_packml_state)
    {
        current_packml_state_ = new_packml_state;
        state_changed = true;
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

    if (mqtt_client_)
    {
        mqtt_client_->set_message_handler(nullptr);
    }

    if (current_packml_state_ == PackML::State::SUSPENDED && bt_tree_.rootNode())
    {
    }
    else
    {
        if (node_message_distributor_ && mqtt_client_)
        {
            std::vector<std::string> old_topics = node_message_distributor_->getActiveTopicPatterns();
            if (!old_topics.empty())
            {
                for (const auto &topic : old_topics)
                {
                    try
                    {
                        mqtt_client_->unsubscribe_topic(topic);
                    }
                    catch (const std::exception &e)
                    {
                        std::cerr << "Exception during unsubscribe in processBehaviorTreeStart for topic " << topic << ": " << e.what() << std::endl;
                    }
                }
            }
        }

        if (bt_tree_.rootNode())
        {
            bt_tree_.haltTree();
            bt_publisher_.reset();
        }

        node_message_distributor_ = std::make_unique<NodeMessageDistributor>(*mqtt_client_);
        MqttSubBase::setNodeMessageDistributor(node_message_distributor_.get());

        bt_factory_.registerBehaviorTreeFromFile(app_params_.bt_description_path);
        bt_tree_ = bt_factory_.createTree("MainTree");

        if (node_message_distributor_)
        {
            node_message_distributor_->subscribeToActiveNodes(bt_tree_);
        }

        bt_publisher_ = std::make_unique<BT::Groot2Publisher>(bt_tree_, app_params_.groot2_port);
    }

    if (mqtt_client_)
    {
        auto main_mqtt_message_handler =
            [this](const std::string &topic, const json &payload, mqtt::properties props)
        {
            if (topic == this->app_params_.start_topic)
            {
                if (!this->sigint_received_.load())
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
            else
            {
                if (this->node_message_distributor_)
                {
                    this->node_message_distributor_->handle_incoming_message(topic, payload, props);
                }
            }
        };
        mqtt_client_->set_message_handler(main_mqtt_message_handler);
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
        std::cerr << "Error: BT is in EXECUTE state but tree.rootNode() is null. Transitioning to IDLE." << std::endl;
        setStateAndPublish(PackML::State::IDLE);
        return;
    }

    if (shutdown_flag_.load())
    {
        std::cout << "Stop/Shutdown command active during EXECUTE. Halting tree and transitioning to STOPPED..." << std::endl;
        bt_tree_.haltTree();
        setStateAndPublish(PackML::State::STOPPED);
    }
    else if (mqtt_halt_bt_flag_.load())
    {
        std::cout << "HALT command active during EXECUTE. Halting tree and transitioning to SUSPENDED..." << std::endl;
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
            if (current_bt_tick_status_ != tick_result || current_packml_state_ != PackML::State::EXECUTE)
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
#include "BehaviorTreeController.h"

#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <behaviortree_cpp/xml_parsing.h>
#include <behaviortree_cpp/aas_provider.h>

#include "mqtt/mqtt_client.h"
#include "mqtt/node_message_distributor.h"
#include "mqtt/mqtt_sub_base.h"
#include "aas/aas_interface_cache.h"
#include "aas/aas_client_provider.h"
#include "bt/register_all_nodes.h"
#include "utils.h"

#include <csignal>
#include <chrono>
#include <thread>
#include <iostream>
#include <algorithm>
#include <fstream>
#include <sstream>

BehaviorTreeController *g_controller_instance = nullptr;

BehaviorTreeController::BehaviorTreeController(int argc, char *argv[])
    : mqtt_start_bt_flag_{false},
      mqtt_suspend_bt_flag_{false},
      mqtt_unsuspend_bt_flag_{false},
      mqtt_reset_bt_flag_{false},
      shutdown_flag_{false},
      sigint_received_{false},
      nodes_registered_{false},
      current_packml_state_{PackML::State::STOPPED},
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
    aas_client_ = std::make_shared<AASClient>(app_params_.aasServerUrl, app_params_.aasRegistryUrl);

    // Initialize AAS interface cache for pre-fetching
    aas_interface_cache_ = std::make_unique<AASInterfaceCache>(*aas_client_);

    // Initialize BehaviorTreeFactory
    bt_factory_ = std::make_unique<BT::BehaviorTreeFactory>();

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

bool BehaviorTreeController::fetchAndBuildEquipmentMapping(BT::Blackboard::Ptr blackboard)
{
    std::cout << "Building equipment mapping from process AAS..." << std::endl;

    // Get the process AAS ID
    std::string process_id;
    {
        std::lock_guard<std::mutex> lock(process_aas_id_mutex_);
        process_id = process_aas_id_;
    }

    if (process_id.empty())
    {
        std::cerr << "No process AAS ID available!" << std::endl;
        return false;
    }

    std::cout << "Process AAS ID: " << process_id << std::endl;

    try
    {
        // Clear existing mapping
        {
            std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);
            equipment_aas_mapping_.clear();
        }

        // Fetch the RequiredCapabilities submodel from the process AAS
        auto capabilities_opt = aas_client_->fetchRequiredCapabilities(process_id);
        if (!capabilities_opt.has_value())
        {
            std::cerr << "Could not fetch RequiredCapabilities from process AAS: " << process_id << std::endl;
            return false;
        }

        const auto &capabilities = capabilities_opt.value();
        std::cout << "Found RequiredCapabilities submodel" << std::endl;

        // Parse each capability and extract the resource references
        if (!capabilities.contains("submodelElements") || !capabilities["submodelElements"].is_array())
        {
            std::cerr << "No submodelElements in RequiredCapabilities" << std::endl;
            return false;
        }

        std::set<std::string> processed_resources;

        // Each submodelElement is a capability (SubmodelElementCollection)
        for (const auto &capability : capabilities["submodelElements"])
        {
            if (!capability.contains("modelType") ||
                capability["modelType"].get<std::string>() != "SubmodelElementCollection")
            {
                continue;
            }

            std::string capability_name = capability.value("idShort", "unknown");
            std::cout << "  Processing capability: " << capability_name << std::endl;

            // Navigate into the capability's value array to find the References collection
            if (!capability.contains("value") || !capability["value"].is_array())
            {
                continue;
            }

            for (const auto &element : capability["value"])
            {
                // Look for the References SubmodelElementCollection
                if (!element.contains("modelType") ||
                    element["modelType"].get<std::string>() != "SubmodelElementCollection")
                {
                    continue;
                }

                if (!element.contains("idShort") || element["idShort"].get<std::string>() != "References")
                {
                    continue;
                }

                // Found the References collection, now extract ReferenceElements
                if (!element.contains("value") || !element["value"].is_array())
                {
                    continue;
                }

                for (const auto &ref_element : element["value"])
                {
                    if (!ref_element.contains("modelType") ||
                        ref_element["modelType"].get<std::string>() != "ReferenceElement")
                    {
                        continue;
                    }

                    // The idShort of the ReferenceElement is the resource name (e.g., "imaLoadingSystemAAS")
                    if (!ref_element.contains("idShort"))
                    {
                        continue;
                    }

                    std::string resource_id_short = ref_element["idShort"].get<std::string>();

                    // Skip if already processed
                    if (processed_resources.find(resource_id_short) != processed_resources.end())
                    {
                        continue;
                    }
                    processed_resources.insert(resource_id_short);

                    // Derive AAS shell ID from the submodel reference
                    // Submodel pattern: {base_url}/submodels/instances/{idShort}/...
                    // AAS pattern: {base_url}/aas/{systemName} where systemName = idShort without "AAS" suffix
                    std::string aas_shell_id;

                    if (ref_element.contains("value") &&
                        ref_element["value"].contains("keys") &&
                        ref_element["value"]["keys"].is_array() &&
                        !ref_element["value"]["keys"].empty())
                    {
                        std::string submodel_id = ref_element["value"]["keys"][0]["value"].get<std::string>();

                        // Extract idShort from submodel path: .../instances/{idShort}/...
                        size_t instances_pos = submodel_id.find("/instances/");
                        if (instances_pos != std::string::npos)
                        {
                            size_t id_start = instances_pos + 11; // length of "/instances/"
                            size_t id_end = submodel_id.find('/', id_start);
                            if (id_end != std::string::npos)
                            {
                                std::string id_short = submodel_id.substr(id_start, id_end - id_start);

                                // Construct AAS shell ID using the idShort (with AAS suffix)
                                size_t base_end = submodel_id.find("/submodels/");
                                if (base_end != std::string::npos)
                                {
                                    std::string base_url = submodel_id.substr(0, base_end);
                                    aas_shell_id = base_url + "/aas/" + id_short;
                                }
                            }
                        }
                    }

                    if (aas_shell_id.empty())
                    {
                        std::cerr << "    Could not derive AAS shell ID for: " << resource_id_short << std::endl;
                        continue;
                    }

                    // Use the resource idShort (with AAS suffix) as the key
                    std::string resource_name = resource_id_short;

                    std::cout << "    Found resource: " << resource_name << " -> " << aas_shell_id << std::endl;

                    // Add to equipment mapping
                    {
                        std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);
                        equipment_aas_mapping_[resource_name] = aas_shell_id;
                    }
                }
            }
        }

        {
            std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);

            if (equipment_aas_mapping_.empty())
            {
                std::cerr << "No equipment found in process AAS RequiredCapabilities!" << std::endl;
                return false;
            }

            std::cout << "Equipment mapping built successfully with "
                      << equipment_aas_mapping_.size() << " entries:" << std::endl;
            for (const auto &[name, id] : equipment_aas_mapping_)
            {
                std::cout << "  " << name << " -> " << id << std::endl;
            }
        }

        // Fetch the ProductReference from ProcessInformation submodel
        auto process_info_opt = aas_client_->fetchProcessInformation(process_id);
        if (process_info_opt.has_value())
        {
            const auto &process_info = process_info_opt.value();
            
            // Look for ProductReference in submodelElements
            if (process_info.contains("submodelElements") && process_info["submodelElements"].is_array())
            {
                for (const auto &element : process_info["submodelElements"])
                {
                    if (element.contains("modelType") && 
                        element["modelType"].get<std::string>() == "ReferenceElement" &&
                        element.contains("idShort") && 
                        element["idShort"].get<std::string>() == "ProductReference")
                    {
                        // Extract the product AAS ID from the reference
                        if (element.contains("value") &&
                            element["value"].contains("keys") &&
                            element["value"]["keys"].is_array() &&
                            !element["value"]["keys"].empty())
                        {
                            std::string product_aas_id = element["value"]["keys"][0]["value"].get<std::string>();
                            
                            std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);
                            equipment_aas_mapping_["product"] = product_aas_id;
                            std::cout << "  Found product AAS: product -> " << product_aas_id << std::endl;
                        }
                        break;
                    }
                }
            }
        }
        else
        {
            std::cerr << "Warning: Could not fetch ProcessInformation submodel, product AAS will not be available" << std::endl;
        }

        // Populate blackboard if provided
        if (blackboard)
        {
            populateBlackboard(blackboard);
        }

        return true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error fetching equipment from process AAS: " << e.what() << std::endl;
        return false;
    }
}

void BehaviorTreeController::populateBlackboard(BT::Blackboard::Ptr blackboard)
{
    if (!blackboard)
    {
        std::cerr << "Cannot populate blackboard: blackboard is null" << std::endl;
        return;
    }

    std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);
    std::cout << "Populating blackboard with equipment mapping..." << std::endl;

    // Store each equipment mapping in the blackboard
    // Simple name -> AAS URL (e.g., "LoadingSystemAAS" -> "https://.../imaLoadingSystemAAS")
    for (const auto &[equipment_name, aas_id] : equipment_aas_mapping_)
    {
        blackboard->set(equipment_name, aas_id);
        std::cout << "  Set blackboard[" << equipment_name << "] = " << aas_id << std::endl;
    }

    std::cout << "Blackboard populated with " << equipment_aas_mapping_.size() << " equipment entries" << std::endl;
}

bool BehaviorTreeController::prefetchAssetInterfaces()
{
    std::cout << "Pre-fetching asset interfaces..." << std::endl;

    // Get the equipment mapping
    std::map<std::string, std::string> mapping_copy;
    {
        std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);
        mapping_copy = equipment_aas_mapping_;
    }

    if (mapping_copy.empty())
    {
        std::cerr << "No equipment mapping available for prefetching" << std::endl;
        return false;
    }

    // Pre-fetch all asset interface descriptions
    if (!aas_interface_cache_->prefetchInterfaces(mapping_copy))
    {
        std::cerr << "Warning: Failed to prefetch some asset interfaces" << std::endl;
        // Continue anyway - nodes can still fall back to direct AAS queries
        return false;
    }

    std::cout << "Pre-fetch returning true" << std::endl << std::flush;
    return true;
}

bool BehaviorTreeController::subscribeToTopics()
{
    std::cout << "Subscribing to topics for active nodes..." << std::endl;

    // Use the distributor to subscribe to specific topics for active nodes
    // This triggers delivery of retained messages
    return node_message_distributor_->subscribeForActiveNodes(bt_tree_, std::chrono::seconds(5));
}

bool BehaviorTreeController::registerNodesWithAASConfig()
{
    std::cout << "Entering registerNodesWithAASConfig..." << std::endl << std::flush;
    try
    {
        // Register all nodes (they will read equipment mapping from blackboard)
        std::cout << "  Calling registerAllNodes..." << std::endl << std::flush;
        registerAllNodes(*bt_factory_, *node_message_distributor_, *mqtt_client_, *aas_client_);
        std::cout << "  registerAllNodes complete" << std::endl << std::flush;

        // Set the node message distributor and interface cache for base classes
        MqttSubBase::setNodeMessageDistributor(node_message_distributor_.get());
        MqttSubBase::setAASInterfaceCache(aas_interface_cache_.get());
        std::cout << "  Node registration complete" << std::endl << std::flush;
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
    // Halt any running tree before unregistering
    if (bt_tree_.rootNode())
    {
        bt_tree_.haltTree();
    }

    // Reset Groot2 publisher
    bt_publisher_.reset();

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

    // Create a new BehaviorTreeFactory to completely clear all node registrations
    // This is necessary because BT factory doesn't provide a way to unregister individual nodes
    bt_factory_ = std::make_unique<BT::BehaviorTreeFactory>();

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
        // Handle reset command - transition to RESETTING state
        if (mqtt_reset_bt_flag_.load())
        {
            if (!sigint_received_.load())
            {
                processResettingState();
            }
            mqtt_reset_bt_flag_ = false;
        }

        // Handle shutdown/stop during execution
        if (shutdown_flag_.load() && !mqtt_start_bt_flag_.load())
        {
            if (current_packml_state_ == PackML::State::EXECUTE)
            {
                // Stop will be handled in manageRunningBehaviorTree
            }
            else if (current_packml_state_ == PackML::State::IDLE)
            {
                // Transition from IDLE to STOPPED when stop command received
                setStateAndPublish(PackML::State::STOPPED);
            }
            // If already in STOPPED or COMPLETE, remain there until reset

            // Only exit on SIGINT
            if (sigint_received_.load())
            {
                break;
            }
        }

        // Handle start command
        if (mqtt_start_bt_flag_.load())
        {
            if (!sigint_received_.load() && current_packml_state_ == PackML::State::IDLE)
            {
                processBehaviorTreeStart();
            }
            mqtt_start_bt_flag_ = false;
        }

        // Handle unsuspend command
        if (mqtt_unsuspend_bt_flag_.load())
        {
            if (!sigint_received_.load() && current_packml_state_ == PackML::State::SUSPENDED)
            {
                processBehaviorTreeUnsuspend();
            }
            mqtt_unsuspend_bt_flag_ = false;
        }

        // Execute behavior tree if in EXECUTE state
        if (current_packml_state_ == PackML::State::EXECUTE)
        {
            manageRunningBehaviorTree();
        }
        else
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
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
        app_params_.aasRegistryUrl,
        app_params_.groot2_port,
        app_params_.bt_description_path,
        app_params_.bt_nodes_path,
        app_params_.registration_config_path,
        app_params_.registration_topic_pattern);

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
    app_params_.suspend_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/CMD/Suspend";
    app_params_.unsuspend_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/CMD/Unsuspend";
    app_params_.reset_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/CMD/Reset";

    // Response topics for command acknowledgments
    app_params_.start_response_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/DATA/Start";
    app_params_.stop_response_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/DATA/Stop";
    app_params_.suspend_response_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/DATA/Suspend";
    app_params_.unsuspend_response_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/DATA/Unsuspend";
    app_params_.reset_response_topic = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/DATA/Reset";

    // Resolve registration topic by replacing {client_id} placeholder
    if (!app_params_.registration_topic_pattern.empty())
    {
        app_params_.registration_topic = app_params_.registration_topic_pattern;
        size_t pos = app_params_.registration_topic.find("{client_id}");
        if (pos != std::string::npos)
        {
            app_params_.registration_topic.replace(pos, 11, app_params_.clientId);
        }
        std::cout << "  Registration Topic: " << app_params_.registration_topic << std::endl;
    }

    std::string state_topic_str = app_params_.unsTopicPrefix + "/" + app_params_.clientId + "/DATA/State";
    std::string state_schema_url = "https://aausmartproductionlab.github.io/AP2030-UNS/MQTTSchemas/state.schema.json";

    // Fetch and resolve the state schema
    nlohmann::json state_schema = schema_utils::fetchSchemaFromUrl(state_schema_url);
    if (!state_schema.empty())
    {
        schema_utils::resolveSchemaReferences(state_schema);
        app_params_.state_publication_config = mqtt_utils::Topic(state_topic_str, state_schema, 2, true);
    }
    else
    {
        std::cerr << "Warning: Failed to fetch state schema, creating topic without schema validation" << std::endl;
        app_params_.state_publication_config = mqtt_utils::Topic(state_topic_str, nlohmann::json(), 2, true);
    }
}

void BehaviorTreeController::setupMainMqttMessageHandler()
{
    main_mqtt_message_handler_ =
        [this](const std::string &topic, const nlohmann::json &payload, mqtt::properties props)
    {
        if (topic == this->app_params_.start_topic)
        {
            std::string uuid = (payload.contains("Uuid") && payload["Uuid"].is_string())
                                   ? payload["Uuid"].get<std::string>()
                                   : "";

            if (!this->sigint_received_.load())
            {
                // Only allow start from IDLE state
                if (this->current_packml_state_ != PackML::State::IDLE)
                {
                    std::cerr << "Cannot start from " << PackML::stateToString(this->current_packml_state_)
                              << " state. Must be in IDLE state." << std::endl;
                    this->publishCommandResponse(this->app_params_.start_response_topic, uuid, false);
                    return;
                }

                // Extract Process AAS ID from the Start command payload
                if (!payload.contains("Process") || !payload["Process"].is_string())
                {
                    std::cerr << "Cannot start: Start command must contain 'Process' field with AAS ID" << std::endl;
                    this->publishCommandResponse(this->app_params_.start_response_topic, uuid, false);
                    return;
                }

                {
                    std::lock_guard<std::mutex> lock(this->process_aas_id_mutex_);
                    this->process_aas_id_ = payload["Process"].get<std::string>();
                }
                std::cout << "Received Start command with Process: " << payload["Process"].get<std::string>() << std::endl;

                // Store UUID for response after processing
                {
                    std::lock_guard<std::mutex> lock(this->pending_command_mutex_);
                    this->pending_start_uuid_ = uuid;
                }

                this->shutdown_flag_ = false;
                this->mqtt_suspend_bt_flag_ = false;
                this->mqtt_unsuspend_bt_flag_ = false;
                this->mqtt_reset_bt_flag_ = false;
                this->mqtt_start_bt_flag_ = true;
            }
            else
            {
                this->publishCommandResponse(this->app_params_.start_response_topic, uuid, false);
            }
        }
        else if (topic == this->app_params_.stop_topic)
        {
            std::string uuid = (payload.contains("Uuid") && payload["Uuid"].is_string())
                                   ? payload["Uuid"].get<std::string>()
                                   : "";
            {
                std::lock_guard<std::mutex> lock(this->pending_command_mutex_);
                this->pending_stop_uuid_ = uuid;
            }
            this->requestShutdown();
        }
        else if (topic == this->app_params_.suspend_topic)
        {
            std::string uuid = (payload.contains("Uuid") && payload["Uuid"].is_string())
                                   ? payload["Uuid"].get<std::string>()
                                   : "";
            {
                std::lock_guard<std::mutex> lock(this->pending_command_mutex_);
                this->pending_suspend_uuid_ = uuid;
            }
            this->mqtt_suspend_bt_flag_ = true;
        }
        else if (topic == this->app_params_.unsuspend_topic)
        {
            std::string uuid = (payload.contains("Uuid") && payload["Uuid"].is_string())
                                   ? payload["Uuid"].get<std::string>()
                                   : "";
            if (this->current_packml_state_ == PackML::State::SUSPENDED)
            {
                {
                    std::lock_guard<std::mutex> lock(this->pending_command_mutex_);
                    this->pending_unsuspend_uuid_ = uuid;
                }
                this->mqtt_unsuspend_bt_flag_ = true;
            }
            else
            {
                std::cerr << "Unsuspend command can only be used from SUSPENDED state." << std::endl;
                this->publishCommandResponse(this->app_params_.unsuspend_response_topic, uuid, false);
            }
        }
        else if (topic == this->app_params_.reset_topic)
        {
            std::string uuid = (payload.contains("Uuid") && payload["Uuid"].is_string())
                                   ? payload["Uuid"].get<std::string>()
                                   : "";
            if (this->current_packml_state_ == PackML::State::STOPPED ||
                this->current_packml_state_ == PackML::State::COMPLETE ||
                this->current_packml_state_ == PackML::State::ABORTED)
            {
                {
                    std::lock_guard<std::mutex> lock(this->pending_command_mutex_);
                    this->pending_reset_uuid_ = uuid;
                }
                this->mqtt_reset_bt_flag_ = true;
            }
            else
            {
                std::cerr << "Reset command can only be used from STOPPED, COMPLETE, or ABORTED states." << std::endl;
                this->publishCommandResponse(this->app_params_.reset_response_topic, uuid, false);
            }
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
}

void BehaviorTreeController::initializeMqttControlInterface()
{
    if (!mqtt_client_)
    {
        std::cerr << "Error: mqtt_client_ is null in initializeMqttControlInterface." << std::endl;
        return;
    }

    setupMainMqttMessageHandler();
    mqtt_client_->set_message_handler(main_mqtt_message_handler_);

    mqtt_client_->subscribe_topic(app_params_.start_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.stop_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.suspend_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.unsuspend_topic, 2);
    mqtt_client_->subscribe_topic(app_params_.reset_topic, 2);

    std::cout << "MQTT control interface initialized." << std::endl;

    // Publish orchestrator config to registration service for AAS generation
    if (!publishConfigToRegistrationService())
    {
        std::cerr << "Warning: Failed to publish config to registration service" << std::endl;
        std::cerr << "         The AAS may not be generated/updated" << std::endl;
    }

    publishCurrentState();
}

bool BehaviorTreeController::handleGenerateXmlModelsOption()
{
    if (app_params_.generate_xml_models)
    {
        // For XML generation, we need a dummy configuration
        std::cout << "Generating XML models requires station configuration..." << std::endl;

        if (!nodes_registered_)
        {
            // Fetch equipment mapping from AAS if not already done
            if (equipment_aas_mapping_.empty())
            {
                fetchAndBuildEquipmentMapping(nullptr);
            }
            registerNodesWithAASConfig();
        }

        std::string xml_models = BT::writeTreeNodesModelXML(*bt_factory_);
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
    nlohmann::json state_json;
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

void BehaviorTreeController::publishCommandResponse(const std::string &response_topic,
                                                    const std::string &uuid,
                                                    bool success)
{
    if (!mqtt_client_ || !mqtt_client_->is_connected())
    {
        std::cerr << "Cannot publish command response: MQTT client not connected" << std::endl;
        return;
    }

    nlohmann::json response_json;
    response_json["Uuid"] = uuid;
    response_json["State"] = success ? "SUCCESS" : "FAILURE";
    response_json["TimeStamp"] = bt_utils::getCurrentTimestampISO();

    mqtt_client_->publish_message(response_topic, response_json, 2, false);

    std::cout << "Published command response to " << response_topic
              << ": " << (success ? "SUCCESS" : "FAILURE") << std::endl;
}

void BehaviorTreeController::processBehaviorTreeStart()
{
    if (current_packml_state_ != PackML::State::IDLE)
    {
        std::cerr << "Cannot start: Not in IDLE state" << std::endl;
        return;
    }

    // Get the process AAS ID from the stored value
    std::string process_id;
    {
        std::lock_guard<std::mutex> lock(process_aas_id_mutex_);
        process_id = process_aas_id_;
    }

    if (process_id.empty())
    {
        std::cerr << "Cannot start: No process AAS ID specified!" << std::endl;
        return;
    }

    std::cout << "====== Starting behavior tree for process: " << process_id << " ======" << std::endl;

    // Transition to STARTING state and initialize the BT
    processStartingState();
}

void BehaviorTreeController::processStartingState()
{
    std::cout << "====== Entering STARTING state... ======" << std::endl;
    setStateAndPublish(PackML::State::STARTING);

    // Get the process AAS ID
    std::string process_id;
    {
        std::lock_guard<std::mutex> lock(process_aas_id_mutex_);
        process_id = process_aas_id_;
    }

    // Clear any existing flags
    shutdown_flag_ = false;
    mqtt_suspend_bt_flag_ = false;
    mqtt_unsuspend_bt_flag_ = false;
    mqtt_reset_bt_flag_ = false;

    // Fetch equipment mapping from AAS hierarchical structure
    std::cout << "Fetching production line structure from AAS..." << std::endl;
    if (!fetchAndBuildEquipmentMapping(nullptr))
    {
        std::cerr << "Failed to fetch equipment mapping from AAS!" << std::endl;
        std::cerr << "Cannot continue without equipment configuration." << std::endl;
        setStateAndPublish(PackML::State::ABORTED);

        // Send failure response for Start command
        std::string uuid;
        {
            std::lock_guard<std::mutex> lock(pending_command_mutex_);
            uuid = pending_start_uuid_;
            pending_start_uuid_.clear();
        }
        publishCommandResponse(app_params_.start_response_topic, uuid, false);
        return;
    }

    std::cout << "Equipment mapping successfully built from AAS" << std::endl;

    // Pre-fetch asset interface descriptions (but don't subscribe yet)
    // This allows nodes to get topic info from cache during initialization
    if (!prefetchAssetInterfaces())
    {
        std::cerr << "Warning: Failed to prefetch asset interfaces, nodes will query AAS individually" << std::endl;
        // Continue anyway - this is a performance optimization, not a hard requirement
    }

    // Register nodes with the equipment mapping
    if (!registerNodesWithAASConfig())
    {
        std::cerr << "Failed to register nodes with AAS configuration!" << std::endl;
        setStateAndPublish(PackML::State::ABORTED);
        nodes_registered_ = false;

        // Send failure response for Start command
        std::string uuid;
        {
            std::lock_guard<std::mutex> lock(pending_command_mutex_);
            uuid = pending_start_uuid_;
            pending_start_uuid_.clear();
        }
        publishCommandResponse(app_params_.start_response_topic, uuid, false);
        return;
    }

    std::cout << "Nodes successfully registered with AAS configuration." << std::endl;
    nodes_registered_ = true;

    // ===== Initialize Behavior Tree =====
    std::cout << "Initializing behavior tree for process: " << process_id << std::endl;

    // Temporarily disable message handler during tree creation
    if (mqtt_client_)
    {
        mqtt_client_->set_message_handler(nullptr);
    }

    try
    {
        // Fetch BT description URL from the process AAS Policy submodel
        auto bt_url_opt = aas_client_->fetchPolicyBTUrl(process_id);
        if (!bt_url_opt.has_value())
        {
            std::cerr << "Failed to fetch BT description URL from process AAS Policy submodel" << std::endl;
            if (mqtt_client_)
            {
                mqtt_client_->set_message_handler(main_mqtt_message_handler_);
            }
            setStateAndPublish(PackML::State::ABORTED);

            std::string uuid;
            {
                std::lock_guard<std::mutex> lock(pending_command_mutex_);
                uuid = pending_start_uuid_;
                pending_start_uuid_.clear();
            }
            publishCommandResponse(app_params_.start_response_topic, uuid, false);
            return;
        }

        std::string bt_url = bt_url_opt.value();
        std::cout << "Fetching BT description from: " << bt_url << std::endl;

        // Fetch the BT XML content from the URL
        std::string bt_xml_content = schema_utils::fetchContentFromUrl(bt_url);
        if (bt_xml_content.empty())
        {
            std::cerr << "Failed to fetch BT description XML from URL: " << bt_url << std::endl;
            if (mqtt_client_)
            {
                mqtt_client_->set_message_handler(main_mqtt_message_handler_);
            }
            setStateAndPublish(PackML::State::ABORTED);

            std::string uuid;
            {
                std::lock_guard<std::mutex> lock(pending_command_mutex_);
                uuid = pending_start_uuid_;
                pending_start_uuid_.clear();
            }
            publishCommandResponse(app_params_.start_response_topic, uuid, false);
            return;
        }

        std::cout << "Successfully fetched BT description (" << bt_xml_content.size() << " bytes)" << std::endl;

        // Create blackboard and populate with equipment mapping
        auto root_blackboard = BT::Blackboard::create();
        
        // Set up AAS provider for $aas{} references in behavior tree
        auto aas_provider = createCachingAASProvider(aas_client_, std::chrono::seconds(300));
        root_blackboard->setAASProvider(aas_provider);
        std::cout << "AAS provider configured on blackboard (TTL: 300s)" << std::endl;
        
        populateBlackboard(root_blackboard);

        // Store the process ID in blackboard for nodes to access
        root_blackboard->set("ProcessAASId", process_id);

        // createTreeFromText parses XML, registers the tree, and creates it in one call
        // It automatically uses the main_tree_to_execute attribute from the XML
        bt_tree_ = bt_factory_->createTreeFromText(bt_xml_content, root_blackboard);
    }
    catch (const BT::RuntimeError &e)
    {
        std::cerr << "BT Runtime Error during tree creation: " << e.what() << std::endl;
        if (mqtt_client_)
        {
            mqtt_client_->set_message_handler(main_mqtt_message_handler_);
        }
        setStateAndPublish(PackML::State::ABORTED);

        // Send failure response for Start command
        std::string uuid;
        {
            std::lock_guard<std::mutex> lock(pending_command_mutex_);
            uuid = pending_start_uuid_;
            pending_start_uuid_.clear();
        }
        publishCommandResponse(app_params_.start_response_topic, uuid, false);
        return;
    }

    // Restore message handler
    if (mqtt_client_)
    {
        mqtt_client_->set_message_handler(main_mqtt_message_handler_);
    }

    // Subscribe to topics for active nodes - this sets up routing AND subscribes,
    // which triggers delivery of retained messages
    if (!subscribeToTopics())
    {
        std::cerr << "Failed to subscribe to topics for active nodes." << std::endl;
        if (bt_tree_.rootNode())
        {
            bt_tree_.haltTree();
        }
        bt_publisher_.reset();
        setStateAndPublish(PackML::State::ABORTED);

        // Send failure response for Start command
        std::string uuid;
        {
            std::lock_guard<std::mutex> lock(pending_command_mutex_);
            uuid = pending_start_uuid_;
            pending_start_uuid_.clear();
        }
        publishCommandResponse(app_params_.start_response_topic, uuid, false);
        return;
    }

    std::cout << "Topic subscriptions established - retained messages delivered." << std::endl;

    // Create Groot2 publisher
    bt_publisher_ = std::make_unique<BT::Groot2Publisher>(bt_tree_, app_params_.groot2_port);

    // Transition to EXECUTE state after successful initialization
    std::cout << "====== Behavior tree fully initialized, transitioning to EXECUTE... ======" << std::endl;
    setStateAndPublish(PackML::State::EXECUTE, BT::NodeStatus::IDLE);

    // Send success response for Start command
    std::string uuid;
    {
        std::lock_guard<std::mutex> lock(pending_command_mutex_);
        uuid = pending_start_uuid_;
        pending_start_uuid_.clear();
    }
    publishCommandResponse(app_params_.start_response_topic, uuid, true);
}

void BehaviorTreeController::processBehaviorTreeUnsuspend()
{
    if (current_packml_state_ != PackML::State::SUSPENDED)
    {
        std::cerr << "Cannot unsuspend: Not in SUSPENDED state" << std::endl;
        return;
    }

    if (!bt_tree_.rootNode())
    {
        std::cerr << "Cannot unsuspend: No behavior tree exists" << std::endl;
        setStateAndPublish(PackML::State::IDLE);
        return;
    }

    std::cout << "====== Resuming suspended behavior tree... ======" << std::endl;

    // Restore message handler if needed
    if (mqtt_client_)
    {
        mqtt_client_->set_message_handler(main_mqtt_message_handler_);
    }

    shutdown_flag_ = false;
    mqtt_suspend_bt_flag_ = false;
    mqtt_unsuspend_bt_flag_ = false;

    setStateAndPublish(PackML::State::EXECUTE, BT::NodeStatus::IDLE);

    // Send success response for Unsuspend command
    std::string uuid;
    {
        std::lock_guard<std::mutex> lock(pending_command_mutex_);
        uuid = pending_unsuspend_uuid_;
        pending_unsuspend_uuid_.clear();
    }
    publishCommandResponse(app_params_.unsuspend_response_topic, uuid, true);
}

void BehaviorTreeController::processResettingState()
{
    std::cout << "====== Entering RESETTING state... ======" << std::endl;
    setStateAndPublish(PackML::State::RESETTING);

    // Clear any existing flags
    mqtt_start_bt_flag_ = false;
    mqtt_suspend_bt_flag_ = false;
    mqtt_unsuspend_bt_flag_ = false;
    mqtt_reset_bt_flag_ = false;
    shutdown_flag_ = false;

    // Clear stored process AAS ID
    {
        std::lock_guard<std::mutex> lock(process_aas_id_mutex_);
        process_aas_id_.clear();
    }

    // Unsubscribe from old node topics if any
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

    // Halt and clear any existing tree and factory
    if (bt_tree_.rootNode())
    {
        std::cout << "Halting existing behavior tree..." << std::endl;
        bt_tree_.haltTree();
        bt_publisher_.reset();
    }

    // Reset the tree and factory to clear all old registrations
    bt_tree_ = BT::Tree();
    bt_factory_ = std::make_unique<BT::BehaviorTreeFactory>();

    // Recreate node message distributor for fresh start
    node_message_distributor_ = std::make_unique<NodeMessageDistributor>(*mqtt_client_);
    MqttSubBase::setNodeMessageDistributor(node_message_distributor_.get());

    // Clear equipment mapping
    {
        std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);
        equipment_aas_mapping_.clear();
    }

    // Mark nodes as not registered
    nodes_registered_ = false;

    std::cout << "====== Reset complete, all BT interfaces purged. Transitioning to IDLE... ======" << std::endl;
    setStateAndPublish(PackML::State::IDLE);

    // Send success response for Reset command
    std::string uuid;
    {
        std::lock_guard<std::mutex> lock(pending_command_mutex_);
        uuid = pending_reset_uuid_;
        pending_reset_uuid_.clear();
    }
    publishCommandResponse(app_params_.reset_response_topic, uuid, true);
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

        // Send success response for Stop command
        std::string uuid;
        {
            std::lock_guard<std::mutex> lock(pending_command_mutex_);
            uuid = pending_stop_uuid_;
            pending_stop_uuid_.clear();
        }
        publishCommandResponse(app_params_.stop_response_topic, uuid, true);
    }
    else if (mqtt_suspend_bt_flag_.load())
    {
        std::cout << "SUSPEND command active during EXECUTE. "
                  << "Halting tree and transitioning to SUSPENDED..." << std::endl;
        bt_tree_.haltTree();
        mqtt_suspend_bt_flag_ = false;
        setStateAndPublish(PackML::State::SUSPENDED);

        // Send success response for Suspend command
        std::string uuid;
        {
            std::lock_guard<std::mutex> lock(pending_command_mutex_);
            uuid = pending_suspend_uuid_;
            pending_suspend_uuid_.clear();
        }
        publishCommandResponse(app_params_.suspend_response_topic, uuid, true);
    }
    else if (mqtt_unsuspend_bt_flag_.load())
    {
        std::cout << "HALT command active during EXECUTE. "
                  << "Halting tree and transitioning to SUSPENDED..." << std::endl;
        bt_tree_.haltTree();
        mqtt_unsuspend_bt_flag_ = false;
        setStateAndPublish(PackML::State::EXECUTE);
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

bool BehaviorTreeController::publishConfigToRegistrationService()
{
    // Check if registration is configured
    if (app_params_.registration_config_path.empty() || app_params_.registration_topic.empty())
    {
        std::cout << "Registration not configured, skipping config publication" << std::endl;
        return true; // Not an error, just not configured
    }

    if (!mqtt_client_ || !mqtt_client_->is_connected())
    {
        std::cerr << "Cannot publish registration config: MQTT client not connected" << std::endl;
        return false;
    }

    std::cout << "Loading AAS description config from: " << app_params_.registration_config_path << std::endl;

    // Load the YAML config file and send it as-is (raw YAML)
    // The registration service can parse raw YAML directly
    std::ifstream config_file(app_params_.registration_config_path);
    if (!config_file.is_open())
    {
        std::cerr << "Failed to open AAS description config: " << app_params_.registration_config_path << std::endl;
        return false;
    }

    std::stringstream buffer;
    buffer << config_file.rdbuf();
    std::string yaml_content = buffer.str();
    config_file.close();

    if (yaml_content.empty())
    {
        std::cerr << "AAS description config file is empty: " << app_params_.registration_config_path << std::endl;
        return false;
    }

    std::cout << "Publishing registration config to: " << app_params_.registration_topic << std::endl;

    // Publish raw YAML content with QoS 2 (exactly once) and retain=false
    // The registration service will parse the YAML directly
    try
    {
        auto msg = mqtt::message::create(
            app_params_.registration_topic,
            yaml_content,
            2,    // QoS 2 for reliable delivery
            false // Don't retain
        );
        mqtt_client_->publish(msg)->wait();
        std::cout << "Successfully published registration config to registration service" << std::endl;
        return true;
    }
    catch (const mqtt::exception &e)
    {
        std::cerr << "Failed to publish registration config: " << e.what() << std::endl;
        return false;
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
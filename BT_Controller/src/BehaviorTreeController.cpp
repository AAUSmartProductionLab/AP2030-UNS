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
    aas_client_ = std::make_unique<AASClient>(app_params_.aasServerUrl, app_params_.aasRegistryUrl);

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

bool BehaviorTreeController::fetchAndBuildEquipmentMapping()
{
    std::cout << "Fetching hierarchical structures from AAS..." << std::endl;
    std::cout << "Asset IDs to resolve:" << std::endl;
    for (const auto &asset_id : app_params_.asset_ids_to_resolve)
    {
        std::cout << "  - " << asset_id << std::endl;
    }

    try
    {
        // Clear existing mapping
        {
            std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);
            equipment_aas_mapping_.clear();
        }

        // Recursively resolve the hierarchy for each asset in the list
        std::set<std::string> visited_assets;
        for (const auto &asset_id : app_params_.asset_ids_to_resolve)
        {
            // Extract a simple name from the asset ID for logging
            std::string asset_name = asset_id.substr(asset_id.find_last_of('/') + 1);
            recursivelyResolveHierarchy(asset_id, asset_name, visited_assets);
        }

        {
            std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);

            if (equipment_aas_mapping_.empty())
            {
                std::cerr << "No equipment found in hierarchical structure!" << std::endl;
                return false;
            }

            std::cout << "Equipment mapping built successfully with "
                      << equipment_aas_mapping_.size() << " entries:" << std::endl;
            for (const auto &[name, id] : equipment_aas_mapping_)
            {
                std::cout << "  " << name << " -> " << id << std::endl;
            }
        }

        return true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error fetching hierarchical structure: " << e.what() << std::endl;
        return false;
    }
}

std::string BehaviorTreeController::getArchetype(const nlohmann::json &hierarchy_submodel)
{
    if (!hierarchy_submodel.contains("submodelElements") || !hierarchy_submodel["submodelElements"].is_array())
    {
        return "";
    }

    for (const auto &element : hierarchy_submodel["submodelElements"])
    {
        if (element.contains("idShort") && element["idShort"].get<std::string>() == "Archetype" &&
            element.contains("modelType") && element["modelType"].get<std::string>() == "Property")
        {
            if (element.contains("value"))
            {
                return element["value"].get<std::string>();
            }
        }
    }

    return "";
}

void BehaviorTreeController::recursivelyResolveHierarchy(const std::string &asset_id, const std::string &asset_name,
                                                         std::set<std::string> &visited_assets)
{
    std::cout << "Resolving hierarchy for: " << asset_name << " (" << asset_id << ")" << std::endl;

    // Check if we've already visited this asset (cycle detection)
    if (visited_assets.find(asset_id) != visited_assets.end())
    {
        std::cout << "  Already visited " << asset_name << ", skipping to avoid circular reference" << std::endl;
        return;
    }

    // Mark as visited
    visited_assets.insert(asset_id);

    // Lookup the AAS shell ID from the asset ID
    auto aas_id_opt = aas_client_->lookupAasIdFromAssetId(asset_id);
    if (!aas_id_opt.has_value())
    {
        std::cerr << "Could not find AAS shell for asset: " << asset_id << std::endl;
        return;
    }

    std::string aas_shell_id = aas_id_opt.value();

    // Add this asset to the mapping using the AAS shell ID
    {
        std::lock_guard<std::mutex> lock(equipment_mapping_mutex_);
        equipment_aas_mapping_[asset_name] = aas_shell_id;
    }

    // Fetch the HierarchicalStructures submodel using the AAS shell ID
    auto hierarchy_opt = aas_client_->fetchHierarchicalStructure(aas_shell_id);
    if (!hierarchy_opt.has_value())
    {
        std::cout << "No hierarchical structure found for " << asset_name << std::endl;
        return;
    }

    const auto &hierarchy = hierarchy_opt.value();

    // Check the archetype to determine traversal direction
    std::string archetype = getArchetype(hierarchy);
    std::cout << "  Archetype: " << (archetype.empty() ? "(not specified)" : archetype) << std::endl;

    // If archetype is "OneUp", this entity points upward in hierarchy
    // We should NOT traverse its children as they point back to parents
    if (archetype == "OneUp")
    {
        std::cout << "  Archetype is OneUp, skipping child traversal (points to parent)" << std::endl;
        return;
    }

    // Look for submodel elements
    if (!hierarchy.contains("submodelElements") || !hierarchy["submodelElements"].is_array())
    {
        std::cout << "No submodelElements in HierarchicalStructures for " << asset_name << std::endl;
        return;
    }

    // Find the EntryNode entity which contains the children
    nlohmann::json entry_node;
    bool found_entry_node = false;

    for (const auto &element : hierarchy["submodelElements"])
    {
        if (element.contains("idShort") && element["idShort"].get<std::string>() == "EntryNode" &&
            element.contains("modelType") && element["modelType"].get<std::string>() == "Entity")
        {
            entry_node = element;
            found_entry_node = true;
            break;
        }
    }

    if (!found_entry_node)
    {
        std::cout << "No EntryNode found in HierarchicalStructures for " << asset_name << std::endl;
        return;
    }

    // Check if EntryNode has statements (children)
    if (!entry_node.contains("statements") || !entry_node["statements"].is_array())
    {
        std::cout << "No statements in EntryNode for " << asset_name << std::endl;
        return;
    }

    // Iterate through statements to find child entities
    for (const auto &statement : entry_node["statements"])
    {
        // Look for Entity elements (not RelationshipElement, not SubmodelElementCollection)
        if (!statement.contains("modelType") || statement["modelType"].get<std::string>() != "Entity")
        {
            continue;
        }

        // Skip if it doesn't have the required fields
        if (!statement.contains("idShort") || !statement.contains("globalAssetId"))
        {
            continue;
        }

        std::string child_name = statement["idShort"].get<std::string>();
        std::string child_global_asset_id = statement["globalAssetId"].get<std::string>();

        std::cout << "  Found child: " << child_name << " -> " << child_global_asset_id << std::endl;

        // Recursively resolve this child's hierarchy
        // Pass the visited set to detect cycles
        recursivelyResolveHierarchy(child_global_asset_id, child_name, visited_assets);
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
    // Simple name -> AAS URL (e.g., "LoadingSystem" -> "https://.../imaLoadingSystem")
    for (const auto &[equipment_name, aas_id] : equipment_aas_mapping_)
    {
        blackboard->set(equipment_name, aas_id);
        std::cout << "  Set blackboard[" << equipment_name << "] = " << aas_id << std::endl;
    }

    std::cout << "Blackboard populated with " << equipment_aas_mapping_.size() << " equipment entries" << std::endl;
}

bool BehaviorTreeController::registerNodesWithAASConfig()
{
    try
    {
        // Register all nodes (they will read equipment mapping from blackboard)
        nlohmann::json empty_config = nlohmann::json::object();
        registerAllNodes(*bt_factory_, *node_message_distributor_, *mqtt_client_,
                         *aas_client_, empty_config);

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
        app_params_.aasRegistryUrl,
        app_params_.groot2_port,
        app_params_.bt_description_path,
        app_params_.bt_nodes_path,
        app_params_.asset_ids_to_resolve);

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
    std::string state_schema_url = "https://aausmartproductionlab.github.io/AP2030-UNS/schemas/state.schema.json";

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
            if (!this->sigint_received_.load())
            {
                // Only allow start if nodes are registered
                if (!this->nodes_registered_.load())
                {
                    std::cerr << "Cannot start: Nodes not registered yet!" << std::endl;
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
    mqtt_client_->subscribe_topic(app_params_.halt_topic, 2);

    std::cout << "MQTT control interface initialized." << std::endl;

    // Fetch equipment mapping from AAS hierarchical structure
    std::cout << "Fetching production line structure from AAS..." << std::endl;
    if (fetchAndBuildEquipmentMapping())
    {
        std::cout << "Equipment mapping successfully built from AAS" << std::endl;

        // Register nodes with the equipment mapping
        if (registerNodesWithAASConfig())
        {
            std::cout << "Nodes successfully registered with AAS configuration." << std::endl;
            nodes_registered_ = true;
        }
        else
        {
            std::cerr << "Failed to register nodes with AAS configuration!" << std::endl;
            nodes_registered_ = false;
        }
    }
    else
    {
        std::cerr << "Failed to fetch equipment mapping from AAS!" << std::endl;
        std::cerr << "Cannot continue without equipment configuration." << std::endl;
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
                fetchAndBuildEquipmentMapping();
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

void BehaviorTreeController::processBehaviorTreeStart()
{
    if (current_packml_state_ == PackML::State::EXECUTE)
    {
        return;
    }

    // Check if nodes are registered
    if (!nodes_registered_.load())
    {
        std::cerr << "Cannot start behavior tree: Nodes not registered!" << std::endl;
        mqtt_start_bt_flag_ = false;
        return;
    }

    if (current_packml_state_ == PackML::State::SUSPENDED && bt_tree_.rootNode())
    {
        std::cout << "Resuming suspended behavior tree." << std::endl;
        if (mqtt_client_)
        {
            mqtt_client_->set_message_handler(main_mqtt_message_handler_);
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
            bt_factory_->registerBehaviorTreeFromFile(app_params_.bt_description_path);

            // Create blackboard and populate it BEFORE creating the tree
            // This ensures nodes can access equipment mapping during initialization
            auto root_blackboard = BT::Blackboard::create();
            populateBlackboard(root_blackboard);

            bt_tree_ = bt_factory_->createTree("MainTree", root_blackboard);
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
            mqtt_client_->set_message_handler(main_mqtt_message_handler_);
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
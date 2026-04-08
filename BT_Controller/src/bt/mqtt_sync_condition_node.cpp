#include "bt/mqtt_sync_condition_node.h"
#include "mqtt/node_message_distributor.h"
#include "aas/aas_interface_cache.h"
#include <iostream>
#include <thread>
#include <chrono>

MqttSyncConditionNode::MqttSyncConditionNode(
    const std::string &name,
    const BT::NodeConfig &config,
    MqttClient &mqtt_client,
    AASClient &aas_client)
    : BT::ConditionNode(name, config),
      MqttSubBase(mqtt_client),
      aas_client_(aas_client)
{
}

void MqttSyncConditionNode::initialize()
{
    // Call the virtual function - safe because construction is complete
    initializeTopicsFromAAS();

    // Only register if we have topics initialized
    if (topics_initialized_ && MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

MqttSyncConditionNode::~MqttSyncConditionNode()
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->unregisterInstance(this);
    }
}

void MqttSyncConditionNode::initializeTopicsFromAAS()
{
    // Already initialized, skip
    if (topics_initialized_)
    {
        return;
    }

    try
    {
        auto asset_input = getInput<std::string>("Asset");
        if (!asset_input.has_value())
        {
            std::cerr << "Node '" << this->name() << "' has no Asset input configured" << std::endl;
            return;
        }

        std::string asset_name = asset_input.value();
        std::cout << "Node '" << this->name() << "' initializing for Asset: " << asset_name << std::endl;

        // Check if already a full URL (starts with https:// or http://)
        std::string asset_id = asset_name;

        // First, try to use the cached interface (fast path)
        auto cache = MqttSubBase::getAASInterfaceCache();
        if (cache)
        {
            auto cached_interface = cache->getInterface(asset_id, this->name(), "output");
            if (cached_interface.has_value())
            {
                std::cout << "Node '" << this->name() << "' using cached interface" << std::endl;
                MqttSubBase::setTopic("output", cached_interface.value());
                topics_initialized_ = true;
                return;
            }
        }

        // Fall back to direct AAS query (slow path)
        std::cout << "Node '" << this->name() << "' falling back to direct AAS query" << std::endl;
        auto response_opt = aas_client_.fetchInterface(asset_id, this->name(), "output");

        if (!response_opt.has_value())
        {
            std::cerr << "Failed to fetch interface from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttSubBase::setTopic("output", response_opt.value());
        topics_initialized_ = true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

bool MqttSyncConditionNode::ensureInitialized()
{
    if (topics_initialized_)
    {
        return true;
    }

    // Try lazy initialization
    std::cout << "[MqttSyncConditionNode] Node '" << this->name() << "' attempting lazy initialization..." << std::endl;
    initializeTopicsFromAAS();

    if (topics_initialized_ && MqttSubBase::node_message_distributor_)
    {
        // Use registerLateInitializingNode to subscribe to specific topics
        // This triggers the broker to resend retained messages
        std::cout << "[MqttSyncConditionNode] Node '" << this->name() << "' registering for late subscription..." << std::endl;
        auto start_time = std::chrono::steady_clock::now();
        
        bool success = MqttSubBase::node_message_distributor_->registerLateInitializingNode(this);
        
        auto sub_time = std::chrono::steady_clock::now();
        auto sub_ms = std::chrono::duration_cast<std::chrono::milliseconds>(sub_time - start_time).count();
        
        if (success)
        {
            std::cout << "[MqttSyncConditionNode] Node '" << this->name() 
                      << "' lazy initialized and subscribed successfully (took " << sub_ms << "ms)" << std::endl;

            // Wait briefly for retained messages to arrive after subscription
            // The MQTT broker sends retained messages asynchronously after subscription completes,
            // so we need a small delay to allow them to be delivered before the first tick
            std::cout << "[MqttSyncConditionNode] Node '" << this->name() 
                      << "' waiting 50ms for retained messages..." << std::endl;
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            std::cout << "[MqttSyncConditionNode] Node '" << this->name() 
                      << "' wait complete, returning from ensureInitialized()" << std::endl;
        }
        else
        {
            std::cerr << "[MqttSyncConditionNode] Node '" << this->name() << "' lazy init: subscription failed" << std::endl;
        }
    }
    else if (!topics_initialized_)
    {
        std::cerr << "[MqttSyncConditionNode] Node '" << this->name() << "' lazy initialization FAILED - topics not configured" << std::endl;
    }

    return topics_initialized_;
}

BT::PortsList MqttSyncConditionNode::providedPorts()
{
    return {};
}

void MqttSyncConditionNode::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(mutex_);
    latest_msg_ = msg;
    std::cout << "Sync subscription node received message" << std::endl;
}

BT::NodeStatus MqttSyncConditionNode::tick()
{
    // Ensure lazy initialization is done
    if (!ensureInitialized())
    {
        auto asset = getInput<std::string>("Asset");
        std::cerr << "Node '" << this->name() << "' FAILED - could not initialize. "
                  << "Asset=" << (asset.has_value() ? asset.value() : "<not set>") << std::endl;
        return BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::SUCCESS; // Default implementation
}

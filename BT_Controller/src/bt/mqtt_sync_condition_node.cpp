#include "bt/mqtt_sync_condition_node.h"
#include "mqtt/node_message_distributor.h"
#include <iostream>

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

        // Create Topic objects
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
    initializeTopicsFromAAS();

    if (topics_initialized_ && MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        std::cout << "Node '" << this->name() << "' lazy initialized successfully" << std::endl;
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
        std::cerr << "Node '" << this->name() << "' could not be initialized, returning FAILURE" << std::endl;
        return BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::SUCCESS; // Default implementation
}

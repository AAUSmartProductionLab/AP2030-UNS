#include <behaviortree_cpp/bt_factory.h>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <nlohmann/json.hpp>
#include "bt/mqtt_sync_action_node.h"
#include "aas/aas_client.h"

MqttSyncActionNode::MqttSyncActionNode(
    const std::string &name,
    const BT::NodeConfig &config,
    MqttClient &mqtt_client,
    AASClient &aas_client)
    : BT::SyncActionNode(name, config),
      MqttPubBase(mqtt_client),
      MqttSubBase(mqtt_client),
      aas_client_(aas_client)
{
}

void MqttSyncActionNode::initialize()
{
    // Call the virtual function - safe because construction is complete
    initializeTopicsFromAAS();

    // Only register if we have topics initialized
    if (topics_initialized_ && MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

MqttSyncActionNode::~MqttSyncActionNode()
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->unregisterInstance(this);
    }
}

json MqttSyncActionNode::createMessage()
{
    // Default implementation
    json message;

    message["Uuid"] = current_uuid_;
    message["TimeStamp"] = bt_utils::getCurrentTimestampISO();
    return message;
}

BT::NodeStatus MqttSyncActionNode::tick()
{
    // Ensure lazy initialization is done
    if (!ensureInitialized())
    {
        std::cerr << "Node '" << this->name() << "' could not be initialized, returning FAILURE" << std::endl;
        return BT::NodeStatus::FAILURE;
    }
    publish("input", createMessage());
    return BT::NodeStatus::SUCCESS;
}

BT::PortsList MqttSyncActionNode::providedPorts()
{
    return {};
}

void MqttSyncActionNode::initializeTopicsFromAAS()
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
        auto request_opt = aas_client_.fetchInterface(asset_id, this->name(), "input");
        auto response_opt = aas_client_.fetchInterface(asset_id, this->name(), "output");

        if (!request_opt.has_value() || !response_opt.has_value())
        {
            std::cerr << "Failed to fetch interfaces from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttPubBase::setTopic("input", request_opt.value());
        MqttSubBase::setTopic("output", response_opt.value());
        topics_initialized_ = true;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

bool MqttSyncActionNode::ensureInitialized()
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

// Standard implementation based on PackML override this if needed
void MqttSyncActionNode::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::cout << "Callback received for topic key: " << topic_key << std::endl;
        setStatus(BT::NodeStatus::SUCCESS);
    }
}
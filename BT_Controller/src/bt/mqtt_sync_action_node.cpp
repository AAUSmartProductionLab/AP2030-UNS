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

    if (MqttSubBase::node_message_distributor_)
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
    publish("input", createMessage());
    return BT::NodeStatus::SUCCESS;
}

BT::PortsList MqttSyncActionNode::providedPorts()
{
    return {};
}

void MqttSyncActionNode::initializeTopicsFromAAS()
{
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

        std::string asset_id = aas_client_.getInstanceNameByAssetName(asset_name);
        std::cout << "Initializing MQTT topics for asset ID: " << asset_id << std::endl;

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
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
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
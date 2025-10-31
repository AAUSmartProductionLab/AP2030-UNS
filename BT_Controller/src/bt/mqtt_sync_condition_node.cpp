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

    if (MqttSubBase::node_message_distributor_)
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
    try
    {
        std::string asset_id = aas_client_.getInstanceNameByAssetName(getInput<std::string>("Asset").value());
        // Create Topic objects
        mqtt_utils::Topic response_topic = aas_client_.fetchInterface(asset_id, this->name(), "response").value();
        MqttSubBase::setTopic("response", response_topic);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
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
    return BT::NodeStatus::SUCCESS; // Default implementation
}

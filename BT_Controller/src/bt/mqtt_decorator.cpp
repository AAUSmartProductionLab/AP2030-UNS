
#include "bt/mqtt_decorator.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
#include <utils.h>

MqttDecorator::MqttDecorator(
    const std::string &name,
    const BT::NodeConfig &config,
    MqttClient &mqtt_client,
    AASClient &aas_client)
    : DecoratorNode(name, config),
      MqttPubBase(mqtt_client),
      MqttSubBase(mqtt_client),
      aas_client_(aas_client)
{
}

void MqttDecorator::initialize()
{
    // Call the virtual function - safe because construction is complete
    initializeTopicsFromAAS();

    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
    }
}

MqttDecorator::~MqttDecorator()
{
    if (MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->unregisterInstance(this);
    }
}

void MqttDecorator::initializeTopicsFromAAS()
{
    try
    {
        std::string asset_id = aas_client_.getInstanceNameByAssetName(getInput<std::string>("Asset").value());
        // Create Topic objects
        mqtt_utils::Topic request = aas_client_.fetchInterface(asset_id, this->name(), "request").value();
        mqtt_utils::Topic response = aas_client_.fetchInterface(asset_id, this->name(), "response").value();

        MqttPubBase::setTopic("request", request);
        MqttSubBase::setTopic("response", response);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

void MqttDecorator::halt()
{
    DecoratorNode::halt();
}

BT::PortsList MqttDecorator::providedPorts()
{
    return {
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INPUT,
            "Asset",
            "{Asset}",
            "The asset to register with"),
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INOUT,
            "Uuid",
            "{Uuid}",
            "UUID Used for registration")};
}

void MqttDecorator::callback(const std::string &topic_key, const nlohmann::json &msg, mqtt::properties props)
{
    // Use mutex to protect shared state
    {
        std::cout << "Callback of Base class used" << std::endl;
    }
}

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

    // Only register if we have topics initialized
    if (topics_initialized_ && MqttSubBase::node_message_distributor_)
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

        std::string asset_id = asset_input.value();
        std::cout << "Node '" << this->name() << "' initializing for Asset: " << asset_id << std::endl;

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

bool MqttDecorator::ensureInitialized()
{
    if (topics_initialized_)
    {
        return true;
    }

    // Try lazy initialization
    std::cout << "Node '" << this->name() << "' attempting lazy initialization..." << std::endl;
    initializeTopicsFromAAS();

    if (topics_initialized_ && MqttSubBase::node_message_distributor_)
    {
        MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        std::cout << "Node '" << this->name() << "' lazy initialized successfully" << std::endl;
    }
    else if (!topics_initialized_)
    {
        std::cerr << "Node '" << this->name() << "' lazy initialization FAILED - topics not configured" << std::endl;
    }

    return topics_initialized_;
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
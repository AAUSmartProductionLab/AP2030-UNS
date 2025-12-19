#include "bt/decorators/occupy.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
#include <utils.h>

void Occupy::initializeTopicsFromAAS()
{
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
        auto register_opt = aas_client_.fetchInterface(asset_id, "occupy", "input");
        auto register_response_opt = aas_client_.fetchInterface(asset_id, "occupy", "output");

        auto unregister_opt = aas_client_.fetchInterface(asset_id, "release", "input");
        auto unregister_response_opt = aas_client_.fetchInterface(asset_id, "release", "output");

        if (!register_opt.has_value() || !unregister_opt.has_value() ||
            !register_response_opt.has_value() || !unregister_response_opt.has_value())
        {
            std::cerr << "Failed to fetch interfaces from AAS for node: " << this->name() << std::endl;
            return;
        }

        MqttPubBase::setTopic("occupyRequest", register_opt.value());
        MqttPubBase::setTopic("releaseRequest", unregister_opt.value());
        MqttSubBase::setTopic("occupyResponse", register_response_opt.value());
        MqttSubBase::setTopic("releaseResponse", unregister_response_opt.value());
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

BT::NodeStatus Occupy::tick()
{
    if (status() == BT::NodeStatus::IDLE)
    {
        current_phase_ = PackML::State::STARTING;
        sendRegisterCommand();
        return BT::NodeStatus::RUNNING;
    }
    if (current_phase_ == PackML::State::EXECUTE)
    {
        BT::NodeStatus child_state = child_node_->executeTick();
        if (child_state == BT::NodeStatus::FAILURE)
        {
            current_phase_ = PackML::State::STOPPING;
            sendUnregisterCommand();
            return BT::NodeStatus::RUNNING;
        }
        else if (child_state == BT::NodeStatus::SUCCESS)
        {
            resetChild();
            current_phase_ = PackML::State::COMPLETING;
            sendUnregisterCommand();
            return BT::NodeStatus::RUNNING;
        }
    }
    // The node should forward the states of its child nodes upwards after it has executed the command to unregister
    else if (current_phase_ == PackML::State::STOPPED)
    {
        current_phase_ = PackML::State::IDLE;
        return BT::NodeStatus::FAILURE;
    }
    else if (current_phase_ == PackML::State::COMPLETE)
    {
        current_phase_ = PackML::State::IDLE;
        return BT::NodeStatus::SUCCESS;
    }
    return BT::NodeStatus::RUNNING;
}

void Occupy::halt()
{
    BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
    if (uuid.has_value())
    {
        current_uuid_ = uuid.value();
    }
    // Only send unregister if topics were initialized
    if (MqttPubBase::topics_.find("releaseRequest") != MqttPubBase::topics_.end())
    {
        sendUnregisterCommand();
    }
    DecoratorNode::halt();
}

void Occupy::sendRegisterCommand()
{
    json message;
    BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
    if (uuid && uuid.has_value() && !uuid.value().empty())
    {
        current_uuid_ = uuid.value();
    }
    else
    {
        current_uuid_ = mqtt_utils::generate_uuid();
        setOutput("Uuid", current_uuid_);
    }
    message["Uuid"] = current_uuid_;
    MqttPubBase::publish("occupyRequest", message);
}
void Occupy::sendUnregisterCommand()
{
    json message;
    message["Uuid"] = current_uuid_;
    MqttPubBase::publish("releaseRequest", message);
}

void Occupy::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(mutex_);

    if (status() == BT::NodeStatus::RUNNING && msg.at("Uuid") == current_uuid_)
    {
        std::string state = msg.at("State");
        if (topic_key == "occupyResponse")
        {
            if (msg.at("State") == "SUCCESS")
            {
                current_phase_ = PackML::State::EXECUTE;
            }
            else if (msg.at("State") == "FAILURE")
            {
                current_phase_ = PackML::State::STOPPED;
            }
        }
        else if (topic_key == "releaseResponse")
        {
            if (msg.at("State") == "SUCCESS")
            {
                if (current_phase_ == PackML::State::COMPLETING)
                {
                    current_phase_ = PackML::State::COMPLETE;
                }
                else if (current_phase_ == PackML::State::STOPPING)
                {
                    current_phase_ = PackML::State::STOPPED;
                }
            }
            else if (msg.at("State") == "FAILURE")
            {
                current_phase_ = PackML::State::STOPPED;
            }
        }
        emitWakeUpSignal();
    }
}

BT::PortsList Occupy::providedPorts()
{
    return {
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INPUT,
            "Asset",
            "{Asset}",
            "The Asset to register with"),
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INOUT,
            "Uuid",
            "{Uuid}",
            "UUID Used for registration")};
}
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
        std::string asset_id = station_config_.at(getInput<std::string>("Station").value()); // Check action:asset association in json message
        // Create Topic objects
        mqtt_utils::Topic raw_register_topic = aas_client_.fetchInterface(asset_id, this->name(), "register").value();
        mqtt_utils::Topic raw_unregister_topic = aas_client_.fetchInterface(asset_id, this->name(), "unregister").value();
        mqtt_utils::Topic raw_register_response_topic = aas_client_.fetchInterface(asset_id, this->name(), "register_response").value();
        mqtt_utils::Topic raw_unregister_response_topic = aas_client_.fetchInterface(asset_id, this->name(), "unregister_response").value();

        MqttPubBase::setTopic("register", raw_register_topic);
        MqttPubBase::setTopic("unregister", raw_unregister_topic);
        MqttSubBase::setTopic("register_response", raw_register_response_topic);
        MqttSubBase::setTopic("unregister_response", raw_unregister_response_topic);
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
    sendUnregisterCommand();
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
    MqttPubBase::publish("register", message);
}
void Occupy::sendUnregisterCommand()
{
    json message;
    message["Uuid"] = current_uuid_;
    MqttPubBase::publish("unregister", message);
}

void Occupy::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(mutex_);

    if (status() == BT::NodeStatus::RUNNING && msg.at("Uuid") == current_uuid_)
    {
        std::string state = msg.at("State");
        if (topic_key == "register_response")
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
        else if (topic_key == "unregister_response")
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
            "Station",
            "{Station}",
            "The station to register with"),
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INOUT,
            "Uuid",
            "{Uuid}",
            "UUID Used for registration")};
}
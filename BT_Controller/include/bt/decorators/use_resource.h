#pragma once

#include "bt/mqtt_async_sub_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
#include <utils.h>
class MqttClient;
using nlohmann::json;

class UseResource : public BT::DecoratorNode, public MqttPubBase, public MqttSubBase
{
private:
    std::string current_uuid_;
    std::mutex mutex_;

    PackML::State current_phase_ = PackML::State::IDLE;

public:
    UseResource(const std::string &name,
                const BT::NodeConfig &config,
                MqttClient &mqtt_client,
                const mqtt_utils::Topic &raw_register_topic,
                const mqtt_utils::Topic &raw_unregister_topic,
                // Topics for MqttSubBase
                const mqtt_utils::Topic &raw_register_response_topic,
                const mqtt_utils::Topic &raw_unregister_response_topic)
        : DecoratorNode(name, config),
          MqttPubBase(mqtt_client, {{"register", raw_register_topic},
                                    {"unregister", raw_unregister_topic}}),
          MqttSubBase(mqtt_client, {{"register_response", raw_register_response_topic},
                                    {"unregister_response", raw_unregister_response_topic}})
    {
        for (auto &[key, topic_obj] : MqttPubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern(), key));
        }
        // For SubBase topics
        for (auto &[key, topic_obj] : MqttSubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern(), key));
        }

        // Register with message distributor
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }

    ~UseResource()
    {
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->unregisterInstance(this);
        }
    }

    std::string getFormattedTopic(const std::string &pattern_to_format, const std::string &topic_key)
    {
        std::vector<std::string> replacements;
        BT::Expected<std::string> station = getInput<std::string>("Station");
        if (!station.has_value())
        {
            return pattern_to_format;
        }
        replacements.push_back(station.value());
        if (topic_key == "register_response")
        {
            replacements.push_back("Register");
        }
        else if (topic_key == "unregister_response")
        {
            replacements.push_back("Unregister");
        }
        std::string formatted = mqtt_utils::formatWildcardTopic(pattern_to_format, replacements);
        return formatted;
    }

    BT::NodeStatus tick() override
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

    void halt()
    {
        BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
        if (uuid.has_value())
        {
            current_uuid_ = uuid.value();
        }
        sendUnregisterCommand();
        DecoratorNode::halt();
    }

    void sendRegisterCommand()
    {
        json message;
        BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
        BT::Expected<int> context = getInput<int>("Context");
        if (uuid && uuid.has_value() && !uuid.value().empty())
        {
            current_uuid_ = uuid.value();
        }
        else
        {
            current_uuid_ = mqtt_utils::generate_uuid();
            setOutput("Uuid", current_uuid_);
        }
        if (context && context.has_value() && context.value() >= 0)
        {
            message["Context"] = context.value();
        }
        message["Uuid"] = current_uuid_;
        MqttPubBase::publish("register", message);
    }
    void sendUnregisterCommand()
    {
        json message;
        message["Uuid"] = current_uuid_;
        MqttPubBase::publish("unregister", message);
    }

    void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override
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

    static BT::PortsList providedPorts()
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
                "UUID Used for registration"),
            BT::details::PortWithDefault<int>(
                BT::PortDirection::INPUT,
                "Context",
                -1,
                "The Context on how the station should be used")};
    }

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        MqttClient &mqtt_client,
        const std::string &node_name,
        // Pass the four topic patterns required by UseStation constructor
        const mqtt_utils::Topic &register_topic_pattern,
        const mqtt_utils::Topic &unregister_topic_pattern,
        const mqtt_utils::Topic &register_response_topic_pattern,
        const mqtt_utils::Topic &unregister_response_topic_pattern)
    {
        auto mqtt_client_ptr = &mqtt_client; // Ensure lifetime management if necessary

        factory.registerBuilder<DerivedNode>( // Typically DerivedNode would be UseStation itself or a derived class
            node_name,
            [mqtt_client_ptr,
             register_topic_pattern,
             unregister_topic_pattern,
             register_response_topic_pattern,
             unregister_response_topic_pattern](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>( // Or std::make_unique<UseStation> if DerivedNode is fixed
                    name, config, *mqtt_client_ptr,
                    register_topic_pattern,
                    unregister_topic_pattern,
                    register_response_topic_pattern,
                    unregister_response_topic_pattern);
            });
    }

    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};
#pragma once

#include "bt/mqtt_async_sub_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
class MqttClient;
using nlohmann::json;

class UseStation : public BT::DecoratorNode, public MqttPubBase, public MqttSubBase
{
private:
    std::string current_uuid_;
    std::mutex mutex_;

    // State tracking using a single enum
    enum class Phase
    {
        REGISTERING, // Waiting for EXECUTE state
        EXECUTING,   // Child is running
        COMPLETING,
        COMPLETE // Waiting for COMPLETE confirmation
    };

    Phase current_phase_ = Phase::REGISTERING;

public:
    UseStation(const std::string &name,
               const BT::NodeConfig &config,
               MqttClient &mqtt_client,
               const mqtt_utils::Topic &start_topic,
               const mqtt_utils::Topic &complete_topic,
               const mqtt_utils::Topic &response_topic)
        : DecoratorNode(name, config),
          MqttPubBase(mqtt_client, start_topic, complete_topic),
          MqttSubBase(mqtt_client, response_topic)
    {
        // Format all topic patterns with station ID
        response_topic_.setTopic(getFormattedTopic(response_topic_.getPattern(), config));
        request_topic_.setTopic(getFormattedTopic(request_topic_.getPattern(), config));
        halt_topic_.setTopic(getFormattedTopic(halt_topic_.getPattern(), config));

        // Register with message distributor
        if (MqttSubBase::node_message_distributor_)
        {
            MqttSubBase::node_message_distributor_->registerDerivedInstance(this);
        }
    }

    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
    {
        BT::Expected<std::string> station = getInput<std::string>("Station");
        if (station.has_value())
        {
            std::string formatted = mqtt_utils::formatWildcardTopic(pattern, station.value());
            return formatted;
        }
        return pattern;
    }

    BT::NodeStatus tick() override
    {
        Phase current_phase;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            current_phase = current_phase_;
        }

        if (status() == BT::NodeStatus::IDLE)
        {
            BT::Expected<std::string> uuid = getInput<std::string>("Uuid");
            if (uuid.has_value())
            {
                current_uuid_ = uuid.value();
            }
            setStatus(BT::NodeStatus::RUNNING);

            std::lock_guard<std::mutex> lock(mutex_);
            current_phase_ = Phase::REGISTERING;
            sendStartCommand();
            return BT::NodeStatus::RUNNING;
        }

        // Only tick child if we've confirmed we're in EXECUTE state
        if (current_phase == Phase::EXECUTING)
        {
            BT::NodeStatus child_state = child_node_->executeTick();
            if (isStatusCompleted(child_state))
            {
                resetChild();

                std::lock_guard<std::mutex> lock(mutex_);
                current_phase_ = Phase::COMPLETING;
                sendCompleteCommand();
                return BT::NodeStatus::RUNNING; // Keep running until COMPLETE is confirmed
            }
        }

        if (current_phase == Phase::COMPLETE)
        {
            return BT::NodeStatus::SUCCESS;
        }

        return BT::NodeStatus::RUNNING;
    }

    void halt()
    {
        sendCompleteCommand();
        DecoratorNode::halt();
    }

    void sendStartCommand()
    {
        json message;
        message["Uuid"] = current_uuid_;
        publish(message);
    }
    void sendCompleteCommand()
    {
        json message;
        message["Uuid"] = current_uuid_;
        publishHalt(message);
    }

    void callback(const json &msg, mqtt::properties props) override
    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Handle both start and complete responses
        if (status() == BT::NodeStatus::RUNNING)
        {
            // Check if our UUID is in the process queue
            if (!msg["ProcessQueue"].empty())
            {
                std::string first_uuid = msg["ProcessQueue"][0];
                if (first_uuid == current_uuid_)
                {
                    if (msg["State"] == "STOPPING")
                    {
                        setStatus(BT::NodeStatus::FAILURE);
                    }
                    else if (msg["State"] == "EXECUTE" && current_phase_ == Phase::REGISTERING)
                    {
                        current_phase_ = Phase::EXECUTING;
                    }
                    else if (msg["State"] == "COMPLETING" && current_phase_ == Phase::COMPLETING)
                    {
                        current_phase_ = Phase::COMPLETE;
                    }
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
                BT::PortDirection::INPUT,
                "Uuid",
                "{ID}",
                "UUID Used for registration")};
    }

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        MqttClient &mqtt_client,
        const std::string &node_name,
        const mqtt_utils::Topic &start_topic,
        const mqtt_utils::Topic &complete_topic,
        const mqtt_utils::Topic &response_topic)
    {
        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr = &mqtt_client,
             start_topic,
             complete_topic,
             response_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name, config, *mqtt_client_ptr,
                    start_topic, complete_topic, response_topic);
            });
    }
    virtual std::string getBTNodeName() const override
    {
        return this->name();
    };
};
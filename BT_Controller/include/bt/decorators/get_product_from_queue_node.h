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

class GetProductFromQueue : public BT::DecoratorNode, public MqttPubBase // Assuming no MqttSubBase here
{
private:
    bool child_running_ = false;
    BT::SharedQueue<std::string> queue_;

public:
    GetProductFromQueue(const std::string &name,
                        const BT::NodeConfig &config,
                        MqttClient &mqtt_client,
                        const mqtt_utils::Topic &request_topic) // This is a pattern
        : BT::DecoratorNode(name, config),
          MqttPubBase(mqtt_client, {{"request", request_topic}}) // Pass as a map
    {
        for (auto &[key, topic_obj] : MqttPubBase::topics_)
        {
            topic_obj.setTopic(getFormattedTopic(topic_obj.getPattern(), config));
        }
    }
    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
    {
        BT::Expected<std::string> id = config.blackboard->get<std::string>("XbotTopic"); // hacky way of getting the ID from the subtree parameter
        if (id.has_value())
        {
            std::string formatted = mqtt_utils::formatWildcardTopic(pattern, id.value());
            return formatted;
        }
        return pattern;
    }

    BT::NodeStatus tick() override
    {
        bool popped = false;
        if (status() == BT::NodeStatus::IDLE)
        {
            child_running_ = false;

            // Always get a fresh queue reference when starting from IDLE
            BT::AnyPtrLocked any_ref = getLockedPortContent("Queue");
            if (any_ref)
            {
                queue_ = any_ref.get()->cast<BT::SharedQueue<std::string>>();
            }
        }

        if (!child_running_)
        {
            if (queue_ && !queue_->empty())
            {
                auto value = std::move(queue_->front());
                queue_->pop_front();
                popped = true;

                // Publish the product ID to the MQTT topic
                json message;
                message["ProductId"] = value;
                auto now = std::chrono::system_clock::now();
                message["TimeStamp"] = fmt::format("{:%FT%T}Z",
                                                   std::chrono::floor<std::chrono::milliseconds>(now));
                MqttPubBase::publish("request", message); // Use the "request" key

                setOutput("ProductID", value);
            }
        }

        if (!popped && !child_running_)
        {
            return getInput<BT::NodeStatus>("if_empty").value();
        }

        if (status() == BT::NodeStatus::IDLE)
        {
            setStatus(BT::NodeStatus::RUNNING);
        }

        BT::NodeStatus child_state = child_node_->executeTick();
        child_running_ = (child_state == BT::NodeStatus::RUNNING);

        if (isStatusCompleted(child_state))
        {
            resetChild();
        }

        if (child_state == BT::NodeStatus::FAILURE)
        {
            return BT::NodeStatus::FAILURE;
        }
        return BT::NodeStatus::RUNNING;
    }

    static BT::PortsList providedPorts()
    {
        // we mark "Queue" as BidirectionalPort, because the original element is modified
        return {
            BT::details::PortWithDefault<BT::SharedQueue<std::string>>(
                BT::PortDirection::INPUT,
                "Queue",
                "{ProductIDs}",
                "The queue of all product IDs of the batch"),
            BT::InputPort<BT::NodeStatus>("if_empty", BT::NodeStatus::SUCCESS,
                                          "Status to return if queue is empty: "
                                          "SUCCESS, FAILURE, SKIPPED"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::OUTPUT,
                "ProductID",
                "{ProductID}",
                "The product ID of the current product")};
    }

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        MqttClient &mqtt_client,
        const std::string &node_name,
        const mqtt_utils::Topic &request_topic)
    {
        factory.registerBuilder<DerivedNode>(
            node_name,
            [mqtt_client_ptr = &mqtt_client,
             request_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name, config, *mqtt_client_ptr,
                    request_topic);
            });
    }
};
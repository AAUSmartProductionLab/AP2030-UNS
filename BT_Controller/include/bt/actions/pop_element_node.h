#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <nlohmann/json.hpp>
#include <fmt/chrono.h>
#include <chrono>

// Forward declaration
class MqttClient;

using nlohmann::json;

class PopElementNode : public BT::SyncActionNode, public MqttPubBase
{
public:
    PopElementNode(const std::string &name,
                   const BT::NodeConfig &config,
                   MqttClient &mqtt_client,
                   const mqtt_utils::Topic &request_topic)
        : BT::SyncActionNode(name, config),
          MqttPubBase(mqtt_client, request_topic)
    {
        request_topic_.setTopic(getFormattedTopic(request_topic_.getPattern(), config));
    }

    std::string getFormattedTopic(const std::string &pattern, const BT::NodeConfig &config)
    {
        BT::Expected<std::string> id = config.blackboard->get<std::string>("XbotTopic");
        if (id.has_value())
        {
            std::string formatted = mqtt_utils::formatWildcardTopic(pattern, id.value());
            return formatted;
        }
        return pattern;
    }

    BT::NodeStatus tick() override
    {
        std::string product_id_to_publish;
        BT::NodeStatus status_if_queue_empty_or_invalid = getInput<BT::NodeStatus>("if_empty").value_or(BT::NodeStatus::FAILURE);
        {
            BT::AnyPtrLocked any_ref = getLockedPortContent("Queue");

            if (!any_ref)
            {
                return status_if_queue_empty_or_invalid;
            }

            BT::Expected<BT::SharedQueue<std::string>> queue_expected = any_ref.get()->cast<BT::SharedQueue<std::string>>();
            if (!queue_expected)
            {
                return status_if_queue_empty_or_invalid;
            }

            BT::SharedQueue<std::string> queue_ptr = queue_expected.value();
            if (!queue_ptr) // Check if the shared_ptr itself is null
            {
                return status_if_queue_empty_or_invalid;
            }

            if (queue_ptr->empty())
            {
                return status_if_queue_empty_or_invalid;
            }

            product_id_to_publish = std::move(queue_ptr->front());
            queue_ptr->pop_front();
        }

        json message;
        message["ProductId"] = product_id_to_publish;
        auto now = std::chrono::system_clock::now();
        message["TimeStamp"] = fmt::format("{:%FT%T}Z",
                                           std::chrono::floor<std::chrono::milliseconds>(now));
        publish(message);

        setOutput("ProductID", product_id_to_publish);
        return BT::NodeStatus::SUCCESS;
    }

    static BT::PortsList providedPorts()
    {
        return {
            BT::InputPort<BT::SharedQueue<std::string>>(
                "Queue",
                "{ProductIDs}",
                "The shared queue of product IDs. An element will be popped from it."),
            BT::InputPort<BT::NodeStatus>("if_empty", BT::NodeStatus::SUCCESS,
                                          "Status to return if the queue is empty or invalid (SUCCESS, FAILURE, SKIPPED)."),
            BT::OutputPort<std::string>(
                "ProductID",
                "{ProductID}",
                "The product ID popped from the queue.")};
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
             request_topic_copy = request_topic](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(
                    name, config, *mqtt_client_ptr,
                    request_topic_copy);
            });
    }
};
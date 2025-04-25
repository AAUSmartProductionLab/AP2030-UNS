#pragma once

#include "bt/mqtt_async_sub_node.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>

// Forward declarations
class MqttClient;
using nlohmann::json;

// GetProductFromQueue class declaration
class GetProductFromQueue : public BT::DecoratorNode
{
private:
    bool child_running_ = false;
    BT::SharedQueue<std::string> queue_;

public:
    GetProductFromQueue(const std::string &name, const BT::NodeConfig &config)
        : DecoratorNode(name, config)
    {
        auto raw_port = getRawPortValue("Queue");
        if (!isBlackboardPointer(raw_port))
        {
            queue_ = BT::convertFromString<BT::SharedQueue<std::string>>(raw_port);
        }
    }

    BT::NodeStatus tick() override
    {
        bool popped = false;
        if (status() == BT::NodeStatus::IDLE)
        {
            child_running_ = false;
        }

        // Pop value from queue, if the child is not RUNNING
        if (!child_running_)
        {
            BT::AnyPtrLocked any_ref =
                queue_ ? BT::AnyPtrLocked() : getLockedPortContent("Queue");

            if (any_ref)
            {
                queue_ = any_ref.get()->cast<BT::SharedQueue<std::string>>();
            }

            if (queue_ && !queue_->empty())
            {
                auto value = std::move(queue_->front());
                queue_->pop_front();
                popped = true;
                setOutput("Product", value);
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
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::INPUT,
                "Queue",
                "{ProductIDs}",
                "The queue of all product IDs of the batch"),
            BT::InputPort<BT::NodeStatus>("if_empty", BT::NodeStatus::SUCCESS,
                                          "Status to return if queue is empty: "
                                          "SUCCESS, FAILURE, SKIPPED"),
            BT::details::PortWithDefault<std::string>(
                BT::PortDirection::OUTPUT,
                "Product",
                "{_ProductID}",
                "The product ID of the current product")};
    }
};
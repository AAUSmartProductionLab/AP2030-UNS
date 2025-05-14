#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include <string>

class KeepRunningUntilEmpty : public BT::DecoratorNode
{
private:
    // This member is assigned within the tick's lock scope for checking emptiness.
    // It's not strictly necessary as a member if queue_expected.value() is used directly,
    // but can be kept for clarity if preferred.
    BT::SharedQueue<std::string> queue_ptr_from_bb_;

public:
    KeepRunningUntilEmpty(const std::string &name,
                          const BT::NodeConfig &config)
        : DecoratorNode(name, config)
    {
    }

    BT::NodeStatus tick() override
    {
        bool should_tick_child = false;
        BT::NodeStatus status_if_condition_false = getInput<BT::NodeStatus>("if_empty").value_or(BT::NodeStatus::FAILURE);

        // Scope for blackboard access to check queue status
        {
            BT::AnyPtrLocked any_ref = getLockedPortContent("Queue");

            if (!any_ref)
            {
                if (child_node_->status() == BT::NodeStatus::RUNNING)
                {
                    haltChild();
                }
                resetChild();
                return status_if_condition_false;
            }

            BT::Expected<BT::SharedQueue<std::string>> queue_expected = any_ref.get()->cast<BT::SharedQueue<std::string>>();
            if (!queue_expected)
            {
                if (child_node_->status() == BT::NodeStatus::RUNNING)
                {
                    haltChild();
                }
                resetChild();
                return status_if_condition_false;
            }

            queue_ptr_from_bb_ = queue_expected.value();

            if (!queue_ptr_from_bb_) // Check if the shared_ptr on the blackboard is null
            {
                if (child_node_->status() == BT::NodeStatus::RUNNING)
                {
                    haltChild();
                }
                resetChild();
                return status_if_condition_false;
            }

            should_tick_child = !queue_ptr_from_bb_->empty();
        } // Lock on "Queue" is released here.

        if (!should_tick_child)
        {
            if (child_node_->status() == BT::NodeStatus::RUNNING)
            {
                haltChild();
            }
            resetChild();
            return status_if_condition_false;
        }

        setStatus(BT::NodeStatus::RUNNING);
        BT::NodeStatus child_status = child_node_->executeTick();

        switch (child_status)
        {
        case BT::NodeStatus::SUCCESS:
            resetChild();
            return BT::NodeStatus::RUNNING;

        case BT::NodeStatus::FAILURE:
            resetChild();
            return BT::NodeStatus::FAILURE;

        case BT::NodeStatus::RUNNING:
            return BT::NodeStatus::RUNNING;

        default: // SKIPPED or IDLE
            resetChild();
            return BT::NodeStatus::FAILURE; // Or handle as appropriate
        }
    }

    static BT::PortsList providedPorts()
    {
        return {
            BT::InputPort<BT::SharedQueue<std::string>>(
                "Queue",
                "{ProductIDs}",
                "The queue to monitor. Node runs child while this queue is not empty."),
            BT::InputPort<BT::NodeStatus>("if_empty", BT::NodeStatus::SUCCESS,
                                          "Status to return if queue is empty: "
                                          "SUCCESS, FAILURE, SKIPPED")};
    }

    template <typename DerivedNode>
    static void registerNodeType(
        BT::BehaviorTreeFactory &factory,
        const std::string &node_name)
    {
        factory.registerBuilder<DerivedNode>(
            node_name,
            [](const std::string &name, const BT::NodeConfig &config)
            {
                return std::make_unique<DerivedNode>(name, config);
            });
    }
};
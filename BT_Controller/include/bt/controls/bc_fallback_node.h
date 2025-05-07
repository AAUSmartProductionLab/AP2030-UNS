#pragma once

#include "behaviortree_cpp/controls/fallback_node.h"

namespace BT
{
    /**
     * @brief The BC_FallbackNode is used to try different strategies explicitly for back chained fallbacks,
     * until one succeeds. If one action succeeds, the post condition is ticked once more to make sure it has been fulfilled.
     * If any child returns RUNNING, previous children will NOT be ticked again.
     *
     * - If all the children return FAILURE, this node returns FAILURE.
     *
     * - If a child returns RUNNING, this node returns RUNNING.
     *
     * - If a child returns SUCCESS, the post condition is ticked.
     *      If both return SUCCESS stop the loop and return SUCCESS.
     *      If the post condition returns failure, try the next child.
     *
     */
    class BC_FallbackNode : public FallbackNode
    {
    public:
        BC_FallbackNode(const std::string &name, bool make_asynch = false);

        virtual ~BC_FallbackNode() override = default;

        virtual void halt() override;

    private:
        size_t current_child_idx_;
        bool checking_post_cond_ = false;
        size_t saved_child_idx_ = 0;
        size_t skipped_count_ = 0;
        bool asynch_ = false;

        virtual BT::NodeStatus tick() override;
    };

} // namespace BT

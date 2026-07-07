#pragma once

#include <behaviortree_cpp/bt_factory.h>

#include <memory>
#include <string>
#include <vector>

#include "bt/execution_refs.h"

class IActionBackend;
struct ActionContext;

/// Planner-driven action node.  Reads its ports once in initialize(),
/// resolves the shared backend from the registry, and delegates every
/// tick to it.  Zero protocol knowledge — just port parsing + delegation.
class Skill : public BT::StatefulActionNode
{
public:
    Skill(const std::string &name, const BT::NodeConfig &config);
    ~Skill() override;

    void initialize();
    static BT::PortsList providedPorts();
    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;
    void onHalted() override;

private:
    void applySymbolicEffects();
    IActionBackend *backend_ = nullptr;
    std::unique_ptr<ActionContext> ctx_;
    std::optional<bt_exec_refs::ActionRef> action_ref_;
    bool initialized_ = false;
    bool effects_applied_ = false;
};

#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>

#include "aas/transformation_resolver.h"
#include "bt/execution_refs.h"
#include "bt/mqtt_action_node.h"

namespace jsonata
{
    class Jsonata;
}

/// Generic planner-driven action node. Reads `action_ref` and `action_args`
/// ports populated from the planner XML contract, fetches the JSONata
/// transformation referenced by the action_ref, and either publishes the
/// generated message via the asset's MQTT input interface (preferred path)
/// or invokes the AAS Operation directly when no Asset Interface
/// Description is available (fallback path).
class ExecuteAction : public MqttActionNode
{
public:
    ExecuteAction(const std::string &name,
                  const BT::NodeConfig &config,
                  MqttClient &mqtt_client,
                  AASClient &aas_client);

    ~ExecuteAction() override;

    static BT::PortsList providedPorts();

    void initializeTopicsFromAAS() override;
    nlohmann::json createMessage() override;

    BT::NodeStatus onStart() override;
    BT::NodeStatus onRunning() override;

private:
    std::optional<bt_exec_refs::ActionRef> action_ref_;
    std::vector<std::string> args_tokens_;
    std::unique_ptr<jsonata::Jsonata> jsonata_expr_;
    std::string transformation_expression_;
    /// True when no Asset Interface Description was found at construction
    /// time. In that case onStart bypasses MQTT publish and uses
    /// AASClient::invokeOperation instead.
    bool aas_direct_fallback_ = false;

    /// Cached interaction name (last segment of action_aas_path) used both
    /// for AAS interface lookup and for AAS-direct invoke endpoint paths.
    std::string interaction_name_;

    static std::shared_ptr<TransformationResolver> getResolver(AASClient &aas_client);
    static std::string envFallbackMode();

    /// Apply ``action_ref_->effects`` to the process-wide
    /// ``SymbolicState``. Called once per SUCCESS transition; idempotent
    /// to safe to call from both the MQTT-driven onRunning() path and
    /// the AAS-direct onStart() path.
    void applySymbolicEffects();
    bool effects_applied_ = false;
};

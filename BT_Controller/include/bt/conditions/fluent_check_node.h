#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>

#include "aas/transformation_resolver.h"
#include "bt/execution_refs.h"
#include "bt/mqtt_sync_condition_node.h"

namespace jsonata
{
    class Jsonata;
}

/// Generic planner-driven condition node. Reads `predicate_ref` and
/// `predicate_args` ports populated by the planner XML contract and
/// evaluates the JSONata transformation referenced by predicate_ref against
/// the latest received subscription message (or against a polled AAS
/// property value when no subscription interface is available).
class FluentCheck : public MqttSyncConditionNode
{
public:
    FluentCheck(const std::string &name,
                const BT::NodeConfig &config,
                MqttClient &mqtt_client,
                AASClient &aas_client);

    ~FluentCheck() override;

    static BT::PortsList providedPorts();

    void initializeTopicsFromAAS() override;
    BT::NodeStatus tick() override;

private:
    std::optional<bt_exec_refs::PredicateRef> predicate_ref_;
    std::vector<std::string> args_tokens_;
    std::unique_ptr<jsonata::Jsonata> jsonata_expr_;
    std::string transformation_expression_;
    /// True when no Asset Interface Description was found at construction
    /// time. In that case tick() polls fetchPropertyValue per evaluation.
    bool aas_direct_fallback_ = false;

    std::string interaction_name_;

    static std::shared_ptr<TransformationResolver> getResolver(AASClient &aas_client);
    bool evaluateAgainst(const nlohmann::json &payload);

    /// Look up the predicate against the process-wide ``SymbolicState``.
    /// Used when ``transformation_aas_path`` is empty (symbolic-only
    /// predicates such as step_done / step_ready). Args are derived from
    /// the predicate_ref's parameter_refs by taking the tail of each
    /// ``aas_path`` (planner emits stable
    /// ``AI-Planning/Problem/Objects/<ObjectName>``-style paths).
    BT::NodeStatus tickSymbolic();
};

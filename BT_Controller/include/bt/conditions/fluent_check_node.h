#pragma once

#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
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
/// evaluates the JSONata transformation referenced by predicate_ref
/// against the latest received subscription message. When the predicate
/// has no transformation_aas_path the node falls back to a symbolic
/// lookup against the process-wide ``SymbolicState``. Data-backed
/// predicates without an MQTT binding are rejected by the controller's
/// startup validator.
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

    /// Override the base callback to route per-Variable MQTT messages
    /// into the corresponding ``params_[i].Variables.<key>`` slot.
    void callback(const std::string &topic_key,
                  const nlohmann::json &msg,
                  mqtt::properties props) override;

private:
    std::optional<bt_exec_refs::PredicateRef> predicate_ref_;
    std::vector<std::string> args_tokens_;
    std::unique_ptr<jsonata::Jsonata> jsonata_expr_;
    std::string transformation_expression_;

    /// Per-parameter AAS snapshots (flattened {idShort: value} JSON), indexed by
    /// the position of the corresponding entry in
    /// ``predicate_ref_->parameter_refs``. ``Parameters`` is fetched once
    /// at init; ``Variables.<key>`` slots are kept live by MQTT callbacks
    /// driven by each Variable's ``InterfaceReference``.
    std::vector<nlohmann::json> params_;

    /// Routing table for per-Variable MQTT subscriptions. Keyed by the
    /// topic_key string passed to ``MqttSubBase::setTopic`` (we use
    /// ``"p<i>:<var_key>"``). Each entry tells ``callback`` which
    /// ``params_[i].Variables.<var_key>`` slot to update; the slot's
    /// existing field set (populated by the static AAS flatten) drives
    /// which keys of the incoming JSON message are consumed.
    struct VarBinding
    {
        std::size_t param_index = 0;
        std::string var_key;
    };
    std::unordered_map<std::string, VarBinding> var_subscriptions_;

    /// Constants declared on the Fluent SMC alongside its Transformation
    /// (registration emits these from each fluent's YAML ``constants:``
    /// block). Flattened to ``{name: typed_value}``; empty object when the
    /// fluent has no constants.
    nlohmann::json constants_;

    std::string interaction_name_;

    static std::shared_ptr<TransformationResolver> getResolver(AASClient &aas_client);
    bool evaluateAgainst();

    /// Look up the predicate against the process-wide ``SymbolicState``.
    /// Used when ``transformation_aas_path`` is empty (symbolic-only
    /// predicates such as step_done / step_ready). Args are derived from
    /// the predicate_ref's parameter_refs by taking the tail of each
    /// ``aas_path`` (planner emits stable
    /// ``AI-Planning/Problem/Objects/<ObjectName>``-style paths).
    BT::NodeStatus tickSymbolic();
};

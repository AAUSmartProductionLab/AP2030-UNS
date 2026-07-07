#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

// Forward declarations.
class AASClient;
namespace bt_exec_refs
{
    struct ParameterRef;
}

/// Resolves skill parameter bindings for ExecuteAction nodes.
///
/// Two resolution paths are supported:
///
/// 1. **Ontology binding** (Phase C, future):
///    Queries the KG for ``apex-protocol-binding`` templates via SPARQL,
///    substitutes ``{args.N}`` placeholders, resolves ``$ref:`` paths
///    against AAS data, and chains transformations to build the AAS
///    Operation input payload.
///
/// 2. **Legacy JSONata binding** (current, fallback):
///    Uses the existing TransformationResolver to fetch JSONata
///    expressions from the AAS Capabilities submodel and evaluates them
///    with the same parameter snapshot context used by the current
///    ExecuteAction node.
///
/// New BT XMLs can use ``binding_template_ref`` instead of
/// ``transformation_aas_path``; old XMLs continue to work via path 2.
class BindingResolver
{
public:
    /// @param aas_client      AASClient for legacy JSONata resolution path.
    explicit BindingResolver(AASClient &aas_client);

    ~BindingResolver();

    // ── Resolution ────────────────────────────────────────────────────

    /// Build the input payload for an AAS Skill Operation invocation.
    ///
    /// @param asset_id        The target asset AAS shell ID.
    /// @param parameter_refs  Per-parameter AAS references.
    /// @param args_tokens     Grounded argument values.
    /// @param params_snapshots Per-parameter AAS snapshots.
    /// @param constants       Flattened constants JSON (or empty object).
    std::optional<nlohmann::json> resolve(
        const std::string &asset_id,
        const std::vector<bt_exec_refs::ParameterRef> &parameter_refs,
        const std::vector<std::string> &args_tokens,
        const std::vector<nlohmann::json> &params_snapshots,
        const nlohmann::json &constants);

    // ── Ontology path (Phase C) ────────────────────────────────────────

    /// Whether to prefer ontology binding templates over legacy JSONata.
    /// When true, resolve() queries the KG for a binding template before
    /// falling back to the legacy path. False by default (legacy-only).
    void setPreferOntologyBindings(bool prefer);
    bool preferOntologyBindings() const;

private:
    AASClient &aas_client_;
    bool prefer_ontology_ = false;

    std::optional<nlohmann::json> resolveViaJsonata(
        const std::string &asset_id,
        const std::vector<bt_exec_refs::ParameterRef> &parameter_refs,
        const std::vector<std::string> &args_tokens,
        const std::vector<nlohmann::json> &params_snapshots,
        const nlohmann::json &constants);
};

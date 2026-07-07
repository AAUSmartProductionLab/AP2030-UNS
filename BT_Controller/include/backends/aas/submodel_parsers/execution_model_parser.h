#pragma once

#include <optional>
#include <string>
#include <vector>
#include <nlohmann/json_fwd.hpp>

// Forward declarations
class AASClient;

namespace bt_exec_refs
{
    struct ParameterRef;
} // namespace bt_exec_refs

/// Parser for the Skills submodel's ExecutionModel SMC.
///
/// Each skill in the Skills submodel may contain an ExecutionModel
/// child that declaratively describes the skill's symbolic effects
/// and conditions using ontology-standardised predicates.  This parser
/// reads that structure and grounds the parameterised predicates
/// against the concrete parameter bindings supplied by the planner.
///
/// The ExecutionModel replaces the earlier approach of embedding
/// fully-grounded effect atoms inside the BT XML (action_ref /
/// predicate_ref payloads).  The BT_Controller now fetches the
/// authoritative skill semantics from the AAS at runtime.
class ExecutionModelParser
{
public:
    /// A single parsed term node from a condition or effect group.
    /// Represents either an atomic predicate (with param indices) or
    /// a compound logic / FOND operator (with nested children).
    struct Term
    {
        /// Ontology predicate URI (e.g. ``http://www.w3id.org/aau-ra/cssx#Operational``)
        /// or logic-operator URI (e.g. ``cssx:And``, ``cssx:Not``).
        std::string semantic_id;

        /// Indices into the ExecutionModel Parameters list for atomic
        /// predicates.  Empty for compound / operator terms.
        std::vector<int> param_indices;

        /// Whether this atomic term is negated.
        bool negated = false;

        /// Operator kind for compound terms: ``"and"``, ``"or"``,
        /// ``"not"``, ``"oneOf"``, ``"when"``, or empty for atoms.
        std::string operator_type;

        /// FOND guard expression (only meaningful when operator_type == "when").
        std::string when_condition;

        /// Nested child terms (compound operators only).
        std::vector<Term> children;
    };

    /// Parsed ExecutionModel for one skill.
    struct ExecutionModel
    {
        /// Number of declared parameters (length of the Parameters list).
        int parameter_count = 0;

        std::vector<Term> preconditions;
        std::vector<Term> invariant_conditions;
        std::vector<Term> postconditions;
        std::vector<Term> start_effects;
        std::vector<Term> continuous_effects;
        std::vector<Term> end_effects;

        /// Transformation JSONata expression string, if present.
        std::optional<std::string> transformation;
    };

    /// A grounded atom ready for KG insertion / deletion.
    struct GroundedAtom
    {
        std::string predicate;         // ontology predicate URI
        std::vector<std::string> args; // concrete object names
        bool value = true;             // true = insert, false = delete
    };

    /// A grounded effect branch (FOND outcome).
    struct GroundedBranch
    {
        int branch_index = 0;
        std::optional<std::string> when_expr;
        std::vector<GroundedAtom> atoms;
    };

    explicit ExecutionModelParser(AASClient &aas_client);

    /// Fetch and parse the ExecutionModel for a named skill from the
    /// asset's Skills submodel.  Returns std::nullopt if the skill or
    /// its ExecutionModel cannot be found / parsed.
    std::optional<ExecutionModel> fetchExecutionModel(
        const std::string &asset_id,
        const std::string &skill_name);

    /// Ground a list of effect terms into concrete KG atoms using the
    /// supplied parameter bindings.  ``param_values`` is indexed by the
    /// ExecutionModel parameter position and should contain the
    /// ``aas_path`` last segment (object name) for each bound parameter.
    std::vector<GroundedAtom> groundEffects(
        const std::vector<Term> &effect_terms,
        const std::vector<std::string> &param_values) const;

    /// Ground effect terms with FOND branching support.  Returns one
    /// branch per distinct ``oneOf`` alternative, or a single branch
    /// with index 0 for plain (non-FOND) effects.
    std::vector<GroundedBranch> groundBranchedEffects(
        const std::vector<Term> &effect_terms,
        const std::vector<std::string> &param_values) const;

    /// Resolve the JSONata transformation expression from a skill's
    /// ExecutionModel.  Looks for a ``Transformation`` property child
    /// inside the ExecutionModel SMC.  Returns std::nullopt if absent.
    std::optional<std::string> resolveTransformation(
        const std::string &asset_id,
        const std::string &skill_name);

private:
    AASClient &aas_client_;

    /// Recursively parse a term tree from a JSON SubmodelElementCollection.
    Term parseTerm(const nlohmann::json &smc) const;

    /// Ground a single term into atoms (recursive for compound terms).
    void groundTerm(
        const Term &term,
        const std::vector<std::string> &param_values,
        bool parent_negated,
        std::vector<GroundedAtom> &out) const;

    // ── CSSX operator URI helpers ──────────────────────────────────
    static constexpr const char *CSSX = "http://www.w3id.org/aau-ra/cssx#";

    static bool isCssxOperator(const std::string &uri, const std::string &op);
};

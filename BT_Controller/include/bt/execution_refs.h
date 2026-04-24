#pragma once

#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace bt_exec_refs
{

    /// Per-parameter binding emitted by the planner inside an action_ref or
    /// predicate_ref payload.
    struct ParameterRef
    {
        std::string name;
        std::string aas_id;
        std::string aas_path;
    };

    /// Fully grounded planner atom of the form ``predicate(arg1, arg2, ...)
    /// := value``. Used both for seeding ``SymbolicState`` from
    /// ``planner_metadata.initial_state`` and for representing per-action
    /// symbolic effects on ``ActionRef``. Args are object-name strings as
    /// emitted by the planner; ``value`` carries the literal effect
    /// (boolean predicates store ``true``/``false``).
    struct GroundedAtom
    {
        std::string predicate;
        std::vector<std::string> args;
        nlohmann::json value;
    };

    /// Decoded `action_ref` payload as carried on planner-generated
    /// ExecuteAction nodes.
    struct ActionRef
    {
        std::string source_aas_id;
        std::string action_aas_path;
        std::string transformation_aas_path;
        std::vector<ParameterRef> parameter_refs;
        /// Optional convenience field referenced by the planner XML when the ref
        /// payload is reused via a blackboard alias. The runtime currently does
        /// not need it but parsing keeps it for diagnostics.
        std::string aas_link_key;
        /// Mapping of parameter name -> object_refs key, where the planner
        /// captures the object name carried at planning time (used only for
        /// diagnostics / future object-ref enrichment).
        nlohmann::json object_refs;
        /// Symbolic-only effects to apply to ``SymbolicState`` after the
        /// underlying skill operation reports SUCCESS. Sensor-backed
        /// effects are intentionally excluded by the planner.
        std::vector<GroundedAtom> effects;
    };

    /// Decoded `predicate_ref` payload as carried on planner-generated
    /// FluentCheck nodes.
    struct PredicateRef
    {
        std::string source_aas_id;
        std::string fluent_aas_path;
        std::string transformation_aas_path;
        std::vector<ParameterRef> parameter_refs;
        std::string aas_link_key;
        nlohmann::json object_refs;
    };

    /// Strip a single optional layer of wrapping double quotes from `text`.
    /// "{a};{b}" -> {a};{b}; plain text passes through unchanged.
    std::string stripWrappingQuotes(const std::string &text);

    /// Parse an args port value into individual argument tokens. Empty input
    /// yields an empty vector. The wrapping quotes (if any) are stripped first
    /// and tokens are split on `;`. BT.CPP port chaining is expected to have
    /// already substituted any `{Param_*}` placeholders before this is called,
    /// so tokens are returned as-is without further unescaping.
    std::vector<std::string> parseArgsList(const std::string &args_value);

    /// Parse a JSON action_ref attribute (raw or HTML-entity-encoded).
    /// Returns std::nullopt on malformed JSON or missing required fields.
    std::optional<ActionRef> parseActionRef(const std::string &raw);

    /// Parse a JSON predicate_ref attribute (raw or HTML-entity-encoded).
    /// Returns std::nullopt on malformed JSON or missing required fields.
    std::optional<PredicateRef> parsePredicateRef(const std::string &raw);

    /// Parse a JSON list of grounded atoms, e.g. the value of the
    /// ``_planner_initial_state`` blackboard port. Accepts raw or
    /// HTML-entity-encoded JSON. Returns an empty vector for empty input;
    /// returns ``std::nullopt`` on malformed JSON. Atoms missing
    /// ``predicate`` are skipped silently to keep the runtime tolerant of
    /// older planner output.
    std::optional<std::vector<GroundedAtom>> parseGroundedAtomList(const std::string &raw);

    /// Decode the limited set of HTML entities BT.CPP / XML emitters might leave
    /// inside attribute values. Exposed for testability.
    std::string decodeHtmlEntities(const std::string &input);

    /// Split a planner-emitted slash path into `(submodel_id_short, remainder)`.
    ///
    /// The planner emits paths like `AI-Planning/Domain/Fluents/Free` whose
    /// leading segment names a submodel using the planner-side spelling
    /// (`AI-Planning`). The actual AAS submodel `idShort` is `AIPlanning`
    /// (no hyphen). This helper canonicalizes the leading segment and
    /// returns it together with the remainder. If the path is empty or has
    /// no `/`, the remainder equals the input and the submodel is empty.
    /// Only well-known prefixes are normalized; unknown leading segments
    /// are returned as-is so callers can decide what to do.
    std::pair<std::string, std::string> splitSubmodelPath(const std::string &slash_path);

} // namespace bt_exec_refs

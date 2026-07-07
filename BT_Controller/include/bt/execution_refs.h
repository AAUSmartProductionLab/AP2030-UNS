#pragma once

#include <optional>
#include <string>
#include <vector>

#include <behaviortree_cpp/blackboard.h>
#include <nlohmann/json.hpp>

namespace bt_exec_refs
{

    /// Per-parameter AAS reference.  Used by backend infrastructure
    /// (ActionContext, fetchParamSnapshots).  No longer embedded in
    /// ActionRef — the planner emits AAS IDs directly now.
    struct ParameterRef
    {
        std::string name;
        std::string aas_id;
        std::string aas_path;
    };

    // ═══════════════════════════════════════════════════════════════════
    //  Action execution ref
    // ═══════════════════════════════════════════════════════════════════

    /// Decoded action_ref payload.
    ///
    /// The planner emits a single AAS URL identifying the skill:
    ///   ``https://<host>/submodels/instances/<asset>/Skills/<name>``
    ///
    /// The BT_Controller extracts the asset ID and skill name from the
    /// URL.  Parameter AAS IDs are carried in the ``action_args`` port
    /// as a JSON array of strings.
    struct ActionRef
    {
        std::string skill_url;     // full AAS URL from planner
        std::string source_aas_id; // extracted from URL
        std::string skill_name;    // extracted from URL (last segment)
    };

    /// Parse an action_ref URL and extract source_aas_id + skill_name.
    /// Expected pattern: ``.../submodels/instances/<id>/Skills/<name>``
    std::optional<ActionRef> parseActionRef(const std::string &raw);

    // ═══════════════════════════════════════════════════════════════════
    //  Fluent check ref
    // ═══════════════════════════════════════════════════════════════════

    /// Decoded fluent_ref payload.
    ///
    /// The planner emits the ontology predicate URI directly:
    ///   ``https://w3id.org/2026/apex/Free``
    ///
    /// Arguments are carried in ``fluent_args`` as a JSON array.
    struct FluentRef
    {
        std::string fluent_uri;        // ontology URI for SPARQL
        std::vector<std::string> args; // AAS IDs or literal tokens
    };

    /// Parse a fluent_ref attribute (plain URI string).
    std::optional<FluentRef> parseFluentRef(const std::string &raw);

    /// Parse a JSON array of strings (used for action_args / fluent_args).
    std::vector<std::string> parseJsonStringArray(const std::string &raw);

    // ═══════════════════════════════════════════════════════════════════
    //  Utilities
    // ═══════════════════════════════════════════════════════════════════

    std::vector<std::string> parseArgsList(const std::string &args_value);
    std::string stripWrappingQuotes(const std::string &text);
    std::string decodeHtmlEntities(const std::string &input);
    std::pair<std::string, std::string> splitSubmodelPath(const std::string &slash_path);

} // namespace bt_exec_refs

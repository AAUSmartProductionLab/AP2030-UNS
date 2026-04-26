#pragma once

#include <string>
#include <vector>

#include <behaviortree_cpp/bt_factory.h>

class AASClient;
class AASInterfaceCache;

namespace bt_runtime_validator
{
    /// Per-node validation failure record.
    struct NodeFailure
    {
        std::string node_name;         ///< BT node name as it appears in XML
        std::string registration_name; ///< "ExecuteAction" or "FluentCheck"
        std::string source_aas_id;     ///< Asset whose binding is missing
        std::string interaction;       ///< Last segment of action/fluent path
        std::string reason;            ///< Human-readable diagnostic
    };

    /// Outcome of walking the tree post-creation.
    struct ValidationResult
    {
        std::vector<NodeFailure> failures;
        std::size_t execute_actions_validated = 0;
        std::size_t fluent_checks_validated = 0;
        std::size_t fluent_checks_seeded = 0;
        std::size_t fluent_checks_symbolic = 0;
        std::size_t blackboard_refs_resolved = 0;
        std::vector<std::string> unresolved_blackboard_keys;

        bool ok() const { return failures.empty() && unresolved_blackboard_keys.empty(); }
    };

    /// Walk the live behavior tree and verify every planner-emitted
    /// ExecuteAction / FluentCheck node has the required MQTT bindings
    /// available in the cache (or live AAS), and seed each data-backed
    /// FluentCheck with a synchronous AAS GET so the very first tick has
    /// a value to evaluate.
    ///
    /// This is the authoritative startup gate: callers MUST inspect
    /// ``ValidationResult::ok()`` and abort the run on failure.
    ValidationResult validateAndSeed(BT::Tree &tree,
                                     AASInterfaceCache &cache,
                                     AASClient &aas_client);

    /// Format ``ValidationResult`` as a multi-line, per-asset error
    /// report suitable for logging. Returns an empty string when
    /// ``result.ok()`` is true.
    std::string formatReport(const ValidationResult &result);
}

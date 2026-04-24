#pragma once

#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include <nlohmann/json.hpp>

namespace bt_exec_refs
{
    /// Forward declaration; defined in execution_refs.h.
    struct GroundedAtom;
}

/// Per-tree symbolic planning state.
///
/// Holds plan-internal flags such as ``step_done`` / ``step_ready`` that the
/// planner emits as PDDL fluents but that have no sensor-backed
/// transformation. Keys are canonicalized as
/// ``predicate(arg1,arg2,...)`` with the argument order taken verbatim
/// from the planner. Values are arbitrary JSON; boolean predicates store
/// ``true``/``false`` literals.
///
/// All operations are thread-safe so callbacks from the BT runtime (which
/// can tick from multiple worker threads in BT.CPP v4) and the controller
/// thread can interleave safely.
class SymbolicState
{
public:
    SymbolicState() = default;

    /// Process-wide singleton accessor. The runtime instantiates one
    /// ``BehaviorTree`` at a time, so a process-scoped store is
    /// functionally equivalent to "per-tree" for the current
    /// ``BT_Controller``. ``BehaviorTreeController`` is expected to call
    /// ``clear()`` and then ``seed()`` on each new tree.
    static SymbolicState &instance();

    /// Replace all stored atoms with the given seed list. Atoms with the
    /// same canonical key are deduplicated; later entries win.
    void seed(const std::vector<bt_exec_refs::GroundedAtom> &atoms);

    /// Drop all stored atoms.
    void clear();

    /// Look up the value for ``predicate(args...)``. Returns
    /// ``std::nullopt`` when the key is not present.
    std::optional<nlohmann::json> get(const std::string &predicate,
                                      const std::vector<std::string> &args) const;

    /// Convenience: look up a boolean predicate. Returns ``false`` when
    /// the key is missing or the stored value is not a JSON boolean.
    bool getBool(const std::string &predicate,
                 const std::vector<std::string> &args) const;

    /// Set ``predicate(args...)`` to ``value``.
    void set(const std::string &predicate,
             const std::vector<std::string> &args,
             nlohmann::json value);

    /// Erase ``predicate(args...)``. No-op when the key is absent.
    void erase(const std::string &predicate,
               const std::vector<std::string> &args);

    /// Build the canonical lookup key. Exposed for tests / diagnostics.
    static std::string canonicalKey(const std::string &predicate,
                                    const std::vector<std::string> &args);

    /// Snapshot the entire store as a JSON object keyed by canonical
    /// keys. Intended for diagnostics; do not rely on iteration order.
    nlohmann::json snapshot() const;

private:
    mutable std::mutex mutex_;
    std::unordered_map<std::string, nlohmann::json> store_;
};

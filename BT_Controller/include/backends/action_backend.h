#pragma once

#include <behaviortree_cpp/basic_types.h>
#include <nlohmann/json.hpp>

#include <string>
#include <vector>

// ── Lightweight context passed from the BT node to the backend ───────
// The node reads its ports, parses them, and hands this struct to the
// backend.  The backend never touches BT ports directly.

struct ActionContext
{
    std::string source_aas_id;           // AAS that owns the action def
    std::string action_aas_path;         // e.g. "Domain/Actions/Move"
    std::string transformation_aas_path; // path to JSONata transform (or empty)

    struct ParamRef
    {
        std::string name;
        std::string aas_id;
        std::string aas_path;
    };
    std::vector<ParamRef> parameter_refs;

    std::vector<std::string> args_tokens; // grounded argument values
};

// ── Interface ────────────────────────────────────────────────────────

/// Protocol-agnostic backend for executing a skill/action.
///
/// Lifecycle:
///   1. onStart(ctx)   — called once with parsed action context;
///                       returns SUCCESS/FAILURE (sync) or RUNNING (async).
///   2. onRunning()    — called each tick while RUNNING.
///   3. onHalted()     — called if the BT halts mid-execution.
class IActionBackend
{
public:
    virtual ~IActionBackend() = default;

    /// One-time init after construction — sets up backend-specific
    /// infrastructure (e.g. MQTT NMD/cache).  AAS/KG backends no-op.
    virtual void initialize() {}

    /// One-time teardown before destruction — clears backend-specific
    /// infrastructure.  Complements initialize().
    virtual void shutdown() {}

    virtual BT::NodeStatus onStart(const ActionContext &ctx) = 0;
    virtual BT::NodeStatus onRunning() = 0;
    virtual void onHalted() = 0;

    virtual nlohmann::json responseData() const = 0;
    virtual bool isConfigured() const = 0;
    virtual std::string backendName() const = 0;
};

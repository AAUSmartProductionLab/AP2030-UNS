#pragma once

#include <optional>
#include <string>
#include <vector>

/// Protocol-agnostic backend for evaluating a predicate condition.
///
/// IConditionBackend decouples FluentCheck from any specific data source.
/// Backends can query a KG (SPARQL), read AAS Variables (REST), subscribe
/// to MQTT topics, or consult the in-process SymbolicState.
///
/// evaluate() returns:
///   - true/false  — the predicate definitively holds / does not hold
///   - std::nullopt — the backend cannot answer (caller tries next backend)
class IConditionBackend
{
public:
    virtual ~IConditionBackend() = default;

    /// One-time init after construction — sets up backend-specific
    /// infrastructure (e.g. MQTT NMD/cache).  AAS/KG backends no-op.
    virtual void initialize() {}

    /// One-time teardown before destruction.  Complements initialize().
    virtual void shutdown() {}

    /// Evaluate the predicate with the given arguments.
    virtual std::optional<bool> evaluate(
        const std::string &predicate_name,
        const std::vector<std::string> &args) = 0;

    /// Whether this backend is ready.
    virtual bool isConfigured() const = 0;

    /// Human-readable name for logging ("KG", "Symbolic", "MQTT", …).
    virtual std::string backendName() const = 0;
};

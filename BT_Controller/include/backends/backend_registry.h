#pragma once

#include "backends/action_backend.h"
#include "backends/condition_backend.h"

#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

class IMqttClient;
class AASClient;
class SkillInterfaceCache;
class BindingResolver;
class KgClient;
class MqttInfra;
struct BtControllerParameters;

namespace BT
{
    class Tree;
}

/// Interface selection mode — set once at controller startup.
enum class InterfaceMode
{
    /// Use whatever the Asset Interface Description submodel declares
    /// (currently MQTT, could be OPC-UA in the future).
    Native,

    /// Always use the AAS standard interface (direct Operation invoke).
    AAS,
};

/// Process-wide registry of shared backends — both actions and conditions.
///
/// Owns shared infrastructure (MqttInfra, AASClient, KG client)
/// and exposes it to backends that need it.  The controller only passes
/// its config struct — everything else is created internally.
///
/// Backends are created lazily on first lookup and cached for the lifetime
/// of the process.
class BackendRegistry
{
public:
    static BackendRegistry &instance();

    /// Configure all backend infrastructure from the controller's config.
    /// Call once at startup.
    void configure(const BtControllerParameters &params);

    // ── Infrastructure accessors ──────────────────────────────────
    MqttInfra *getMqttInfra() { return mqtt_infra_.get(); }
    AASClient *getAasClient() { return aas_client_.get(); }
    KgClient *getKgClient() { return kg_client_.get(); }
    SkillInterfaceCache *getInterfaceCache();

    // ── Execution lifecycle (protocol-agnostic) ─────────────────────
    /// Called once before the first tick of a new BT tree.  Each
    /// protocol infra performs its own setup (MQTT suspends routing,
    /// subscribes to active-node topics, resumes; HTTP/OPC-UA no-op).
    void prepareForExecution(const BT::Tree &tree);

    // ── Action backends ────────────────────────────────────────────
    /// @param action_name  The skill/action name (last segment of action_aas_path).
    /// @param asset_id     The AAS ID of the asset that owns the action.
    ///                     Used in Native mode for protocol dispatch.
    IActionBackend *getActionBackend(const std::string &action_name,
                                     const std::string &asset_id = "");

    // ── Condition backends (keyed by protocol) ─────────────────────
    IConditionBackend *getConditionBackend(const std::string &key);

    /// Call initialize() on every registered action + condition backend
    /// and on the MQTT infrastructure.
    void initializeAll();

    /// Call shutdown() on every backend and the MQTT infrastructure.
    void shutdownAll();

    /// Lightweight reset between runs: unsubscribe MQTT topics, clear
    /// backend caches and AAS interface cache.  Does NOT tear down the
    /// MQTT transport — it stays connected for the next run.
    void deinitializeAll();

    /// Clear all backends (on reset).
    void clear();

private:
    BackendRegistry() = default;

    mutable std::mutex mutex_;
    std::unordered_map<std::string, std::unique_ptr<IActionBackend>> actions_;
    std::unordered_map<std::string, std::unique_ptr<IConditionBackend>> conditions_;

    InterfaceMode mode_ = InterfaceMode::AAS;

    // ── Backend-owned infrastructure ───────────────────────────────
    std::unique_ptr<MqttInfra> mqtt_infra_;
    std::unique_ptr<AASClient> aas_client_;
    std::unique_ptr<BindingResolver> binding_resolver_;
    std::unique_ptr<KgClient> kg_client_;
};

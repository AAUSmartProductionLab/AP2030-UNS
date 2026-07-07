#include "backends/backend_registry.h"
#include "backends/aas/action_backend.h"
#include "backends/aas/aas_interface_cache.h"
#include "backends/aas/aas_client.h"
#include "backends/aas/binding_resolver.h"
#include "backends/kg/condition_backend.h"
#include "backends/kg/kg_query_client.h"
#include "backends/mqtt/action_backend.h"
#include "backends/mqtt/mqtt_infra.h"
#include "backends/mqtt/node_message_distributor.h"

#include <iostream>

#include "BehaviorTreeController.h"

BackendRegistry &BackendRegistry::instance()
{
    static BackendRegistry reg;
    return reg;
}

void BackendRegistry::configure(const BtControllerParameters &params)
{
    std::lock_guard<std::mutex> lock(mutex_);
    mode_ = params.interface_mode;

    // ── AAS infrastructure (always needed for AAS queries) ────────
    aas_client_ = std::make_unique<AASClient>(params.aasServerUrl,
                                              params.aasRegistryUrl);

    // ── MQTT infrastructure (always needed for message routing) ────
    mqtt_infra_ = std::make_unique<MqttInfra>(params.serverURI,
                                              params.clientId,
                                              *aas_client_);

    // ── AAS binding (only in AAS mode) ────────────────────────
    if (mode_ == InterfaceMode::AAS)
    {
        binding_resolver_ = std::make_unique<BindingResolver>(*aas_client_);
    }

    // ── KG infrastructure (optional, URL-driven) ───────────────────
    if (!params.kg_query_url.empty())
    {
        std::string kg_update_url = params.kg_update_url;
        if (kg_update_url.empty())
        {
            // Auto-derive update URL from query URL:
            //   http://host:3030/kg/sparql  →  http://host:3030/kg/update
            kg_update_url = params.kg_query_url;
            auto pos = kg_update_url.rfind("/sparql");
            if (pos != std::string::npos)
                kg_update_url.replace(pos, 7, "/update");
        }
        kg_client_ = std::make_unique<FusekiQueryClient>(params.kg_query_url,
                                                         kg_update_url,
                                                         params.kg_graph);
    }
}

// ── Action backends ─────────────────────────────────────────────────

IActionBackend *BackendRegistry::getActionBackend(const std::string &name,
                                                  const std::string &asset_id)
{
    std::string cache_key = name;
    if (!asset_id.empty())
        cache_key = asset_id + ":" + name;

    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = actions_.find(cache_key);
        if (it != actions_.end())
            return it->second.get();
    }

    std::unique_ptr<IActionBackend> backend;

    if (mode_ == InterfaceMode::AAS && binding_resolver_)
    {
        backend = std::make_unique<AasActionBackend>(
            *binding_resolver_, *aas_client_);
    }
    else
    {
        // Native mode — dispatch based on asset's declared protocol.
        // resolveSkillInterface caches the result so MqttActionBackend
        // can reuse it without another AAS round-trip.
        std::string protocol;
        if (!asset_id.empty() && mqtt_infra_)
        {
            auto si = mqtt_infra_->getInterfaceCache()
                          ->resolve(asset_id, name);
            if (si)
                protocol = si->protocol;
        }

        if (protocol.empty())
            protocol = "mqtt"; // default / fallback

        if (protocol == "mqtt")
        {
            // Lazy-init MQTT infra on first use.
            if (mqtt_infra_)
                mqtt_infra_->initialize();
            backend = std::make_unique<MqttActionBackend>(
                *mqtt_infra_->getMqttClient(), *aas_client_);
        }
        else
        {
            // Future protocol: log warning, fall back to MQTT.
            std::cerr << "BackendRegistry: unknown protocol '" << protocol
                      << "' for asset " << asset_id
                      << ", falling back to MQTT" << std::endl;
            backend = std::make_unique<MqttActionBackend>(
                *mqtt_infra_->getMqttClient(), *aas_client_);
        }
    }

    std::lock_guard<std::mutex> lock(mutex_);
    auto [it, _] = actions_.emplace(cache_key, std::move(backend));
    return it->second.get();
}

// ── Condition backends ──────────────────────────────────────────────

IConditionBackend *BackendRegistry::getConditionBackend(const std::string &key)
{
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = conditions_.find(key);
        if (it != conditions_.end())
            return it->second.get();
    }

    std::unique_ptr<IConditionBackend> backend;

    if (key == "kg")
    {
        if (kg_client_ && kg_client_->isConfigured())
            backend = std::make_unique<KgConditionBackend>(*kg_client_);
    }
    // Future: re-enable "protocol" key when per-predicate condition_backend
    // classification is added (MQTT variables, AAS properties, OPC-UA).

    if (!backend)
        return nullptr;

    std::lock_guard<std::mutex> lock(mutex_);
    auto [it, _] = conditions_.emplace(key, std::move(backend));
    return it->second.get();
}

void BackendRegistry::initializeAll()
{
    std::lock_guard<std::mutex> lock(mutex_);

    // MQTT infra is now initialized lazily on first action that needs it.
    for (auto &[name, backend] : actions_)
        backend->initialize();
    for (auto &[key, backend] : conditions_)
        backend->initialize();
}

void BackendRegistry::shutdownAll()
{
    std::lock_guard<std::mutex> lock(mutex_);

    for (auto &[name, backend] : actions_)
        backend->shutdown();
    for (auto &[key, backend] : conditions_)
        backend->shutdown();

    if (mqtt_infra_)
        mqtt_infra_->shutdown();
}

void BackendRegistry::deinitializeAll()
{
    std::lock_guard<std::mutex> lock(mutex_);

    // Unsubscribe all active MQTT topic patterns.
    if (mqtt_infra_)
        mqtt_infra_->unsubscribeTopics(
            mqtt_infra_->getNmd()->getActiveTopicPatterns());

    // Drop cached backends — they will be re-created on next use.
    actions_.clear();
    conditions_.clear();

    // Clear the AAS interface cache so the next run re-resolves.
    if (mqtt_infra_)
        mqtt_infra_->getInterfaceCache()->clear();
}

void BackendRegistry::clear()
{
    std::lock_guard<std::mutex> lock(mutex_);
    actions_.clear();
    conditions_.clear();
}

// ── Execution lifecycle ──────────────────────────────────────────────

SkillInterfaceCache *BackendRegistry::getInterfaceCache()
{
    return mqtt_infra_ ? mqtt_infra_->getInterfaceCache() : nullptr;
}

void BackendRegistry::prepareForExecution(const BT::Tree &tree)
{
    if (mqtt_infra_)
        mqtt_infra_->prepareForExecution(tree);
}

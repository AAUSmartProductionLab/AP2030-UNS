#include "backends/aas/binding_resolver.h"
#include "backends/aas/aas_client.h"
#include "bt/execution_refs.h"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>

#include <jsonata/Jsonata.h>

namespace
{
    std::string nowIso8601()
    {
        auto now = std::chrono::system_clock::now();
        std::time_t t = std::chrono::system_clock::to_time_t(now);
        std::tm tm_buf{};
        gmtime_r(&t, &tm_buf);
        std::ostringstream oss;
        oss << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%SZ");
        return oss.str();
    }

    std::string generateUuid()
    {
        // Simple UUID v4 generation. In production this should use a
        // proper UUID library, but this matches the existing behavior.
        static std::mutex rng_mutex;
        std::lock_guard<std::mutex> lock(rng_mutex);
        static bool seeded = false;
        if (!seeded)
        {
            std::srand(static_cast<unsigned>(std::time(nullptr)));
            seeded = true;
        }
        std::ostringstream oss;
        oss << std::hex << std::setfill('0');
        for (int i = 0; i < 8; ++i)
            oss << std::setw(2) << (std::rand() % 256);
        oss << "-";
        for (int i = 0; i < 2; ++i)
            oss << std::setw(2) << (std::rand() % 256);
        oss << "-4"; // Version 4
        oss << std::setw(3) << (std::rand() % 4096);
        oss << "-";
        oss << std::setw(1) << ((8 + (std::rand() % 4)) % 16);
        oss << std::setw(3) << (std::rand() % 4096);
        oss << "-";
        for (int i = 0; i < 6; ++i)
            oss << std::setw(2) << (std::rand() % 256);
        return oss.str();
    }
}

BindingResolver::BindingResolver(AASClient &aas_client)
    : aas_client_(aas_client)
{
}

BindingResolver::~BindingResolver() = default;

void BindingResolver::setPreferOntologyBindings(bool prefer)
{
    prefer_ontology_ = prefer;
}

bool BindingResolver::preferOntologyBindings() const
{
    return prefer_ontology_;
}

std::optional<nlohmann::json> BindingResolver::resolve(
    const std::string &asset_id,
    const std::vector<bt_exec_refs::ParameterRef> &parameter_refs,
    const std::vector<std::string> &args_tokens,
    const std::vector<nlohmann::json> &params_snapshots,
    const nlohmann::json &constants)
{
    // ── Legacy JSONata path (transformation resolved from Skills ExecutionModel) ──
    return resolveViaJsonata(asset_id, parameter_refs, args_tokens, params_snapshots, constants);
}

std::optional<nlohmann::json> BindingResolver::resolveViaJsonata(
    const std::string &asset_id,
    const std::vector<bt_exec_refs::ParameterRef> &parameter_refs,
    const std::vector<std::string> &args_tokens,
    const std::vector<nlohmann::json> &params_snapshots,
    const nlohmann::json &constants)
{
    // Build minimal payload with UUID.
    // Transformation expressions are now resolved from Skills.ExecutionModel
    // by the MqttActionBackend directly; this path returns the fallback.
    nlohmann::json msg;
    msg["Uuid"] = generateUuid();
    return msg;
}

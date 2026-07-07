#include "backends/aas/action_backend.h"
#include "backends/aas/aas_client.h"
#include "backends/aas/binding_resolver.h"
#include "bt/execution_refs.h"

#include <iostream>

namespace
{
    std::string lastSegment(const std::string &path)
    {
        if (path.empty())
            return path;
        std::string t = path;
        while (!t.empty() && (t.back() == '/' || t.back() == '.'))
            t.pop_back();
        auto p = t.find_last_of("/.");
        return (p == std::string::npos) ? t : t.substr(p + 1);
    }
}

AasActionBackend::AasActionBackend(BindingResolver &resolver,
                                   AASClient &aas_client)
    : resolver_(resolver), aas_client_(aas_client) {}

bool AasActionBackend::isConfigured() const { return true; }

BT::NodeStatus AasActionBackend::onStart(const ActionContext &ctx)
{
    std::string asset_id = ctx.source_aas_id;
    if (!ctx.parameter_refs.empty() && !ctx.parameter_refs.front().aas_id.empty())
        asset_id = ctx.parameter_refs.front().aas_id;

    std::string skill_name = lastSegment(ctx.action_aas_path);

    // Fetch constants and parameter snapshots from AAS.
    std::vector<bt_exec_refs::ParameterRef> param_refs;
    for (const auto &p : ctx.parameter_refs)
        param_refs.push_back({p.name, p.aas_id, p.aas_path});

    auto constants = aas_client_.fetchSiblingConstants(asset_id, "");
    auto params = aas_client_.fetchParamSnapshots(param_refs, true);

    auto payload = resolver_.resolve(asset_id, param_refs,
                                     ctx.args_tokens, params, constants);
    if (!payload.has_value())
    {
        std::cerr << "AasActionBackend: payload resolution failed for "
                  << skill_name << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    // Invoke the skill: operation path is "<skill_name>/<skill_name>".
    std::string op_path = skill_name + "/" + skill_name;
    auto response = aas_client_.invokeOperation(asset_id, "Skills", op_path, *payload);
    if (!response.has_value())
    {
        last_response_ = {};
        return BT::NodeStatus::FAILURE;
    }
    last_response_ = *response;
    return BT::NodeStatus::SUCCESS;
}

BT::NodeStatus AasActionBackend::onRunning() { return BT::NodeStatus::SUCCESS; }
void AasActionBackend::onHalted() {}
nlohmann::json AasActionBackend::responseData() const { return last_response_; }

#include "bt/actions/execute_action_node.h"

#include "backends/action_backend.h"
#include "backends/aas/submodel_parsers/execution_model_parser.h"
#include "backends/backend_registry.h"
#include "backends/kg/kg_query_client.h"
#include "bt/bt_log.h"
#include "bt/execution_refs.h"

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

Skill::Skill(const std::string &name,
               const BT::NodeConfig &config)
    : BT::StatefulActionNode(name, config) {}

Skill::~Skill() = default;

BT::PortsList Skill::providedPorts()
{
    return {BT::InputPort<std::string>("action_ref"),
            BT::InputPort<std::string>("action_args")};
}

void Skill::initialize()
{
    if (initialized_)
        return;

    auto ref_str = getInput<std::string>("action_ref");
    if (!ref_str.has_value())
        return;
    action_ref_ = bt_exec_refs::parseActionRef(ref_str.value());
    if (!action_ref_.has_value())
        return;

    // Parse argument AAS IDs (JSON array) or legacy semicolon-separated.
    auto args_str = getInput<std::string>("action_args");
    auto args_tokens = args_str.has_value()
                           ? bt_exec_refs::parseJsonStringArray(args_str.value())
                           : std::vector<std::string>{};
    // Fallback: if JSON parse yielded nothing, try legacy format
    if (args_tokens.empty() && args_str.has_value())
        args_tokens = bt_exec_refs::parseArgsList(args_str.value());

    // Resolve the shared backend by skill name and asset.
    std::string action_name = action_ref_->skill_name;
    backend_ = BackendRegistry::instance().getActionBackend(
        action_name, action_ref_->source_aas_id);
    if (!backend_)
    {
        BT_LOG_ERROR("Skill '" << name() << "': no backend for '"
                     << action_name << "'");
        return;
    }

    // Build the context.
    ctx_ = std::make_unique<ActionContext>();
    ctx_->source_aas_id = action_ref_->source_aas_id;
    ctx_->action_aas_path = "Skills/" + action_ref_->skill_name;
    ctx_->transformation_aas_path = "";
    // Build parameter_refs from AAS IDs: each arg becomes a ParamRef
    // with the AAS ID as both aas_id and aas_path (for backend compat).
    for (const auto &aas_id : args_tokens)
        ctx_->parameter_refs.push_back({"", aas_id, aas_id});
    ctx_->args_tokens = std::move(args_tokens);

    initialized_ = true;
}

// ── BT lifecycle ────────────────────────────────────────────────────

BT::NodeStatus Skill::onStart()
{
    effects_applied_ = false;
    if (!initialized_ || !backend_)
        return BT::NodeStatus::FAILURE;
    return backend_->onStart(*ctx_);
}

BT::NodeStatus Skill::onRunning()
{
    if (!backend_)
        return BT::NodeStatus::FAILURE;
    BT::NodeStatus s = backend_->onRunning();
    if (s == BT::NodeStatus::SUCCESS)
        applySymbolicEffects();
    return s;
}

void Skill::onHalted()
{
    if (backend_)
        backend_->onHalted();
}

void Skill::applySymbolicEffects()
{
    if (effects_applied_ || !action_ref_.has_value())
        return;
    effects_applied_ = true;

    const auto &ref = *action_ref_;
    if (ref.skill_name.empty())
        return;

    auto *kg = BackendRegistry::instance().getKgClient();
    if (!kg || !kg->isConfigured())
    {
        BT_LOG_WARN("ExecuteAction '" << name()
                                      << "': KG client not available for symbolic effects");
        return;
    }

    // ── Fetch skill execution semantics from AAS ──────────────────
    auto *aas_client = BackendRegistry::instance().getAasClient();
    if (!aas_client)
    {
        BT_LOG_WARN("ExecuteAction '" << name()
                                      << "': AAS client not available");
        return;
    }

    ExecutionModelParser parser(*aas_client);
    auto exec_model = parser.fetchExecutionModel(
        ref.source_aas_id, ref.skill_name);
    if (!exec_model)
    {
        BT_LOG_WARN("ExecuteAction '" << name()
                                      << "': cannot fetch ExecutionModel for skill '"
                                      << ref.skill_name << "' on " << ref.source_aas_id);
        return;
    }

    // Build param_values from action_args tokens — these are the grounded
    // object names in the same order as the skill's ExecutionModel parameters.
    // The planner emits plain semicolon-separated strings (no Param_* indirection).
    std::vector<std::string> param_values = ctx_->args_tokens;

    // Ground the end-effects (the primary effects applied on completion).
    auto branches = parser.groundBranchedEffects(
        exec_model->end_effects, param_values);

    // Select the branch matching the response Outcome.
    nlohmann::json response = backend_->responseData();
    int outcome = 0;
    if (response.contains("Outcome") && response["Outcome"].is_number_integer())
        outcome = response["Outcome"].get<int>();

    const ExecutionModelParser::GroundedBranch *selected = nullptr;
    for (const auto &b : branches)
    {
        if (b.branch_index == outcome)
        {
            selected = &b;
            break;
        }
    }
    if (!selected && !branches.empty())
        selected = &branches.front();
    if (!selected)
        return;

    // Apply all atoms of the selected branch to the KG.
    for (const auto &atom : selected->atoms)
    {
        if (atom.value)
            kg->insertFact(atom.predicate, atom.args);
        else
            kg->deleteFact(atom.predicate, atom.args);
    }
}

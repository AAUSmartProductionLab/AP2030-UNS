#include "bt/conditions/fluent_check_node.h"

#include "backends/backend_registry.h"
#include "backends/condition_backend.h"
#include "bt/bt_log.h"
#include "bt/execution_refs.h"

Predicate::Predicate(const std::string &name,
                     const BT::NodeConfig &config)
    : BT::ConditionNode(name, config) {}

Predicate::~Predicate() = default;

BT::PortsList Predicate::providedPorts()
{
    return {BT::InputPort<std::string>("fluent_ref"),
            BT::InputPort<std::string>("fluent_args")};
}

void Predicate::initialize()
{
    if (initialized_)
        return;

    auto ref_str = getInput<std::string>("fluent_ref");
    if (!ref_str.has_value())
        return;
    fluent_ref_ = bt_exec_refs::parseFluentRef(ref_str.value());
    if (!fluent_ref_.has_value())
        return;

    // Parse argument AAS IDs (JSON array) or legacy semicolon-separated.
    auto args_str = getInput<std::string>("fluent_args");
    if (args_str.has_value())
    {
        fluent_ref_->args = bt_exec_refs::parseJsonStringArray(args_str.value());
        if (fluent_ref_->args.empty())
            fluent_ref_->args = bt_exec_refs::parseArgsList(args_str.value());
    }

    kg_ = BackendRegistry::instance().getConditionBackend("kg");
    if (!kg_)
        BT_LOG_ERROR("FluentCheck '" << name() << "': KG backend not configured");

    initialized_ = true;
}

BT::NodeStatus Predicate::tick()
{
    if (!initialized_)
        initialize();
    if (!fluent_ref_.has_value() || !kg_)
        return BT::NodeStatus::FAILURE;

    auto result = kg_->evaluate(fluent_ref_->fluent_uri, fluent_ref_->args);
    if (!result.has_value())
    {
        BT_LOG_WARN("FluentCheck '" << fluent_ref_->fluent_uri
                                    << "': KG query returned nullopt");
        return BT::NodeStatus::FAILURE;
    }
    return *result ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

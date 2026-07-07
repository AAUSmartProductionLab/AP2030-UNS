#pragma once

#include <behaviortree_cpp/bt_factory.h>

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "bt/execution_refs.h"

class IConditionBackend;

/// Planner-driven condition node.  Reads its ports once in initialize(),
/// resolves the KG condition backend from BackendRegistry, and evaluates
/// every predicate via SPARQL ASK to the knowledge graph.
///
/// Ports (new format):
///   - ``fluent_ref``  — ontology predicate URI (e.g. https://w3id.org/2026/apex/Free)
///   - ``fluent_args`` — JSON array of argument values (AAS IDs or literals)
class Predicate : public BT::ConditionNode
{
public:
    Predicate(const std::string &name, const BT::NodeConfig &config);
    ~Predicate() override;

    void initialize();
    static BT::PortsList providedPorts();
    BT::NodeStatus tick() override;

private:
    std::optional<bt_exec_refs::FluentRef> fluent_ref_;
    IConditionBackend *kg_ = nullptr;
    bool initialized_ = false;
};

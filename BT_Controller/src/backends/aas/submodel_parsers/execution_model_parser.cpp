#include "backends/aas/submodel_parsers/execution_model_parser.h"
#include "backends/aas/submodel_parsers/skills_parser.h"
#include "backends/aas/aas_client.h"
#include "bt/execution_refs.h"

#include <algorithm>
#include <iostream>
#include <nlohmann/json.hpp>

namespace
{
    // ── JSON helpers ───────────────────────────────────────────────

    /// Extract the first GlobalReference value from a semanticId object.
    std::string extractSemanticId(const nlohmann::json &element)
    {
        if (!element.contains("semanticId"))
            return {};
        const auto &sid = element["semanticId"];
        const nlohmann::json *keys = nullptr;
        if (sid.is_object() && sid.contains("keys") && sid["keys"].is_array())
            keys = &sid["keys"];
        else if (sid.is_array())
            keys = &sid;
        if (!keys)
            return {};
        for (const auto &k : *keys)
        {
            if (k.is_object() && k.value("type", "") == "GlobalReference" &&
                k.contains("value") && k["value"].is_string())
                return k["value"].get<std::string>();
        }
        return {};
    }

    /// Locate a child by idShort within an SMC's value array.
    const nlohmann::json *findInValue(const nlohmann::json &parent,
                                      const std::string &id_short)
    {
        if (!parent.contains("value") || !parent["value"].is_array())
            return nullptr;
        for (const auto &child : parent["value"])
        {
            if (child.is_object() &&
                child.value("idShort", "") == id_short)
                return &child;
        }
        return nullptr;
    }

    /// Extract param index from a child ReferenceElement's idShort.
    /// Expected format: ``param_N`` where N is an integer.
    int parseParamIndex(const nlohmann::json &child)
    {
        std::string id = child.value("idShort", "");
        if (id.rfind("param_", 0) == 0)
        {
            try
            {
                return std::stoi(id.substr(6));
            }
            catch (...)
            {
                return -1;
            }
        }
        return -1;
    }

    /// Check if a semantic URI is a CSSX operator.
    bool isCssxOp(const std::string &uri, const std::string &op)
    {
        const std::string suffix = "#" + op;
        if (uri.size() >= suffix.size())
            return uri.compare(uri.size() - suffix.size(), suffix.size(), suffix) == 0;
        return false;
    }
} // namespace

// ── Public interface ─────────────────────────────────────────────────────

ExecutionModelParser::ExecutionModelParser(AASClient &aas_client)
    : aas_client_(aas_client) {}

bool ExecutionModelParser::isCssxOperator(const std::string &uri,
                                          const std::string &op)
{
    return ::isCssxOp(uri, op);
}

std::optional<ExecutionModelParser::ExecutionModel>
ExecutionModelParser::fetchExecutionModel(
    const std::string &asset_id,
    const std::string &skill_name)
{
    try
    {
        auto skills_sm = aas_client_.fetchSubmodelData(asset_id, "Skills");
        if (!skills_sm)
        {
            std::cerr << "ExecutionModelParser: Skills submodel not found for "
                      << asset_id << std::endl;
            return std::nullopt;
        }

        const auto *skill_smc = SkillsParser::findSkillSMC(*skills_sm, skill_name);
        if (!skill_smc)
        {
            std::cerr << "ExecutionModelParser: skill '" << skill_name
                      << "' not found in Skills submodel" << std::endl;
            return std::nullopt;
        }

        const auto *exec_model = findInValue(*skill_smc, "ExecutionModel");
        if (!exec_model)
        {
            std::cerr << "ExecutionModelParser: no ExecutionModel in skill '"
                      << skill_name << "'" << std::endl;
            return std::nullopt;
        }

        ExecutionModel model;

        // ── Parameters ──────────────────────────────────────────
        const auto *params_list = findInValue(*exec_model, "Parameters");
        if (params_list && params_list->contains("value") &&
            (*params_list)["value"].is_array())
        {
            model.parameter_count = static_cast<int>((*params_list)["value"].size());
        }

        // ── Transformation ──────────────────────────────────────
        const auto *trans = findInValue(*exec_model, "Transformation");
        if (trans)
        {
            if (trans->contains("value") && (*trans)["value"].is_string())
                model.transformation = (*trans)["value"].get<std::string>();
        }

        // ── Conditions ──────────────────────────────────────────
        const auto *conditions = findInValue(*exec_model, "Conditions");
        if (conditions)
        {
            auto parse_group = [&](const char *name) -> std::vector<Term>
            {
                const auto *group = findInValue(*conditions, name);
                if (!group || !group->contains("value") || !(*group)["value"].is_array())
                    return {};
                std::vector<Term> terms;
                for (const auto &child : (*group)["value"])
                {
                    if (child.is_object())
                        terms.push_back(parseTerm(child));
                }
                return terms;
            };
            model.preconditions = parse_group("PreConditions");
            model.invariant_conditions = parse_group("InvariantConditions");
            model.postconditions = parse_group("PostConditions");
        }

        // ── Effects ─────────────────────────────────────────────
        const auto *effects = findInValue(*exec_model, "Effects");
        if (effects)
        {
            auto parse_group = [&](const char *name) -> std::vector<Term>
            {
                const auto *group = findInValue(*effects, name);
                if (!group || !group->contains("value") || !(*group)["value"].is_array())
                    return {};
                std::vector<Term> terms;
                for (const auto &child : (*group)["value"])
                {
                    if (child.is_object())
                        terms.push_back(parseTerm(child));
                }
                return terms;
            };
            model.start_effects = parse_group("StartEffects");
            model.continuous_effects = parse_group("ContinuousEffects");
            model.end_effects = parse_group("EndEffects");
        }

        return model;
    }
    catch (const std::exception &e)
    {
        std::cerr << "ExecutionModelParser::fetchExecutionModel error: "
                  << e.what() << std::endl;
        return std::nullopt;
    }
}

// ── Term parser (recursive) ──────────────────────────────────────────────

ExecutionModelParser::Term
ExecutionModelParser::parseTerm(const nlohmann::json &smc) const
{
    Term term;
    term.semantic_id = extractSemanticId(smc);

    // Classify the term by its semanticId.
    if (::isCssxOp(term.semantic_id, "And"))
    {
        term.operator_type = "and";
    }
    else if (::isCssxOp(term.semantic_id, "Or"))
    {
        term.operator_type = "or";
    }
    else if (::isCssxOp(term.semantic_id, "Not"))
    {
        term.operator_type = "not";
    }
    else if (::isCssxOp(term.semantic_id, "OneOf"))
    {
        term.operator_type = "oneOf";
    }
    else if (::isCssxOp(term.semantic_id, "When"))
    {
        term.operator_type = "when";
    }

    // Parse children.
    if (!smc.contains("value") || !smc["value"].is_array())
        return term;

    for (const auto &child : smc["value"])
    {
        if (!child.is_object())
            continue;

        std::string child_type = child.value("modelType", "");

        if (child_type == "ReferenceElement")
        {
            // This child refers to a parameter in the Parameters list.
            int idx = parseParamIndex(child);
            if (idx >= 0)
                term.param_indices.push_back(idx);
        }
        else if (child_type == "SubmodelElementCollection")
        {
            // Nested term — recurse.
            Term nested = parseTerm(child);

            // ``when`` has a displayName encoding the guard expression.
            if (::isCssxOp(nested.semantic_id, "When"))
            {
                if (child.contains("displayName"))
                {
                    const auto &dn = child["displayName"];
                    if (dn.is_object() && dn.contains("en") && dn["en"].is_string())
                    {
                        std::string label = dn["en"].get<std::string>();
                        const std::string prefix = "When: ";
                        if (label.rfind(prefix, 0) == 0)
                            nested.when_condition = label.substr(prefix.size());
                    }
                }
            }

            term.children.push_back(std::move(nested));
        }
    }

    return term;
}

// ── Effect grounding ─────────────────────────────────────────────────────

std::vector<ExecutionModelParser::GroundedAtom>
ExecutionModelParser::groundEffects(
    const std::vector<Term> &effect_terms,
    const std::vector<std::string> &param_values) const
{
    std::vector<GroundedAtom> out;
    for (const auto &term : effect_terms)
        groundTerm(term, param_values, false, out);
    return out;
}

void ExecutionModelParser::groundTerm(
    const Term &term,
    const std::vector<std::string> &param_values,
    bool parent_negated,
    std::vector<GroundedAtom> &out) const
{
    bool effective_negated = (parent_negated != term.negated);

    if (term.operator_type.empty())
    {
        // ── Atomic predicate ──
        GroundedAtom atom;
        atom.predicate = term.semantic_id;
        atom.value = !effective_negated; // negated → delete (false)
        for (int idx : term.param_indices)
        {
            if (idx >= 0 && idx < static_cast<int>(param_values.size()))
                atom.args.push_back(param_values[idx]);
            else
                atom.args.push_back("?"); // unresolved — keep for diagnostics
        }
        if (!atom.predicate.empty())
            out.push_back(std::move(atom));
    }
    else if (term.operator_type == "and")
    {
        for (const auto &child : term.children)
            groundTerm(child, param_values, effective_negated, out);
    }
    else if (term.operator_type == "or")
    {
        // OR effects cannot be applied deterministically at runtime
        // without knowing which disjunct holds.  Log and skip.
        std::cerr << "ExecutionModelParser: 'or' in effects is not "
                  << "deterministically applicable; skipping" << std::endl;
    }
    else if (term.operator_type == "not")
    {
        for (const auto &child : term.children)
            groundTerm(child, param_values, !effective_negated, out);
    }
    else if (term.operator_type == "oneOf")
    {
        // oneOf at the top level is handled by groundBranchedEffects().
        // If nested inside another operator, flatten with warning.
        std::cerr << "ExecutionModelParser: nested 'oneOf' in effects; "
                  << "flattening all branches" << std::endl;
        for (const auto &child : term.children)
            groundTerm(child, param_values, effective_negated, out);
    }
    else if (term.operator_type == "when")
    {
        // ``when`` is a FOND guard — handled by groundBranchedEffects().
        // If encountered outside branch context, treat as pass-through.
        for (const auto &child : term.children)
            groundTerm(child, param_values, effective_negated, out);
    }
}

std::vector<ExecutionModelParser::GroundedBranch>
ExecutionModelParser::groundBranchedEffects(
    const std::vector<Term> &effect_terms,
    const std::vector<std::string> &param_values) const
{
    std::vector<GroundedBranch> branches;

    // Check if any term is a ``oneOf`` at the top level.
    const Term *oneof = nullptr;
    for (const auto &term : effect_terms)
    {
        if (term.operator_type == "oneOf")
        {
            oneof = &term;
            break;
        }
    }

    if (oneof)
    {
        // FOND case: each child of oneOf is a branch.
        int idx = 0;
        for (const auto &child : oneof->children)
        {
            GroundedBranch branch;
            branch.branch_index = idx++;

            // Extract when guard if present.
            if (child.operator_type == "when")
            {
                branch.when_expr = child.when_condition;
                for (const auto &grandchild : child.children)
                {
                    std::vector<GroundedAtom> atoms;
                    groundTerm(grandchild, param_values, false, atoms);
                    for (auto &a : atoms)
                        branch.atoms.push_back(std::move(a));
                }
            }
            else
            {
                std::vector<GroundedAtom> atoms;
                groundTerm(child, param_values, false, atoms);
                for (auto &a : atoms)
                    branch.atoms.push_back(std::move(a));
            }
            branches.push_back(std::move(branch));
        }
    }
    else
    {
        // Plain (non-FOND) case: single branch with index 0.
        GroundedBranch branch;
        branch.branch_index = 0;
        for (const auto &term : effect_terms)
        {
            std::vector<GroundedAtom> atoms;
            groundTerm(term, param_values, false, atoms);
            for (auto &a : atoms)
                branch.atoms.push_back(std::move(a));
        }
        branches.push_back(std::move(branch));
    }

    return branches;
}

// ── Transformation resolution ────────────────────────────────────────────

std::optional<std::string> ExecutionModelParser::resolveTransformation(
    const std::string &asset_id,
    const std::string &skill_name)
{
    auto model = fetchExecutionModel(asset_id, skill_name);
    if (!model)
        return std::nullopt;
    return model->transformation;
}

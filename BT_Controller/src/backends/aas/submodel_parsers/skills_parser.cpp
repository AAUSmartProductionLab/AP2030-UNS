#include "backends/aas/submodel_parsers/skills_parser.h"

#include <algorithm>
#include <cctype>
#include <iostream>
#include <nlohmann/json.hpp>

namespace
{
    std::string toLower(const std::string &s)
    {
        std::string result = s;
        std::transform(result.begin(), result.end(), result.begin(),
                       [](unsigned char c)
                       { return std::tolower(c); });
        return result;
    }
} // namespace

// ── Generic AAS element navigation ──────────────────────────────────

const nlohmann::json *SkillsParser::findChildByIdShort(
    const nlohmann::json &collection,
    const std::string &id_short)
{
    const nlohmann::json *children = nullptr;
    if (collection.contains("submodelElements") && collection["submodelElements"].is_array())
        children = &collection["submodelElements"];
    else if (collection.contains("value") && collection["value"].is_array())
        children = &collection["value"];
    if (!children)
        return nullptr;
    for (const auto &c : *children)
    {
        if (c.contains("idShort") && c["idShort"].is_string() &&
            c["idShort"].get<std::string>() == id_short)
        {
            return &c;
        }
    }
    return nullptr;
}

std::optional<std::string> SkillsParser::lastKeyValue(
    const nlohmann::json &reference_element)
{
    if (!reference_element.is_object())
        return std::nullopt;
    if (!reference_element.contains("value") || !reference_element["value"].is_object())
        return std::nullopt;
    const auto &val = reference_element["value"];
    if (!val.contains("keys") || !val["keys"].is_array() || val["keys"].empty())
        return std::nullopt;
    const auto &last = val["keys"].back();
    if (!last.contains("value") || !last["value"].is_string())
        return std::nullopt;
    return last["value"].get<std::string>();
}

// ── Skills submodel navigation ──────────────────────────────────────

const nlohmann::json *SkillsParser::findSkillSMC(
    const nlohmann::json &skills_submodel,
    const std::string &skill_name)
{
    if (!skills_submodel.contains("submodelElements") ||
        !skills_submodel["submodelElements"].is_array())
    {
        return nullptr;
    }

    std::string key = toLower(skill_name);
    for (const auto &elem : skills_submodel["submodelElements"])
    {
        if (!elem.contains("idShort"))
            continue;
        if (toLower(elem["idShort"].get<std::string>()) == key)
            return &elem;
    }
    return nullptr;
}

std::optional<std::pair<std::string, std::string>>
SkillsParser::getInterfaceReference(const nlohmann::json &skill_smc)
{
    if (!skill_smc.contains("value") || !skill_smc["value"].is_array())
        return std::nullopt;

    for (const auto &child : skill_smc["value"])
    {
        if (!child.contains("idShort") || child["idShort"] != "InterfaceReference")
            continue;
        if (!child.contains("value") || !child["value"].contains("keys") ||
            !child["value"]["keys"].is_array())
        {
            std::cerr << "SkillsParser: InterfaceReference has invalid structure" << std::endl;
            return std::nullopt;
        }

        const auto &keys = child["value"]["keys"];
        if (keys.empty())
        {
            std::cerr << "SkillsParser: InterfaceReference has no keys" << std::endl;
            return std::nullopt;
        }

        // The second key (index 1) is the AID interface element idShort.
        // The last key is the interaction name within InteractionMetadata.
        std::string iface_id_short;
        if (keys.size() >= 5)
            iface_id_short = keys[1].value("value", "");

        std::string interaction_name = keys.back().value("value", "");

        return std::make_pair(iface_id_short, interaction_name);
    }
    return std::nullopt;
}

std::string SkillsParser::buildOperationPath(const std::string &skill_name)
{
    return skill_name + "/" + skill_name;
}

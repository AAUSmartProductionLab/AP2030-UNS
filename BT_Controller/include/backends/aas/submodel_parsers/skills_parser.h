#pragma once

#include <optional>
#include <string>
#include <utility>
#include <nlohmann/json_fwd.hpp>

/// Static utility class for navigating the Skills submodel.
///
/// Extracts skill SMCs, InterfaceReference details, and builds
/// operation paths from the Skills submodel JSON structure.
class SkillsParser
{
public:
    // ── Generic AAS element navigation ──────────────────────────────

    /// Locate a child element by idShort within a collection (either
    /// submodelElements or a SubmodelElementCollection value array).
    /// Returns nullptr when the chain breaks.
    static const nlohmann::json *findChildByIdShort(
        const nlohmann::json &collection,
        const std::string &id_short);

    /// Extract the last key value from a ReferenceElement's keys array.
    /// Returns std::nullopt for malformed references.
    static std::optional<std::string> lastKeyValue(
        const nlohmann::json &reference_element);

    // ── Skills submodel navigation ──────────────────────────────────

    /// Locate a skill SubmodelElementCollection within the Skills
    /// submodel by skill name (case-insensitive match on idShort).
    static const nlohmann::json *findSkillSMC(
        const nlohmann::json &skills_submodel,
        const std::string &skill_name);

    /// Extract the InterfaceReference from a skill SMC.
    /// Returns {interface_id_short, interaction_name} where
    /// interface_id_short is the AID interface element idShort and
    /// interaction_name is the key within InteractionMetadata.
    static std::optional<std::pair<std::string, std::string>>
    getInterfaceReference(const nlohmann::json &skill_smc);

    /// Build the operation path for a skill SMC.
    /// Returns "<skill_name>/<skill_name>" (the convention where
    /// the Operation inside a Skill SMC shares the SMC's id_short).
    static std::string buildOperationPath(const std::string &skill_name);
};

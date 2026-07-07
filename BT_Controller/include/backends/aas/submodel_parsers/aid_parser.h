#pragma once

#include "backends/aas/aas_interface_cache.h" // for SkillInterface

#include <optional>
#include <string>
#include <vector>
#include <nlohmann/json_fwd.hpp>

// Forward declarations
class AASClient;
class IProtocolAidParser;

/// Parser for the Asset Interface Description (AID) submodel.
///
/// Walks the AID submodel to resolve a skill name into a SkillInterface
/// by:
/// 1. Loading the Skills submodel to find the skill's InterfaceReference
/// 2. Navigating to the correct interface element in the AID submodel
/// 3. Extracting the protocol from supplementalSemanticIds
/// 4. Dispatching to the registered IProtocolAidParser for that protocol
///
/// This class owns the common AID traversal logic.  Protocol-specific
/// form parsing (MQTT topics, HTTP endpoints, …) is delegated to
/// registered IProtocolAidParser implementations.
class AIDParser
{
public:
    explicit AIDParser(AASClient &aas_client);

    /// Register a protocol-specific AID parser.
    void registerProtocolParser(IProtocolAidParser &parser);

    /// Resolve the SkillInterface for a given (asset, skill) by walking
    /// the Skills → AID submodel chain and dispatching to the appropriate
    /// protocol parser.
    std::optional<SkillInterface> resolveSkillInterface(
        const std::string &asset_id,
        const std::string &skill_name);

private:
    AASClient &aas_client_;
    std::vector<IProtocolAidParser *> protocol_parsers_;

    /// Extract protocol name from supplementalSemanticIds of an AID
    /// interface element.
    static std::string extractProtocolFromSupplemental(
        const nlohmann::json &elem);
};

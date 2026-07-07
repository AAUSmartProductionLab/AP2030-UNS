#pragma once

#include <optional>
#include <string>
#include <nlohmann/json_fwd.hpp>

struct SkillInterface;

/// Protocol-specific parser for a single AID (Asset Interface Description)
/// interaction element.  Each protocol backend (MQTT, HTTP, OPC-UA, …)
/// implements one of these and registers it with AIDParser.
///
/// When AIDParser walks the AID submodel and finds an interaction
/// with a given protocol, it dispatches to the registered parser to
/// extract protocol-specific metadata (topics, endpoints, QoS, etc.).
class IProtocolAidParser
{
public:
    virtual ~IProtocolAidParser() = default;

    /// Human-readable protocol name for matching / diagnostics.
    virtual std::string protocolName() const = 0;

    /// Parse a single interaction element from the AID submodel.
    ///
    /// @param interaction_elem  The JSON SubmodelElementCollection for the
    ///                          interaction (action or property) found in
    ///                          InteractionMetadata.
    /// @param skill_name        The idShort of the skill being resolved.
    /// @return A populated SkillInterface on success, nullopt on failure.
    virtual std::optional<SkillInterface> parseInteraction(
        const nlohmann::json &interaction_elem,
        const std::string &skill_name) = 0;
};

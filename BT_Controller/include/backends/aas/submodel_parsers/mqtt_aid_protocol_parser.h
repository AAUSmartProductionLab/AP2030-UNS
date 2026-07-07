#pragma once

#include "backends/aas/submodel_parsers/i_protocol_aid_parser.h"
#include <string>

/// Parses MQTT-specific metadata from an AID Interface* submodel element.
///
/// Extracts the base topic from EndpointMetadata, locates the skill in
/// InteractionMetadata, and reads MQTT form fields (href, QoS, retain,
/// response href, schema URLs) to build a SkillInterface.
///
/// Owned by MqttInfra and registered with AIDParser so that AID traversal
/// dispatches to it automatically when the protocol is "mqtt".
class MqttAidProtocolParser : public IProtocolAidParser
{
public:
    std::string protocolName() const override { return "mqtt"; }

    std::optional<SkillInterface> parseInteraction(
        const nlohmann::json &interaction_elem,
        const std::string &skill_name) override;
};

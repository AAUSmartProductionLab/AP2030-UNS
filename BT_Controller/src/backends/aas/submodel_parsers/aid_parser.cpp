#include "backends/aas/submodel_parsers/aid_parser.h"
#include "backends/aas/submodel_parsers/i_protocol_aid_parser.h"
#include "backends/aas/submodel_parsers/skills_parser.h"
#include "backends/aas/aas_client.h"
#include "utils.h"

#include <algorithm>
#include <cctype>
#include <iostream>

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

AIDParser::AIDParser(AASClient &aas_client)
    : aas_client_(aas_client) {}

void AIDParser::registerProtocolParser(IProtocolAidParser &parser)
{
    protocol_parsers_.push_back(&parser);
}

std::string AIDParser::extractProtocolFromSupplemental(const nlohmann::json &elem)
{
    static const std::vector<std::pair<std::string, std::string>> kKnown = {
        {"mqtt", "mqtt"}, {"http", "http"}, {"modbus", "modbus"}, {"opc-ua", "opcua"}, {"opcua", "opcua"}};
    if (!elem.contains("supplementalSemanticIds") ||
        !elem["supplementalSemanticIds"].is_array())
        return {};
    for (const auto &sid : elem["supplementalSemanticIds"])
    {
        std::string uri;
        if (sid.contains("keys") && sid["keys"].is_array() && !sid["keys"].empty())
            uri = sid["keys"][0].value("value", "");
        if (uri.empty())
            continue;
        std::string lu = str_utils::toLower(uri);
        for (const auto &[kw, proto] : kKnown)
            if (lu.find(kw) != std::string::npos)
                return proto;
    }
    return {};
}

std::optional<SkillInterface> AIDParser::resolveSkillInterface(
    const std::string &asset_id,
    const std::string &skill_name)
{
    try
    {
        // Step 1: fetch Skills submodel, find the skill SMC
        auto skills = aas_client_.fetchSubmodelData(asset_id, "Skills");
        if (!skills)
        {
            std::cerr << "AIDParser: no Skills submodel for " << asset_id << std::endl;
            return std::nullopt;
        }

        const auto *skill_smc = SkillsParser::findSkillSMC(*skills, skill_name);
        if (!skill_smc)
        {
            std::cerr << "AIDParser: skill '" << skill_name
                      << "' not found in Skills submodel for " << asset_id << std::endl;
            return std::nullopt;
        }

        // Step 2: extract InterfaceReference details
        auto iref = SkillsParser::getInterfaceReference(*skill_smc);
        std::string iface_id_short;
        std::string interaction_name = skill_name;
        if (iref.has_value())
        {
            iface_id_short = iref->first;
            interaction_name = iref->second;
        }
        else
        {
            std::cerr << "AIDParser: no InterfaceReference in skill '" << skill_name
                      << "', falling back to skill name as interaction key" << std::endl;
        }

        std::string ik = toLower(interaction_name);

        // Step 3: helper to try parsing a single interface element
        auto tryParse = [&](const nlohmann::json &iface_elem) -> std::optional<SkillInterface>
        {
            std::string protocol = extractProtocolFromSupplemental(iface_elem);
            if (protocol.empty())
            {
                // Fallback: derive protocol from interface element idShort
                // (e.g. "InterfaceMQTT" → "mqtt")
                std::string id = iface_elem["idShort"].get<std::string>();
                if (id.size() > 9) // "Interface" prefix
                    protocol = toLower(id.substr(9));
            }
            for (auto *parser : protocol_parsers_)
            {
                if (parser->protocolName() == protocol)
                    return parser->parseInteraction(iface_elem, ik);
            }
            std::cerr << "AIDParser: no parser for protocol '" << protocol << "'"
                      << std::endl;
            return std::nullopt;
        };

        // Step 4: locate the interface element and dispatch
        if (!iface_id_short.empty())
        {
            auto iface_json = aas_client_.fetchSubmodelElementByPath(
                asset_id, "AssetInterfacesDescription", iface_id_short);
            if (iface_json)
                return tryParse(*iface_json);
        }
        else
        {
            // Fallback: scan all interface elements in AID submodel
            auto aid = aas_client_.fetchSubmodelData(asset_id, "AssetInterfacesDescription");
            if (aid && aid->contains("submodelElements") && (*aid)["submodelElements"].is_array())
            {
                for (const auto &elem : (*aid)["submodelElements"])
                {
                    if (elem.contains("idShort") &&
                        elem["idShort"].get<std::string>().rfind("Interface", 0) == 0)
                    {
                        if (auto si = tryParse(elem))
                            return si;
                    }
                }
            }
        }

        std::cerr << "AIDParser: interaction '" << interaction_name
                  << "' not found for " << asset_id << std::endl;
        return std::nullopt;
    }
    catch (const std::exception &e)
    {
        std::cerr << "AIDParser::resolveSkillInterface: " << e.what() << std::endl;
        return std::nullopt;
    }
}

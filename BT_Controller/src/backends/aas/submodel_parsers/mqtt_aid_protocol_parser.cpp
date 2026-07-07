#include "backends/aas/submodel_parsers/mqtt_aid_protocol_parser.h"

#include "backends/aas/aas_interface_cache.h"
#include "utils.h"

#include <algorithm>
#include <cctype>
#include <cstring>
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

    const nlohmann::json *findChild(const nlohmann::json &parent,
                                    const std::string &name)
    {
        if (!parent.contains("value") || !parent["value"].is_array())
            return nullptr;
        std::string key = toLower(name);
        for (const auto &c : parent["value"])
            if (c.contains("idShort") &&
                toLower(c["idShort"].get<std::string>()) == key)
                return &c;
        return nullptr;
    }

    std::string getChildValue(const nlohmann::json &parent,
                              const std::string &idShort)
    {
        if (auto *c = findChild(parent, idShort))
            return c->value("value", "");
        return "";
    }

    int getIntValue(const nlohmann::json &elem, int default_val = 0)
    {
        const auto &v = elem["value"];
        if (v.is_number())
            return v.get<int>();
        if (v.is_string())
        {
            try
            {
                return std::stoi(v.get<std::string>());
            }
            catch (...)
            {
            }
        }
        return default_val;
    }

    bool getBoolValue(const nlohmann::json &elem, bool default_val = false)
    {
        const auto &v = elem["value"];
        if (v.is_boolean())
            return v.get<bool>();
        if (v.is_string())
        {
            std::string s = toLower(v.get<std::string>());
            return s == "true" || s == "1";
        }
        return default_val;
    }

    std::string buildTopicString(const std::string &base,
                                 const std::string &suffix)
    {
        if (suffix.empty())
            return "";
        std::string full = base;
        if (!full.empty() && suffix[0] != '/')
            full += "/";
        full += suffix;
        if (!full.empty() && full[0] == '/')
            full = full.substr(1);
        return full;
    }

    nlohmann::json fetchSchema(const std::string &url)
    {
        if (url.empty())
            return {};
        try
        {
            auto schema = schema_utils::fetchSchemaFromUrl(url);
            schema_utils::resolveSchemaReferences(schema);
            return schema;
        }
        catch (...)
        {
            return {};
        }
    }

    std::string stripProtocolPrefix(const std::string &base)
    {
        std::string r = base;
        for (const auto *p : {"mqtts://", "mqtt://", "https://", "http://",
                              "opc.tcp://"})
        {
            size_t pl = std::strlen(p);
            if (r.size() > pl && r.compare(0, pl, p) == 0)
            {
                r = r.substr(pl);
                size_t sl = r.find('/');
                if (sl != std::string::npos)
                    r = r.substr(sl);
                break;
            }
        }
        if (!r.empty() && r[0] == '/')
            r = r.substr(1);
        return r;
    }
} // namespace

std::optional<SkillInterface> MqttAidProtocolParser::parseInteraction(
    const nlohmann::json &iface_elem,
    const std::string &skill_name)
{
    // 1. Extract base topic from EndpointMetadata
    std::string base_topic;
    if (auto *ep = findChild(iface_elem, "EndpointMetadata"))
        base_topic = stripProtocolPrefix(getChildValue(*ep, "base"));

    // 2. Find the interaction in InteractionMetadata → actions|properties
    const nlohmann::json *interaction = nullptr;
    if (auto *im = findChild(iface_elem, "InteractionMetadata"))
    {
        for (const auto &list : im->at("value"))
        {
            if (list["idShort"] == "actions" ||
                list["idShort"] == "properties")
            {
                if (auto *inter = findChild(list, toLower(skill_name)))
                {
                    interaction = inter;
                    break;
                }
            }
        }
    }

    if (!interaction)
    {
        std::cerr << "MqttAidProtocolParser: interaction '"
                  << skill_name << "' not found" << std::endl;
        return std::nullopt;
    }

    // 3. Parse MQTT forms (href, QoS, retain, response, schema URLs)
    std::string href, response_href;
    int qos = 0;
    bool retain = false;
    std::string input_schema_url, output_schema_url;

    for (const auto &fe : (*interaction)["value"])
    {
        std::string fid = fe.value("idShort", "");

        if (fid == "Forms" || fid == "forms")
        {
            for (const auto &f : fe["value"])
            {
                std::string fk = f.value("idShort", "");

                if (fk == "href")
                    href = f["value"].get<std::string>();
                else if (fk == "mqv_qos")
                    qos = getIntValue(f);
                else if (fk == "mqv_retain")
                    retain = getBoolValue(f);
                else if (fk == "response" &&
                         f["modelType"] == "SubmodelElementCollection")
                    response_href = getChildValue(f, "href");
            }
        }
        else if (fid == "input" && fe["modelType"] == "File")
        {
            if (fe.contains("value") && fe["value"].is_string())
                input_schema_url = fe["value"].get<std::string>();
        }
        else if (fid == "output" && fe["modelType"] == "File")
        {
            if (fe.contains("value") && fe["value"].is_string())
                output_schema_url = fe["value"].get<std::string>();
        }
    }

    // 4. Build SkillInterface with resolved topics
    SkillInterface si;
    si.protocol = "mqtt";

    if (!href.empty())
    {
        si.input_topic = mqtt_utils::Topic(
            buildTopicString(base_topic, href),
            fetchSchema(input_schema_url),
            qos, retain);
        si.has_input = true;
    }

    std::string out_href = response_href.empty() ? href : response_href;
    if (!out_href.empty())
    {
        si.output_topic = mqtt_utils::Topic(
            buildTopicString(base_topic, out_href),
            fetchSchema(output_schema_url),
            qos, retain);
        si.has_output = true;
    }

    return si;
}

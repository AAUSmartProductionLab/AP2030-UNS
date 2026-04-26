#include "aas/aas_snapshot.h"

#include <algorithm>

namespace aas_snapshot
{
    nlohmann::json coerceProperty(const nlohmann::json &elem)
    {
        if (!elem.contains("value"))
        {
            return nlohmann::json(nullptr);
        }
        const auto &raw = elem["value"];
        if (!raw.is_string())
        {
            return raw;
        }
        const std::string s = raw.get<std::string>();
        std::string vt = elem.value("valueType", "");
        try
        {
            if (vt == "xs:boolean")
            {
                return s == "true" || s == "1";
            }
            if (vt == "xs:integer" || vt == "xs:int" || vt == "xs:long" ||
                vt == "xs:short" || vt == "xs:byte" ||
                vt == "xs:nonNegativeInteger" || vt == "xs:positiveInteger" ||
                vt == "xs:unsignedInt" || vt == "xs:unsignedLong")
            {
                return std::stoll(s);
            }
            if (vt == "xs:double" || vt == "xs:float" || vt == "xs:decimal")
            {
                return std::stod(s);
            }
        }
        catch (const std::exception &)
        {
            // fall through to string
        }
        return s;
    }

    nlohmann::json flattenAasElement(const nlohmann::json &elem)
    {
        if (!elem.is_object())
        {
            return elem;
        }
        const std::string mt = elem.value("modelType", "");
        if (mt == "Property")
        {
            return coerceProperty(elem);
        }
        if (mt == "SubmodelElementList")
        {
            nlohmann::json out = nlohmann::json::array();
            if (elem.contains("value") && elem["value"].is_array())
            {
                for (const auto &child : elem["value"])
                {
                    out.push_back(flattenAasElement(child));
                }
            }
            return out;
        }
        if (elem.contains("submodelElements") && elem["submodelElements"].is_array())
        {
            nlohmann::json out = nlohmann::json::object();
            for (const auto &child : elem["submodelElements"])
            {
                if (child.is_object() && child.contains("idShort"))
                {
                    out[child["idShort"].get<std::string>()] = flattenAasElement(child);
                }
            }
            return out;
        }
        if (elem.contains("value") && elem["value"].is_array())
        {
            nlohmann::json out = nlohmann::json::object();
            for (const auto &child : elem["value"])
            {
                if (child.is_object() && child.contains("idShort"))
                {
                    out[child["idShort"].get<std::string>()] = flattenAasElement(child);
                }
            }
            return out;
        }
        if (elem.contains("value"))
        {
            return elem["value"];
        }
        return nlohmann::json(nullptr);
    }

    std::string parentSlashPath(const std::string &slash_path)
    {
        if (slash_path.empty())
        {
            return slash_path;
        }
        auto pos = slash_path.find_last_of('/');
        if (pos == std::string::npos)
        {
            return std::string();
        }
        return slash_path.substr(0, pos);
    }

    std::optional<std::string> lastKeyValue(const nlohmann::json &reference_element)
    {
        if (!reference_element.is_object())
            return std::nullopt;
        if (!reference_element.contains("value") ||
            !reference_element["value"].is_object())
            return std::nullopt;
        const auto &val = reference_element["value"];
        if (!val.contains("keys") || !val["keys"].is_array() || val["keys"].empty())
            return std::nullopt;
        const auto &last = val["keys"].back();
        if (!last.contains("value") || !last["value"].is_string())
            return std::nullopt;
        return last["value"].get<std::string>();
    }

    std::vector<nlohmann::json> fetchParamSnapshots(
        AASClient &aas_client,
        const std::vector<bt_exec_refs::ParameterRef> &parameter_refs,
        bool include_variables,
        std::vector<std::optional<nlohmann::json>> *raw_variables)
    {
        std::vector<nlohmann::json> params;
        params.reserve(parameter_refs.size());
        if (raw_variables)
        {
            raw_variables->clear();
            raw_variables->reserve(parameter_refs.size());
        }
        for (const auto &p : parameter_refs)
        {
            nlohmann::json snapshot = nlohmann::json::object();
            std::optional<nlohmann::json> vars_raw;
            if (p.aas_id.empty())
            {
                params.push_back(std::move(snapshot));
                if (raw_variables)
                {
                    raw_variables->push_back(std::nullopt);
                }
                continue;
            }

            auto params_sm = aas_client.fetchSubmodelElementByPath(
                p.aas_id, "Parameters", std::string());
            if (params_sm.has_value())
            {
                snapshot["Parameters"] = flattenAasElement(*params_sm);
            }

            if (include_variables)
            {
                vars_raw = aas_client.fetchSubmodelElementByPath(
                    p.aas_id, "Variables", std::string());
                if (vars_raw.has_value())
                {
                    snapshot["Variables"] = flattenAasElement(*vars_raw);
                }
            }

            params.push_back(std::move(snapshot));
            if (raw_variables)
            {
                raw_variables->push_back(std::move(vars_raw));
            }
        }
        return params;
    }

    nlohmann::json fetchSiblingConstants(
        AASClient &aas_client,
        const std::string &source_aas_id,
        const std::string &transformation_aas_path)
    {
        nlohmann::json constants = nlohmann::json::object();
        if (source_aas_id.empty() || transformation_aas_path.empty())
        {
            return constants;
        }
        const std::string parent_path = parentSlashPath(transformation_aas_path);
        if (parent_path.empty())
        {
            return constants;
        }
        auto constants_smc = aas_client.fetchSubmodelElementByPath(
            source_aas_id, "AIPlanning", parent_path + "/Constants");
        if (constants_smc.has_value())
        {
            constants = flattenAasElement(*constants_smc);
        }
        return constants;
    }
}

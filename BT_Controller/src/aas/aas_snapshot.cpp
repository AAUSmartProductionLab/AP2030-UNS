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
        // AAS Property cannot natively represent arrays/objects -- they
        // are conventionally stored as ``xs:string`` whose content is a
        // JSON literal (e.g. ``"[]"`` for an empty ProcessQueue, or a
        // JSON object for a structured snapshot). Parse those so JSONata
        // sees them as actual arrays/objects; ``$count("[]")`` returns 1,
        // which would silently break predicates like
        // ``$count(...ProcessQueue) = 0``. Live MQTT updates already
        // arrive as parsed JSON via the callback path, so this aligns
        // the static-snapshot semantics with the runtime semantics.
        if (!s.empty() && (s.front() == '[' || s.front() == '{'))
        {
            try
            {
                return nlohmann::json::parse(s);
            }
            catch (const std::exception &)
            {
                // Not valid JSON after all; fall through to raw string.
            }
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
            // Convention: a SubmodelElementCollection that wraps exactly
            // one Property child named ``value`` is a "scalar wrapper"
            // (used pervasively in the Parameters submodels for fields
            // like Uuid, Location.Position.X, ...). Collapse it to the
            // bare scalar so JSONata expressions like
            // ``params[1].Parameters.Uuid`` and
            // ``params[1].Parameters.Location.Position.X`` see the
            // expected scalar instead of ``{"value": <scalar>}``.
            if (mt == "SubmodelElementCollection" &&
                elem["value"].size() == 1)
            {
                const auto &only = elem["value"][0];
                if (only.is_object() &&
                    only.value("modelType", "") == "Property" &&
                    only.value("idShort", "") == "value")
                {
                    return coerceProperty(only);
                }
            }
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

            // The planner emits ``aas_path`` as
            // ``AI-Planning/Problem/Objects/<obj>``. That target is itself
            // a ``ReferenceElement`` whose first key points at the actual
            // runtime data location:
            //   * type=AssetAdministrationShell -> the *instance* asset
            //     whose top-level ``Parameters``/``Variables`` submodels
            //     hold the runtime values (e.g. ``MIM8_0001AAS``).
            //   * type=Submodel -> a submodel that directly holds the
            //     parameter data (e.g. a Location living inside a
            //     station's ``Parameters`` submodel).
            // We must dereference that ReferenceElement; the planner-side
            // ``aas_id`` only points at the *type* AAS hosting the
            // AIPlanning Object SMC, never at the runtime data itself.
            auto [submodel, remainder] = bt_exec_refs::splitSubmodelPath(p.aas_path);
            if (submodel.empty())
            {
                submodel = "AIPlanning";
                remainder = p.aas_path;
            }

            auto object_smc = aas_client.fetchSubmodelElementByPath(
                p.aas_id, submodel, remainder);

            std::string ref_type;
            std::string ref_value;
            if (object_smc.has_value() && object_smc->is_object() &&
                object_smc->value("modelType", "") == "ReferenceElement" &&
                object_smc->contains("value") && (*object_smc)["value"].is_object())
            {
                const auto &v = (*object_smc)["value"];
                if (v.contains("keys") && v["keys"].is_array() && !v["keys"].empty())
                {
                    const auto &k = v["keys"][0];
                    ref_type = k.value("type", "");
                    ref_value = k.value("value", "");
                }
            }

            std::optional<nlohmann::json> params_sm;
            if (ref_type == "AssetAdministrationShell" && !ref_value.empty())
            {
                // The Object reference points at an instance AAS; fetch
                // its top-level ``Parameters`` and ``Variables``.
                params_sm = aas_client.fetchSubmodelElementByPath(
                    ref_value, "Parameters", "");
                if (include_variables)
                {
                    vars_raw = aas_client.fetchSubmodelElementByPath(
                        ref_value, "Variables", "");
                }
            }
            else if (ref_type == "Submodel" && !ref_value.empty())
            {
                // The Object reference points directly at a submodel
                // (e.g. a station's Parameters submodel hosting a
                // Location SMC). Fetch by full submodel id. There are no
                // Variables in this case.
                params_sm = aas_client.fetchSubmodelById(ref_value);
            }
            else
            {
                // Back-compat / fallback: try the historic top-level
                // lookup directly on the planner-emitted aas_id.
                params_sm = aas_client.fetchSubmodelElementByPath(
                    p.aas_id, "Parameters", "");
                if (include_variables)
                {
                    vars_raw = aas_client.fetchSubmodelElementByPath(
                        p.aas_id, "Variables", "");
                }
            }

            if (params_sm.has_value())
            {
                snapshot["Parameters"] = flattenAasElement(*params_sm);
            }
            if (include_variables && vars_raw.has_value())
            {
                snapshot["Variables"] = flattenAasElement(*vars_raw);
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
        // The planner emits paths like
        // ``AI-Planning/Domain/Fluents/Free/Transformation``. The leading
        // segment names a submodel (``AIPlanning`` after normalization)
        // and must be passed to ``fetchSubmodelElementByPath`` as the
        // ``submodel_id_short`` argument; the remainder is the path
        // *within* that submodel. Without this split we'd ask the AAS
        // server to descend through ``AI-Planning/Domain/...`` as if it
        // were an SMC chain, which fails on the first segment.
        auto [submodel, remainder] = bt_exec_refs::splitSubmodelPath(transformation_aas_path);
        if (submodel.empty())
        {
            submodel = "AIPlanning";
            remainder = transformation_aas_path;
        }
        const std::string parent_remainder = parentSlashPath(remainder);
        if (parent_remainder.empty())
        {
            return constants;
        }
        auto constants_smc = aas_client.fetchSubmodelElementByPath(
            source_aas_id, submodel, parent_remainder + "/Constants");
        if (constants_smc.has_value())
        {
            constants = flattenAasElement(*constants_smc);
        }
        return constants;
    }
}

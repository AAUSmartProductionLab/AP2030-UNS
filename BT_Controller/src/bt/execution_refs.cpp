#include "bt/execution_refs.h"

#include <iostream>
#include <sstream>

namespace bt_exec_refs
{

    std::string decodeHtmlEntities(const std::string &input)
    {
        // BT.CPP normally decodes XML entities itself, but action_ref/
        // predicate_ref attribute values can contain JSON with embedded
        // double quotes that some emitters re-escape as &quot;. Decode the
        // small set of entities that may show up.
        std::string out;
        out.reserve(input.size());
        for (size_t i = 0; i < input.size();)
        {
            if (input[i] == '&')
            {
                // Match the longest known entity at this position.
                const struct
                {
                    const char *entity;
                    char replacement;
                } entities[] = {
                    {"&quot;", '"'},
                    {"&apos;", '\''},
                    {"&amp;", '&'},
                    {"&lt;", '<'},
                    {"&gt;", '>'},
                };
                bool matched = false;
                for (const auto &e : entities)
                {
                    size_t len = std::char_traits<char>::length(e.entity);
                    if (input.compare(i, len, e.entity) == 0)
                    {
                        out.push_back(e.replacement);
                        i += len;
                        matched = true;
                        break;
                    }
                }
                if (!matched)
                {
                    out.push_back(input[i]);
                    ++i;
                }
            }
            else
            {
                out.push_back(input[i]);
                ++i;
            }
        }
        return out;
    }

    std::string stripWrappingQuotes(const std::string &text)
    {
        if (text.size() >= 2 && text.front() == '"' && text.back() == '"')
        {
            return text.substr(1, text.size() - 2);
        }
        return text;
    }

    std::vector<std::string> parseArgsList(const std::string &args_value)
    {
        std::vector<std::string> result;
        std::string body = stripWrappingQuotes(args_value);
        // Trim ASCII whitespace.
        auto is_ws = [](char c)
        {
            return c == ' ' || c == '\t' || c == '\n' || c == '\r';
        };
        size_t start = 0;
        while (start < body.size() && is_ws(body[start]))
            ++start;
        size_t end = body.size();
        while (end > start && is_ws(body[end - 1]))
            --end;
        if (start >= end)
        {
            return result;
        }
        body = body.substr(start, end - start);

        std::string token;
        for (char c : body)
        {
            if (c == ';')
            {
                result.push_back(token);
                token.clear();
            }
            else
            {
                token.push_back(c);
            }
        }
        result.push_back(token);
        return result;
    }

    namespace
    {
        std::vector<ParameterRef> parseParameterRefs(const nlohmann::json &node)
        {
            std::vector<ParameterRef> out;
            if (!node.contains("parameter_refs") || !node["parameter_refs"].is_array())
            {
                return out;
            }
            for (const auto &entry : node["parameter_refs"])
            {
                if (!entry.is_object())
                {
                    continue;
                }
                ParameterRef pr;
                if (entry.contains("name") && entry["name"].is_string())
                {
                    pr.name = entry["name"].get<std::string>();
                }
                if (entry.contains("aas_id") && entry["aas_id"].is_string())
                {
                    pr.aas_id = entry["aas_id"].get<std::string>();
                }
                if (entry.contains("aas_path") && entry["aas_path"].is_string())
                {
                    pr.aas_path = entry["aas_path"].get<std::string>();
                }
                out.push_back(std::move(pr));
            }
            return out;
        }

        nlohmann::json safeObject(const nlohmann::json &node, const char *key)
        {
            if (node.contains(key) && (node[key].is_object() || node[key].is_array()))
            {
                return node[key];
            }
            return nlohmann::json::object();
        }

        std::string safeString(const nlohmann::json &node, const char *key)
        {
            if (node.contains(key) && node[key].is_string())
            {
                return node[key].get<std::string>();
            }
            return std::string();
        }

        std::optional<nlohmann::json> tryParseJson(const std::string &raw)
        {
            try
            {
                return nlohmann::json::parse(raw);
            }
            catch (const std::exception &)
            {
                return std::nullopt;
            }
        }

        std::vector<std::string> parseStringArgs(const nlohmann::json &node)
        {
            std::vector<std::string> out;
            if (!node.is_array())
            {
                return out;
            }
            out.reserve(node.size());
            for (const auto &entry : node)
            {
                if (entry.is_string())
                {
                    out.push_back(entry.get<std::string>());
                }
                else
                {
                    // Tolerate non-string args by stringifying; keeps the
                    // runtime resilient to planner schema drift.
                    out.push_back(entry.dump());
                }
            }
            return out;
        }

        std::optional<GroundedAtom> parseGroundedAtom(const nlohmann::json &entry)
        {
            if (!entry.is_object())
            {
                return std::nullopt;
            }
            GroundedAtom atom;
            atom.predicate = safeString(entry, "predicate");
            if (atom.predicate.empty())
            {
                return std::nullopt;
            }
            if (entry.contains("args"))
            {
                atom.args = parseStringArgs(entry["args"]);
            }
            if (entry.contains("value"))
            {
                atom.value = entry["value"];
            }
            else
            {
                // Default to `true` so that a bare {"predicate":"X","args":[...]}
                // entry is interpreted as "the atom holds".
                atom.value = true;
            }
            return atom;
        }

        std::vector<GroundedAtom> parseEffects(const nlohmann::json &node)
        {
            std::vector<GroundedAtom> out;
            if (!node.contains("effects") || !node["effects"].is_array())
            {
                return out;
            }
            for (const auto &entry : node["effects"])
            {
                auto atom = parseGroundedAtom(entry);
                if (atom.has_value())
                {
                    out.push_back(std::move(*atom));
                }
            }
            return out;
        }
    }

    std::optional<ActionRef> parseActionRef(const std::string &raw)
    {
        if (raw.empty())
        {
            return std::nullopt;
        }
        auto parsed = tryParseJson(raw);
        if (!parsed.has_value())
        {
            std::string decoded = decodeHtmlEntities(raw);
            parsed = tryParseJson(decoded);
        }
        if (!parsed.has_value() || !parsed->is_object())
        {
            std::cerr << "parseActionRef: not a JSON object: "
                      << raw.substr(0, std::min<size_t>(raw.size(), 200)) << std::endl;
            return std::nullopt;
        }

        ActionRef ref;
        ref.source_aas_id = safeString(*parsed, "source_aas_id");
        ref.action_aas_path = safeString(*parsed, "action_aas_path");
        ref.transformation_aas_path = safeString(*parsed, "transformation_aas_path");
        ref.aas_link_key = safeString(*parsed, "aas_link_key");
        ref.parameter_refs = parseParameterRefs(*parsed);
        ref.object_refs = safeObject(*parsed, "object_refs");
        ref.effects = parseEffects(*parsed);
        return ref;
    }

    std::optional<PredicateRef> parsePredicateRef(const std::string &raw)
    {
        if (raw.empty())
        {
            return std::nullopt;
        }
        auto parsed = tryParseJson(raw);
        if (!parsed.has_value())
        {
            std::string decoded = decodeHtmlEntities(raw);
            parsed = tryParseJson(decoded);
        }
        if (!parsed.has_value() || !parsed->is_object())
        {
            std::cerr << "parsePredicateRef: not a JSON object: "
                      << raw.substr(0, std::min<size_t>(raw.size(), 200)) << std::endl;
            return std::nullopt;
        }

        PredicateRef ref;
        ref.source_aas_id = safeString(*parsed, "source_aas_id");
        ref.fluent_aas_path = safeString(*parsed, "fluent_aas_path");
        ref.transformation_aas_path = safeString(*parsed, "transformation_aas_path");
        ref.aas_link_key = safeString(*parsed, "aas_link_key");
        ref.parameter_refs = parseParameterRefs(*parsed);
        ref.object_refs = safeObject(*parsed, "object_refs");
        return ref;
    }

    std::optional<std::vector<GroundedAtom>> parseGroundedAtomList(const std::string &raw)
    {
        std::vector<GroundedAtom> out;
        if (raw.empty())
        {
            return out;
        }
        auto parsed = tryParseJson(raw);
        if (!parsed.has_value())
        {
            std::string decoded = decodeHtmlEntities(raw);
            parsed = tryParseJson(decoded);
        }
        if (!parsed.has_value())
        {
            std::cerr << "parseGroundedAtomList: malformed JSON: "
                      << raw.substr(0, std::min<size_t>(raw.size(), 200)) << std::endl;
            return std::nullopt;
        }
        if (!parsed->is_array())
        {
            std::cerr << "parseGroundedAtomList: expected JSON array" << std::endl;
            return std::nullopt;
        }
        for (const auto &entry : *parsed)
        {
            auto atom = parseGroundedAtom(entry);
            if (atom.has_value())
            {
                out.push_back(std::move(*atom));
            }
        }
        return out;
    }

    std::pair<std::string, std::string> splitSubmodelPath(const std::string &slash_path)
    {
        if (slash_path.empty())
        {
            return {"", ""};
        }
        size_t slash = slash_path.find('/');
        if (slash == std::string::npos)
        {
            return {"", slash_path};
        }
        std::string head = slash_path.substr(0, slash);
        std::string tail = slash_path.substr(slash + 1);

        // Canonicalize the planner-side spelling to the actual submodel
        // idShort. The planner emits AI-Planning/... but the submodel
        // generated by Registration_Service is AIPlanning.
        if (head == "AI-Planning" || head == "AIPlanning")
        {
            return {"AIPlanning", tail};
        }
        // Other well-known submodels are passed through verbatim.
        if (head == "Skills" || head == "Capabilities" || head == "Variables" ||
            head == "AssetInterfacesDescription" || head == "ProcessInformation" ||
            head == "RequiredCapabilities" || head == "HierarchicalStructures")
        {
            return {head, tail};
        }
        // Unknown leading segment - treat as in-submodel content (caller
        // will pick a default).
        return {"", slash_path};
    }

} // namespace bt_exec_refs

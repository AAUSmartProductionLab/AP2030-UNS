#include "bt/execution_refs.h"

#include <iostream>
#include <regex>

namespace bt_exec_refs
{

    std::string decodeHtmlEntities(const std::string &input)
    {
        std::string out;
        out.reserve(input.size());
        for (size_t i = 0; i < input.size();)
        {
            if (input[i] == '&')
            {
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
            return text.substr(1, text.size() - 2);
        return text;
    }

    std::vector<std::string> parseArgsList(const std::string &args_value)
    {
        std::vector<std::string> result;
        std::string body = stripWrappingQuotes(args_value);
        auto is_ws = [](char c)
        { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; };
        size_t start = 0;
        while (start < body.size() && is_ws(body[start]))
            ++start;
        size_t end = body.size();
        while (end > start && is_ws(body[end - 1]))
            --end;
        if (start >= end)
            return result;
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
                token.push_back(c);
        }
        result.push_back(token);
        return result;
    }

    std::vector<std::string> parseJsonStringArray(const std::string &raw)
    {
        std::vector<std::string> result;
        if (raw.empty())
            return result;
        std::string decoded = decodeHtmlEntities(raw);
        try
        {
            auto parsed = nlohmann::json::parse(decoded);
            if (parsed.is_array())
                for (const auto &e : parsed)
                    result.push_back(e.is_string() ? e.get<std::string>() : e.dump());
        }
        catch (const std::exception &e)
        {
            std::cerr << "parseJsonStringArray: " << e.what()
                      << " for: " << raw.substr(0, 200) << std::endl;
        }
        return result;
    }

    // ── URL parser ───────────────────────────────────────────────────

    namespace
    {
        bool parseSkillUrl(const std::string &url, std::string &out_aas, std::string &out_skill)
        {
            auto pos = url.find("/instances/");
            if (pos == std::string::npos)
                return false;
            std::string tail = url.substr(pos + 11);
            auto slash1 = tail.find('/');
            if (slash1 == std::string::npos)
                return false;
            out_aas = tail.substr(0, slash1);
            auto skills_pos = tail.find("/Skills/", slash1);
            if (skills_pos == std::string::npos)
                return false;
            std::string skill_part = tail.substr(skills_pos + 8);
            while (!skill_part.empty() && skill_part.back() == '/')
                skill_part.pop_back();
            auto last_slash = skill_part.rfind('/');
            out_skill = (last_slash != std::string::npos)
                            ? skill_part.substr(last_slash + 1)
                            : skill_part;
            return !out_aas.empty() && !out_skill.empty();
        }
    }

    std::optional<ActionRef> parseActionRef(const std::string &raw)
    {
        if (raw.empty())
            return std::nullopt;
        std::string url = stripWrappingQuotes(raw);
        if (url.empty())
            return std::nullopt;
        ActionRef ref;
        ref.skill_url = url;
        if (!parseSkillUrl(url, ref.source_aas_id, ref.skill_name))
        {
            // Backward compat: old JSON with source_aas_id + skill_name
            try
            {
                auto j = nlohmann::json::parse(decodeHtmlEntities(raw));
                if (j.is_object())
                {
                    ref.source_aas_id = j.value("source_aas_id", "");
                    ref.skill_name = j.value("skill_name", "");
                    if (ref.source_aas_id.empty())
                        return std::nullopt;
                }
            }
            catch (...)
            {
                return std::nullopt;
            }
        }
        return ref;
    }

    std::optional<FluentRef> parseFluentRef(const std::string &raw)
    {
        if (raw.empty())
            return std::nullopt;
        std::string uri = stripWrappingQuotes(raw);
        if (uri.empty())
            return std::nullopt;
        if (uri.front() == '{') // old JSON compat
        {
            try
            {
                auto j = nlohmann::json::parse(decodeHtmlEntities(raw));
                if (j.is_object())
                {
                    FluentRef r;
                    r.fluent_uri = j.value("semantic_id", j.value("predicate", ""));
                    if (j.contains("args") && j["args"].is_array())
                        for (const auto &a : j["args"])
                            if (a.is_string())
                                r.args.push_back(a.get<std::string>());
                    if (!r.fluent_uri.empty())
                        return r;
                }
            }
            catch (...)
            {
            }
            return std::nullopt;
        }
        FluentRef ref;
        ref.fluent_uri = uri;
        return ref;
    }

    std::pair<std::string, std::string> splitSubmodelPath(const std::string &slash_path)
    {
        if (slash_path.empty())
            return {"", ""};
        auto pos = slash_path.find('/');
        if (pos == std::string::npos)
            return {"", slash_path};
        std::string first = slash_path.substr(0, pos);
        std::string remainder = slash_path.substr(pos + 1);
        if (first == "AI-Planning" || first == "ai-planning")
            first = "AIPlanning";
        return {first, remainder};
    }

} // namespace bt_exec_refs

#include "backends/aas/condition_backend.h"
#include "backends/aas/aas_client.h"

#include <algorithm>
#include <cctype>
#include <string>

AasConditionBackend::AasConditionBackend(AASClient &aas_client)
    : aas_client_(aas_client) {}

std::optional<bool> AasConditionBackend::evaluate(
    const std::string &predicate_name,
    const std::vector<std::string> &args)
{
    if (args.empty())
        return std::nullopt;

    const std::string &asset_id = args.front();

    if (predicate_name == "Operational")
    {
        auto val = aas_client_.fetchPropertyValue(
            asset_id, "Variables", std::vector<std::string>{"PackMLState", "State"});
        if (!val.has_value())
            return std::nullopt;
        if (!val->is_string())
            return std::nullopt;
        std::string s = val->get<std::string>();
        std::transform(s.begin(), s.end(), s.begin(),
                       [](unsigned char c)
                       { return std::tolower(c); });
        return s == "execute";
    }

    if (predicate_name == "Occupied")
    {
        auto val = aas_client_.fetchPropertyValue(
            asset_id, "Variables", std::vector<std::string>{"ProcessQueue"});
        if (!val.has_value())
            return std::nullopt;
        if (val->is_array())
            return !val->empty();
        if (val->is_string())
        {
            std::string s = val->get<std::string>();
            return !s.empty();
        }
        return false;
    }

    return std::nullopt;
}

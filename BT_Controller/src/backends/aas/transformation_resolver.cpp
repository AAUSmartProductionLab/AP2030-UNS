#include "backends/aas/transformation_resolver.h"

#include <iostream>

#include "bt/execution_refs.h"

TransformationResolver::TransformationResolver(AASClient &aas_client) noexcept
    : aas_client_(aas_client)
{
}

std::string TransformationResolver::makeCacheKey(const std::string &aas_id,
                                                 const std::string &transformation_aas_path) noexcept
{
    return aas_id + "\x1f" + transformation_aas_path;
}

namespace
{
    // Pull a string value out of an AAS Property element. Some BaSyx
    // serializations expose the value at the top level, others wrap it under
    // a "value" object. We accept either.
    std::optional<std::string> extractStringValue(const nlohmann::json &element)
    {
        if (element.is_string())
        {
            return element.get<std::string>();
        }
        if (element.is_object())
        {
            if (element.contains("value"))
            {
                const auto &v = element["value"];
                if (v.is_string())
                {
                    return v.get<std::string>();
                }
                if (v.is_object() || v.is_array())
                {
                    return v.dump();
                }
            }
        }
        return std::nullopt;
    }

    // Transformation expressions now primarily live in the Skills
    // submodel under Skills/<skill>/ExecutionModel/Transformation.
    // Legacy paths (AIPlanning/Domain/.../Transformation) are still
    // supported as fallbacks.
    //
    // The transformation path emitted by the planner may be empty
    // (new format: skill_name is used instead). In that case we
    // try Skills first.
    std::optional<nlohmann::json> resolveAcrossSubmodels(
        AASClient &client,
        const std::string &aas_id,
        const std::string &slash_path)
    {
        auto [submodel, remainder] = bt_exec_refs::splitSubmodelPath(slash_path);
        if (!submodel.empty())
        {
            auto element = client.fetchSubmodelElementByPath(aas_id, submodel, remainder);
            if (element.has_value())
                return element;
        }

        static const std::vector<std::string> candidates = {
            "Skills",
            "AIPlanning",
            "Capabilities",
            "Variables",
        };

        for (const auto &candidate : candidates)
        {
            auto element = client.fetchSubmodelElementByPath(aas_id, candidate, slash_path);
            if (element.has_value())
            {
                return element;
            }
        }
        return std::nullopt;
    }
}

std::optional<std::string> TransformationResolver::getTransformationExpression(
    const std::string &aas_id,
    const std::string &transformation_aas_path)
{
    if (aas_id.empty() || transformation_aas_path.empty())
    {
        std::cerr << "TransformationResolver: empty aas_id or transformation path" << std::endl;
        return std::nullopt;
    }

    const std::string key = makeCacheKey(aas_id, transformation_aas_path);
    {
        std::lock_guard<std::mutex> lock(cache_mutex_);
        auto it = cache_.find(key);
        if (it != cache_.end())
        {
            return it->second;
        }
    }

    auto element = resolveAcrossSubmodels(aas_client_, aas_id, transformation_aas_path);
    if (!element.has_value())
    {
        std::cerr << "TransformationResolver: failed to resolve "
                  << aas_id << " :: " << transformation_aas_path << std::endl;
        return std::nullopt;
    }

    auto expression = extractStringValue(*element);
    if (!expression.has_value())
    {
        std::cerr << "TransformationResolver: element at " << transformation_aas_path
                  << " has no string value" << std::endl;
        return std::nullopt;
    }

    {
        std::lock_guard<std::mutex> lock(cache_mutex_);
        cache_.emplace(key, *expression);
    }
    return expression;
}

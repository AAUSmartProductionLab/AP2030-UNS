#pragma once

#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>

#include "aas/aas_client.h"

/// Caching wrapper around AASClient for fetching JSONata transformation
/// expressions referenced by planner-generated BT nodes.
///
/// Each (asset_id, transformation_aas_path) pair is fetched at most once and
/// the resulting JSONata expression string is cached for the lifetime of the
/// resolver instance. Failures are not cached, so transient AAS server hiccups
/// can be retried on the next BT node construction.
class TransformationResolver
{
public:
    /// The transformation_aas_path is interpreted relative to the
    /// "Capabilities" submodel of the source asset. Concrete BaSyx
    /// deployments may store transformation snippets under a different
    /// submodel; in that case the slash path may include the submodel name
    /// itself as the first segment - the resolver tries both forms.
    explicit TransformationResolver(AASClient &aas_client) noexcept;

    /// Fetch and cache the JSONata transformation expression located at
    /// `transformation_aas_path` within the asset identified by `aas_id`.
    /// Returns std::nullopt when the path cannot be resolved or the value
    /// at the path is not a string-typed Property.
    std::optional<std::string> getTransformationExpression(
        const std::string &aas_id,
        const std::string &transformation_aas_path);

private:
    AASClient &aas_client_;
    std::mutex cache_mutex_;
    std::unordered_map<std::string, std::string> cache_;

    static std::string makeCacheKey(const std::string &aas_id,
                                    const std::string &transformation_aas_path) noexcept;
};

#pragma once

#include <string>
#include <map>
#include <optional>
#include <mutex>
#include <set>
#include <nlohmann/json.hpp>
#include "utils.h"

class AIDParser;

/// Resolved interface for a single skill of an asset.
struct SkillInterface
{
    std::string protocol;
    mqtt_utils::Topic input_topic;
    mqtt_utils::Topic output_topic;
    bool has_input = false;
    bool has_output = false;
};

/// Thread-safe cache of SkillInterface by (asset_id, skill_name).
///
/// AID traversal and protocol dispatch are delegated to
/// AIDParser::resolveSkillInterface() — this class is purely caching.
class SkillInterfaceCache
{
public:
    explicit SkillInterfaceCache(AIDParser &aid_parser);

    /// Resolve + cache.  Calls AIDParser::resolveSkillInterface() on
    /// first lookup for a given (asset, skill) pair.
    std::optional<SkillInterface> resolve(
        const std::string &asset_id,
        const std::string &skill_name);

    /// Wildcard MQTT topic patterns from all cached skills.
    std::set<std::string> getWildcardTopicPatterns() const;

    /// True if any skill is cached for the asset.
    bool hasAsset(const std::string &asset_id) const;

    /// Clear all cached data.
    void clear();

private:
    AIDParser &aid_parser_;
    mutable std::mutex mutex_;
    std::map<std::string, std::map<std::string, SkillInterface>> cache_;
    std::set<std::string> failed_assets_;
};

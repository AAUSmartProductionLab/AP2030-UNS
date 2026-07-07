#include "backends/aas/aas_interface_cache.h"
#include "backends/aas/submodel_parsers/aid_parser.h"
#include "utils.h"
#include <iostream>

SkillInterfaceCache::SkillInterfaceCache(AIDParser &aid_parser)
    : aid_parser_(aid_parser) {}

std::optional<SkillInterface> SkillInterfaceCache::resolve(
    const std::string &asset_id, const std::string &skill_name)
{
    std::string key = str_utils::toLower(skill_name);

    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto ai = cache_.find(asset_id);
        if (ai != cache_.end())
        {
            auto si = ai->second.find(key);
            if (si != ai->second.end())
                return si->second;
        }
        if (failed_assets_.count(asset_id))
            return std::nullopt;
    }

    // Double-checked locking: re-check under lock before fetch.
    std::lock_guard<std::mutex> lock(mutex_);
    {
        auto ai = cache_.find(asset_id);
        if (ai != cache_.end())
        {
            auto si = ai->second.find(key);
            if (si != ai->second.end())
                return si->second;
        }
    }

    // Cache miss — delegate to AIDParser for AID traversal + parser dispatch.
    auto si = aid_parser_.resolveSkillInterface(asset_id, skill_name);
    if (!si.has_value())
    {
        failed_assets_.insert(asset_id);
        return std::nullopt;
    }

    cache_[asset_id][key] = *si;
    return *si;
}

std::set<std::string> SkillInterfaceCache::getWildcardTopicPatterns() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    std::set<std::string> patterns;
    for (const auto &[aid, skills] : cache_)
    {
        for (const auto &[sn, info] : skills)
        {
            if (!info.has_output || info.output_topic.getTopic().empty())
                continue;
            const std::string &t = info.output_topic.getTopic();
            size_t dp = t.find("/DATA"), cp = t.find("/CMD");
            size_t s = std::string::npos;
            if (dp != std::string::npos && cp != std::string::npos)
                s = std::min(dp, cp);
            else if (dp != std::string::npos)
                s = dp;
            else if (cp != std::string::npos)
                s = cp;
            if (s != std::string::npos)
                patterns.insert(t.substr(0, s) + "/#");
        }
    }
    return patterns;
}

bool SkillInterfaceCache::hasAsset(const std::string &asset_id) const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return cache_.find(asset_id) != cache_.end();
}

void SkillInterfaceCache::clear()
{
    std::lock_guard<std::mutex> lock(mutex_);
    cache_.clear();
    failed_assets_.clear();
}

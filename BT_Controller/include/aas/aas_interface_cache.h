#pragma once

#include <string>
#include <map>
#include <optional>
#include <mutex>
#include <set>
#include <nlohmann/json.hpp>
#include "utils.h"

class AASClient;

/**
 * @brief Caches Asset Interface Descriptions fetched from AAS
 *
 * This class pre-fetches and caches interface information for all assets
 * to avoid individual AAS queries during BT node initialization.
 * It also computes wildcard topic patterns for early MQTT subscription.
 */
class AASInterfaceCache
{
public:
    AASInterfaceCache(AASClient &aas_client);

    /**
     * @brief Pre-fetch and cache interface descriptions for all assets
     *
     * Should be called once when the equipment mapping is built,
     * before creating the behavior tree.
     *
     * @param asset_ids Map of equipment name to AAS ID
     * @return true if at least some interfaces were cached successfully
     */
    bool prefetchInterfaces(const std::map<std::string, std::string> &asset_ids);

    /**
     * @brief Get a cached interface for an asset
     *
     * @param asset_id The AAS ID of the asset
     * @param interaction The interaction name (action or property)
     * @param endpoint "input" or "output"
     * @return The Topic if found in cache, nullopt otherwise
     */
    std::optional<mqtt_utils::Topic> getInterface(
        const std::string &asset_id,
        const std::string &interaction,
        const std::string &endpoint) const;

    /**
     * @brief Get wildcard topic patterns that cover all cached assets
     *
     * These patterns can be used for early MQTT subscription to ensure
     * no messages are missed during node initialization.
     *
     * @return Set of wildcard topic patterns
     */
    std::set<std::string> getWildcardTopicPatterns() const;

    /**
     * @brief Get all output topics for a specific asset
     *
     * Useful for subscribing to all state/data topics for an asset
     *
     * @param asset_id The AAS ID of the asset
     * @return Vector of output topics
     */
    std::vector<mqtt_utils::Topic> getAssetOutputTopics(const std::string &asset_id) const;

    /**
     * @brief Check if interfaces are cached for an asset
     */
    bool hasAsset(const std::string &asset_id) const;

    /**
     * @brief Clear all cached data
     */
    void clear();

    /**
     * @brief Get statistics about the cache
     */
    struct CacheStats
    {
        size_t total_assets;
        size_t total_interfaces;
        size_t failed_assets;
    };
    CacheStats getStats() const;

private:
    AASClient &aas_client_;
    mutable std::mutex mutex_;

    // Structure to cache interface data
    struct InterfaceData
    {
        mqtt_utils::Topic input_topic;
        mqtt_utils::Topic output_topic;
        bool has_input = false;
        bool has_output = false;
    };

    // Cache: asset_id -> interaction_name -> InterfaceData
    std::map<std::string, std::map<std::string, InterfaceData>> interface_cache_;

    // Base topic patterns per asset (for computing wildcards)
    std::map<std::string, std::string> asset_base_topics_;

    // Track failed assets for diagnostics
    std::set<std::string> failed_assets_;

    // Helper to extract base topic from a full topic path
    std::string extractBaseTopic(const std::string &topic) const;

    // Helper to fetch all interfaces for a single asset
    bool fetchAssetInterfaces(const std::string &asset_id);
};

#pragma once

#include <string>
#include <optional>
#include <map>
#include <nlohmann/json.hpp>
#include <curl/curl.h>
#include "utils.h"

class AASClient
{
public:
    AASClient(const std::string &aas_server_url,
              const std::string &registry_url = "");
    ~AASClient();

    // Fetch topic configuration for a specific node type and instance
    // The node_params can contain parameters from the BT XML (e.g., station_id, device_name)
    std::optional<mqtt_utils::Topic> fetchInterface(
        const std::string &asset_id,
        const std::string &skill,
        const std::string &interfaceProp);

    nlohmann::json station_config;

    // Helper function to search station config for InstanceName by asset name
    std::string getInstanceNameByAssetName(const std::string &asset_name);
    std::string getStationIdByAssetName(const std::string &asset_name);

private:
    std::string aas_server_url_;
    std::string registry_url_;
    CURL *curl_;
    
    // Cache for fetched schemas to avoid redundant HTTP requests
    std::map<std::string, nlohmann::json> schema_cache_;

    // Helper to make HTTP GET requests
    nlohmann::json makeGetRequest(const std::string &endpoint, bool use_registry = false);

    // Helper to substitute parameters in topic patterns
    std::string substituteParams(const std::string &pattern, const nlohmann::json &params);
    
    // Helper to fetch a schema from a URL (with caching)
    nlohmann::json fetchSchemaFromUrl(const std::string &schema_url);
    
    // Helper to recursively resolve $ref in schemas
    void resolveSchemaReferences(nlohmann::json &schema);
};
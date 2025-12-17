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
        const std::string &interaction,
        const std::string &interfaceProp);

    nlohmann::json station_config;

    // Helper function to search station config for InstanceName by asset name
    std::string getInstanceNameByAssetName(const std::string &asset_name);
    std::string getStationIdByAssetName(const std::string &asset_name);

    // Fetch a property value directly from the AAS
    // Simple version: searches recursively for first match
    std::optional<nlohmann::json> fetchPropertyValue(
        const std::string &asset_id,
        const std::string &submodel_id_short,
        const std::string &property_id_short);

    // Path-based version: navigates through specific hierarchy path
    // Example path: {"EntryNode", "Loading", "Location", "x"}
    // This allows targeting specific nested properties when multiple properties share the same idShort
    std::optional<nlohmann::json> fetchPropertyValue(
        const std::string &asset_id,
        const std::string &submodel_id_short,
        const std::vector<std::string> &property_path);

private:
    std::string aas_server_url_;
    std::string registry_url_;
    CURL *curl_;

    // Helper to make HTTP GET requests
    nlohmann::json makeGetRequest(const std::string &endpoint, bool use_registry = false);

    // Helper to substitute parameters in topic patterns
    std::string substituteParams(const std::string &pattern, const nlohmann::json &params);

    // Helper to fetch a schema from a URL (delegates to schema_utils)
    nlohmann::json fetchSchemaFromUrl(const std::string &schema_url);

    // Helper to recursively resolve $ref in schemas (delegates to schema_utils)
    void resolveSchemaReferences(nlohmann::json &schema);

    // Helper to encode string to base64url format (RFC 4648)
    static std::string base64url_encode(const std::string &input);

    // Helper to fetch submodel data from AAS (common logic for fetchPropertyValue overloads)
    std::optional<nlohmann::json> fetchSubmodelData(
        const std::string &asset_id,
        const std::string &submodel_id_short);

    // Recursive helper to search for property path in submodel elements
    std::optional<nlohmann::json> searchPropertyInElements(
        const nlohmann::json &elements,
        const std::vector<std::string> &property_path,
        size_t path_idx);
};
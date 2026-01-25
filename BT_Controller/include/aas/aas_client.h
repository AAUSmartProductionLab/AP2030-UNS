#pragma once

#include <string>
#include <optional>
#include <map>
#include <nlohmann/json.hpp>
#include <curl/curl.h>
#include "utils.h"

// Forward declaration
class AASInterfaceCache;

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

    // Fetch property value directly from Submodel repository using Submodel ID
    // This follows ModelReference Submodel-first pattern (AASd-123 with Submodel as first key)
    // @param submodel_id Full Submodel identifier (URL or URN)
    // @param property_path idShort-based navigation path within the submodel
    std::optional<nlohmann::json> fetchPropertyValueBySubmodelId(
        const std::string &submodel_id,
        const std::vector<std::string> &property_path);

    // Fetch property value via AAS context (AAS-first pattern)
    // This follows ModelReference with AAS as first key, Submodel ID as second
    // @param aas_id Full AAS identifier
    // @param submodel_id Full Submodel identifier OR Submodel idShort (will be resolved)
    // @param property_path idShort-based navigation path within the submodel
    std::optional<nlohmann::json> fetchPropertyValueViaAAS(
        const std::string &aas_id,
        const std::string &submodel_id,
        const std::vector<std::string> &property_path);

    // Fetch the HierarchicalStructure submodel of an asset
    std::optional<nlohmann::json> fetchHierarchicalStructure(const std::string &asset_id);

    // Fetch station position from the filling line's HierarchicalStructures
    // The station_asset_id is the full AAS ID (e.g., https://...imaDispensingSystemAAS)
    // The filling_line_asset_id is the parent line's AAS ID
    // Returns a JSON object with x, y, yaw (or theta) values
    std::optional<nlohmann::json> fetchStationPosition(
        const std::string &station_asset_id,
        const std::string &filling_line_asset_id);

    // Fetch the RequiredCapabilities submodel from a process AAS
    std::optional<nlohmann::json> fetchRequiredCapabilities(const std::string &aas_shell_id);

    // Fetch the ProcessInformation submodel from a process AAS
    std::optional<nlohmann::json> fetchProcessInformation(const std::string &aas_shell_id);

    // Fetch the BT description URL from the Policy submodel of a process AAS
    std::optional<std::string> fetchPolicyBTUrl(const std::string &aas_shell_id);

    // Fetch the shell descriptor to get the asset ID from registry
    std::optional<nlohmann::json> lookupAssetById(const std::string &asset_id);

    // Lookup AAS shell ID from asset ID using the registry
    std::optional<std::string> lookupAasIdFromAssetId(const std::string &asset_id);

    // Allow AASInterfaceCache to access private helpers for bulk fetching
    friend class AASInterfaceCache;

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

    // Helper to resolve interface reference from Variables submodel
    // Returns the actual interface name to use when the requested interaction
    // is defined as a variable with an InterfaceReference
    std::optional<std::string> resolveInterfaceReference(
        const std::string &asset_id,
        const std::string &interaction);
};
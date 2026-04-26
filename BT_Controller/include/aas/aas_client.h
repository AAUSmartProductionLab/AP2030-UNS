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

    // ------------------------------------------------------------------
    // PR2/PR3 additions: generic submodel-element access and invocation.
    // ------------------------------------------------------------------

    /// Fetch an arbitrary submodel-element by its slash-delimited idShort
    /// path within a given submodel of an asset.
    ///
    /// Example slash_path: "Capabilities/Dispense/Transformation"
    /// Returns the parsed JSON element on success, std::nullopt on failure.
    std::optional<nlohmann::json> fetchSubmodelElementByPath(
        const std::string &asset_id,
        const std::string &submodel_id_short,
        const std::string &slash_path);

    /// Invoke an AAS Operation submodel-element via its dot-delimited path.
    ///
    /// Used as the AAS-direct fallback when no Asset Interface Description
    /// is available for an action. Issues a POST to
    ///   /submodels/<base64url(submodel_id)>/submodel-elements/<dot.path>/invoke
    /// with the supplied JSON body. Returns the parsed JSON response on
    /// success, std::nullopt on failure.
    std::optional<nlohmann::json> invokeOperation(
        const std::string &asset_id,
        const std::string &submodel_id_short,
        const std::string &operation_aas_path,
        const nlohmann::json &input_json);

    /// Resolve the SkillReference embedded in an AIPlanning Action SMC into
    /// the (skills_submodel_id_short, operation_aas_path) pair that can be
    /// passed to invokeOperation. The action_aas_path is expected to be the
    /// in-AIPlanning-submodel slash path (no leading "AIPlanning/" segment).
    /// Returns std::nullopt when the SkillReference cannot be located or
    /// does not point at a SubmodelElementCollection inside the Skills
    /// submodel.
    std::optional<std::pair<std::string, std::string>> resolveSkillReference(
        const std::string &asset_id,
        const std::string &action_aas_path);

    // Allow AASInterfaceCache to access private helpers for bulk fetching
    friend class AASInterfaceCache;

private:
    std::string aas_server_url_;
    std::string registry_url_;
    CURL *curl_;

    // Helper to make HTTP GET requests
    nlohmann::json makeGetRequest(const std::string &endpoint, bool use_registry = false);

    // Helper to make HTTP POST requests with a JSON body
    nlohmann::json makePostRequest(const std::string &endpoint,
                                   const nlohmann::json &body,
                                   bool use_registry = false);

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

    // Resolve a planner-emitted action name (e.g. ``Move``, ``Transport``) to
    // the underlying ``InteractionMetadata.actions`` key by walking
    // ``AIPlanning.Domain.Actions.<name>.SkillReference`` -->
    // ``Skills.<skill>.InterfaceReference``. Returns the last key of the
    // skill's InterfaceReference (e.g. ``MoveToPosition``) on success.
    std::optional<std::string> resolveActionViaAIPlanning(
        const std::string &asset_id,
        const std::string &action_name);

    // Resolve a planner-emitted fluent name (e.g. ``Free``, ``Operational``,
    // ``ResourceAt``) to the underlying ``InteractionMetadata.properties``
    // key by parsing
    // ``AIPlanning.Domain.Fluents.<name>.Transformation`` for the first
    // ``parameter1.Variables.<X>`` reference and following
    // ``Variables.<X>.InterfaceReference``. Returns the last key of that
    // InterfaceReference (e.g. ``StationState``) on success.
    std::optional<std::string> resolveFluentViaAIPlanning(
        const std::string &asset_id,
        const std::string &fluent_name);
};
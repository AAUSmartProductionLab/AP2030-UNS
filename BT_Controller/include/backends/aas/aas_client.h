#pragma once

#include <string>
#include <optional>
#include <map>
#include <memory>
#include <nlohmann/json.hpp>
#include <curl/curl.h>
#include "utils.h"
#include "bt/execution_refs.h"

// Forward declarations
class IProtocolAidParser;
class AIDParser;
class ExecutionModelParser;
struct SkillInterface;

class AASClient
{
    friend class AIDParser;
    friend class ExecutionModelParser;

public:
    AASClient(const std::string &aas_server_url,
              const std::string &registry_url = "");
    ~AASClient();

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

    /// Fetch a submodel by its full identifier (URL form). Issues a GET to
    ///   /submodels/<base64url(submodel_id)>
    /// Returns the parsed JSON submodel on success, std::nullopt on failure.
    /// Used to dereference planner-emitted Object references whose first
    /// key is of type "Submodel" (i.e. points directly at a submodel).
    std::optional<nlohmann::json> fetchSubmodelById(const std::string &submodel_id);

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

    // ── JSONata context helpers ──────────────────────────────────
    /// Pre-fetch Parameters + Variables submodel data for each parameter
    /// ref and flatten into JSONata-friendly objects.
    std::vector<nlohmann::json> fetchParamSnapshots(
        const std::vector<bt_exec_refs::ParameterRef> &parameter_refs,
        bool include_variables,
        std::vector<std::optional<nlohmann::json>> *raw_variables = nullptr);

    /// Fetch the Constants SMC sibling of a Transformation path and
    /// flatten to ``{name: typed_value}``.
    nlohmann::json fetchSiblingConstants(
        const std::string &source_aas_id,
        const std::string &transformation_aas_path);

    // ── Submodel parser access ──────────────────────────────────
    /// Access the AID (Asset Interface Description) submodel parser.
    /// Used by SkillInterfaceCache and protocol infras for skill
    /// interface resolution and protocol parser registration.
    AIDParser &getAIDParser() { return *aid_parser_; }

    /// Register a protocol-specific AID parser.  Delegates to AIDParser.
    void registerProtocolParser(IProtocolAidParser &parser);

private:
    std::unique_ptr<AIDParser> aid_parser_;
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
};
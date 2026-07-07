#include "backends/aas/aas_client.h"
#include "backends/aas/aas_interface_cache.h"
#include "backends/aas/submodel_parsers/aid_parser.h"
#include "backends/aas/submodel_parsers/i_protocol_aid_parser.h"
#include <stdexcept>
#include <iostream>
#include <sstream>
#include <algorithm>
#include <regex>
#include <openssl/evp.h>
#include "utils.h"

namespace
{
    std::optional<std::string> lastKeyValue(const nlohmann::json &reference_element)
    {
        if (!reference_element.is_object())
            return std::nullopt;
        if (!reference_element.contains("value") || !reference_element["value"].is_object())
            return std::nullopt;
        const auto &val = reference_element["value"];
        if (!val.contains("keys") || !val["keys"].is_array() || val["keys"].empty())
            return std::nullopt;
        const auto &last = val["keys"].back();
        if (!last.contains("value") || !last["value"].is_string())
            return std::nullopt;
        return last["value"].get<std::string>();
    }
}

static size_t WriteCallback(void *contents, size_t size, size_t nmemb, void *userp)
{
    ((std::string *)userp)->append((char *)contents, size * nmemb);
    return size * nmemb;
}

// Base64url encoding helper using OpenSSL (RFC 4648)
std::string AASClient::base64url_encode(const std::string &input)
{
    // Calculate the size needed for base64 encoding (including padding)
    size_t encoded_length = 4 * ((input.length() + 2) / 3);
    std::vector<unsigned char> encoded(encoded_length + 1); // +1 for null terminator

    // Use OpenSSL's base64 encoding
    int actual_length = EVP_EncodeBlock(encoded.data(),
                                        reinterpret_cast<const unsigned char *>(input.data()),
                                        input.length());

    std::string result(reinterpret_cast<char *>(encoded.data()), actual_length);

    // Convert to base64url by replacing + with - and / with _
    std::replace(result.begin(), result.end(), '+', '-');
    std::replace(result.begin(), result.end(), '/', '_');

    // Remove padding for base64url
    result.erase(std::find(result.begin(), result.end(), '='), result.end());

    return result;
}

AASClient::AASClient(const std::string &aas_server_url, const std::string &registry_url)
    : aas_server_url_(aas_server_url),
      registry_url_(registry_url.empty() ? aas_server_url : registry_url),
      curl_(nullptr)
{
    curl_global_init(CURL_GLOBAL_DEFAULT);
    curl_ = curl_easy_init();
    aid_parser_ = std::make_unique<AIDParser>(*this);
}

AASClient::~AASClient()
{
    if (curl_)
    {
        curl_easy_cleanup(curl_);
    }
    curl_global_cleanup();
}

nlohmann::json AASClient::makeGetRequest(const std::string &endpoint, bool use_registry)
{
    if (!curl_)
    {
        throw std::runtime_error("CURL not initialized");
    }

    std::string readBuffer;
    std::string base_url = use_registry ? registry_url_ : aas_server_url_;
    std::string full_url = base_url + endpoint;

    curl_easy_setopt(curl_, CURLOPT_URL, full_url.c_str());
    curl_easy_setopt(curl_, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl_, CURLOPT_WRITEDATA, &readBuffer);
    curl_easy_setopt(curl_, CURLOPT_TIMEOUT, 10L);

    struct curl_slist *headers = nullptr;
    headers = curl_slist_append(headers, "Accept: application/json");
    curl_easy_setopt(curl_, CURLOPT_HTTPHEADER, headers);

    CURLcode res = curl_easy_perform(curl_);
    long response_code;
    curl_easy_getinfo(curl_, CURLINFO_RESPONSE_CODE, &response_code);

    curl_slist_free_all(headers);

    if (res != CURLE_OK)
    {
        throw std::runtime_error(std::string("CURL error: ") + curl_easy_strerror(res));
    }

    if (response_code != 200)
    {
        std::string error_msg = "HTTP error code: " + std::to_string(response_code) + " for URL: " + full_url;
        if (!readBuffer.empty())
        {
            error_msg += ", Response: " + readBuffer;
        }
        throw std::runtime_error(error_msg);
    }

    return nlohmann::json::parse(readBuffer);
}

std::string AASClient::substituteParams(const std::string &pattern, const nlohmann::json &params)
{
    std::string result = pattern;

    // Replace {param_name} with actual values from params JSON
    for (auto it = params.begin(); it != params.end(); ++it)
    {
        std::string placeholder = "{" + it.key() + "}";
        std::string value = it.value().is_string() ? it.value().get<std::string>() : it.value().dump();

        size_t pos = 0;
        while ((pos = result.find(placeholder, pos)) != std::string::npos)
        {
            result.replace(pos, placeholder.length(), value);
            pos += value.length();
        }
    }

    return result;
}

nlohmann::json AASClient::fetchSchemaFromUrl(const std::string &schema_url)
{
    // Use the shared utility function
    return schema_utils::fetchSchemaFromUrl(schema_url);
}

void AASClient::resolveSchemaReferences(nlohmann::json &schema)
{
    // Use the shared utility function
    schema_utils::resolveSchemaReferences(schema);
}

std::optional<nlohmann::json> AASClient::fetchPropertyValue(
    const std::string &asset_id,
    const std::string &submodel_id_short,
    const std::string &property_id_short)
{
    // Simple version: delegate to path-based version with single-element vector
    return fetchPropertyValue(asset_id, submodel_id_short, std::vector<std::string>{property_id_short});
}

std::optional<nlohmann::json> AASClient::fetchPropertyValue(
    const std::string &asset_id,
    const std::string &submodel_id_short,
    const std::vector<std::string> &property_path)
{
    try
    {
        std::cout << "Fetching property value from AAS with path - Asset: " << asset_id
                  << ", Submodel: " << submodel_id_short
                  << ", Path: [";
        for (size_t i = 0; i < property_path.size(); ++i)
        {
            std::cout << property_path[i];
            if (i < property_path.size() - 1)
                std::cout << " -> ";
        }
        std::cout << "]" << std::endl;

        // Fetch the submodel data using common helper
        auto submodel_data = fetchSubmodelData(asset_id, submodel_id_short);
        if (!submodel_data.has_value())
        {
            return std::nullopt;
        }

        // Navigate through the path to find the target property
        if (!submodel_data->contains("submodelElements") || !(*submodel_data)["submodelElements"].is_array())
        {
            std::cerr << "Submodel missing submodelElements array" << std::endl;
            return std::nullopt;
        }

        // Use the extracted recursive search method
        auto result = searchPropertyInElements((*submodel_data)["submodelElements"], property_path, 0);
        if (result.has_value())
        {
            return result;
        }

        std::cerr << "Could not find property path" << std::endl;
        return std::nullopt;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception fetching property value with path from AAS: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<nlohmann::json> AASClient::fetchSubmodelData(
    const std::string &asset_id,
    const std::string &submodel_id_short)
{
    try
    {
        // Step 1: Get the shell descriptor from registry
        std::string registry_url = "/shell-descriptors";
        nlohmann::json registry_response = makeGetRequest(registry_url, true);

        if (!registry_response.contains("result") || !registry_response["result"].is_array())
        {
            std::cerr << "Invalid registry response structure" << std::endl;
            return std::nullopt;
        }

        // Find the AAS with matching id (asset_id is the full AAS ID like https://smartproductionlab.aau.dk/aas/MIM8AAS)
        std::string shell_endpoint;
        for (const auto &shell : registry_response["result"])
        {
            // Match by full id first, then try idShort for backwards compatibility
            bool matches = false;
            if (shell.contains("id") && shell["id"].get<std::string>() == asset_id)
            {
                matches = true;
            }
            else if (shell.contains("idShort"))
            {
                // Try matching idShort for legacy support (e.g., "MIM8AAS" or adding "AAS" suffix)
                std::string id_short = shell["idShort"].get<std::string>();
                if (id_short == asset_id || asset_id.find(id_short) != std::string::npos)
                {
                    matches = true;
                }
            }

            if (matches)
            {
                if (shell.contains("endpoints") && shell["endpoints"].is_array() && !shell["endpoints"].empty())
                {
                    shell_endpoint = shell["endpoints"][0]["protocolInformation"]["href"];
                    break;
                }
            }
        }

        if (shell_endpoint.empty())
        {
            std::cerr << "Could not find shell endpoint for asset: " << asset_id << std::endl;
            return std::nullopt;
        }

        // Extract the relative path from the full URL
        size_t pos = shell_endpoint.find("/shells/");
        if (pos == std::string::npos)
        {
            std::cerr << "Invalid shell endpoint format: " << shell_endpoint << std::endl;
            return std::nullopt;
        }
        std::string shell_path = shell_endpoint.substr(pos);

        // Step 2: Get the shell to find submodel references
        nlohmann::json shell_data = makeGetRequest(shell_path);

        if (!shell_data.contains("submodels") || !shell_data["submodels"].is_array())
        {
            std::cerr << "Shell missing submodels array" << std::endl;
            return std::nullopt;
        }

        // Find the submodel reference matching the submodel_id_short
        std::string submodel_id;
        for (const auto &submodel_ref : shell_data["submodels"])
        {
            if (submodel_ref.contains("keys") && submodel_ref["keys"].is_array())
            {
                std::string ref_value = submodel_ref["keys"][0]["value"];
                if (ref_value.find(submodel_id_short) != std::string::npos)
                {
                    submodel_id = ref_value;
                    break;
                }
            }
        }

        if (submodel_id.empty())
        {
            std::cerr << "Could not find submodel with idShort: " << submodel_id_short << std::endl;
            return std::nullopt;
        }

        // Step 3: Fetch the submodel using base64url-encoded ID
        std::string submodel_id_b64 = base64url_encode(submodel_id);
        std::string submodel_url = "/submodels/" + submodel_id_b64;

        return makeGetRequest(submodel_url);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception fetching submodel data: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<nlohmann::json> AASClient::searchPropertyInElements(
    const nlohmann::json &elements,
    const std::vector<std::string> &property_path,
    size_t path_idx)
{
    if (path_idx >= property_path.size())
    {
        return std::nullopt;
    }

    const std::string &target_id_short = property_path[path_idx];
    bool is_last_element = (path_idx == property_path.size() - 1);

    // Search at current level
    for (const auto &elem : elements)
    {
        if (elem.contains("idShort") && elem["idShort"] == target_id_short)
        {
            // Found matching element
            if (is_last_element)
            {
                // This is the target property - return its value
                if (elem.contains("value") && !elem["value"].is_array())
                {
                    std::cout << "Found property at path end, value: " << elem["value"].dump() << std::endl;
                    return elem["value"];
                }
                else if (elem.contains("valueId"))
                {
                    std::cout << "Found property at path end, valueId: " << elem["valueId"].dump() << std::endl;
                    return elem["valueId"];
                }
                else if (elem.contains("value") && elem["value"].is_array())
                {
                    // Return the whole collection/element if it's an array
                    std::cout << "Found collection at path end" << std::endl;
                    return elem["value"];
                }
                else
                {
                    std::cerr << "Found element but it has no value or valueId" << std::endl;
                    return std::nullopt;
                }
            }
            else
            {
                // Not the last element - descend into nested structure
                if (elem.contains("value") && elem["value"].is_array())
                {
                    auto result = searchPropertyInElements(elem["value"], property_path, path_idx + 1);
                    if (result.has_value())
                        return result;
                }
                else if (elem.contains("statements") && elem["statements"].is_array())
                {
                    auto result = searchPropertyInElements(elem["statements"], property_path, path_idx + 1);
                    if (result.has_value())
                        return result;
                }
            }
        }
    }

    // Not found at this level - search recursively in nested structures
    for (const auto &elem : elements)
    {
        if (elem.contains("value") && elem["value"].is_array())
        {
            auto result = searchPropertyInElements(elem["value"], property_path, path_idx);
            if (result.has_value())
                return result;
        }
        else if (elem.contains("statements") && elem["statements"].is_array())
        {
            auto result = searchPropertyInElements(elem["statements"], property_path, path_idx);
            if (result.has_value())
                return result;
        }
    }

    return std::nullopt;
}

std::optional<nlohmann::json> AASClient::fetchRequiredCapabilities(const std::string &aas_shell_id)
{
    try
    {
        std::cout << "Fetching RequiredCapabilities submodel for AAS: " << aas_shell_id << std::endl;

        // Step 1: Fetch the full shell to get submodel references
        std::string encoded_id = base64url_encode(aas_shell_id);
        std::string shell_endpoint = "/shells/" + encoded_id;
        nlohmann::json shell_data = makeGetRequest(shell_endpoint);

        if (!shell_data.contains("submodels") || !shell_data["submodels"].is_array())
        {
            std::cerr << "Shell missing submodels array" << std::endl;
            return std::nullopt;
        }

        // Step 2: Find the RequiredCapabilities submodel reference
        std::string submodel_id;
        for (const auto &submodel_ref : shell_data["submodels"])
        {
            if (submodel_ref.contains("keys") && submodel_ref["keys"].is_array())
            {
                std::string ref_value = submodel_ref["keys"][0]["value"];
                if (ref_value.find("RequiredCapabilities") != std::string::npos)
                {
                    submodel_id = ref_value;
                    break;
                }
            }
        }

        if (submodel_id.empty())
        {
            std::cerr << "RequiredCapabilities submodel reference not found for AAS: " << aas_shell_id << std::endl;
            return std::nullopt;
        }

        std::cout << "Found RequiredCapabilities submodel reference: " << submodel_id << std::endl;

        // Step 3: Fetch the submodel using base64url-encoded ID
        std::string submodel_id_b64 = base64url_encode(submodel_id);
        std::string submodel_url = "/submodels/" + submodel_id_b64;

        nlohmann::json submodel_data = makeGetRequest(submodel_url);
        std::cout << "Successfully fetched RequiredCapabilities submodel" << std::endl;

        return submodel_data;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error fetching RequiredCapabilities: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<nlohmann::json> AASClient::fetchProcessInformation(const std::string &aas_shell_id)
{
    try
    {
        std::cout << "Fetching ProcessInformation submodel for AAS: " << aas_shell_id << std::endl;

        // Step 1: Fetch the full shell to get submodel references
        std::string encoded_id = base64url_encode(aas_shell_id);
        std::string shell_endpoint = "/shells/" + encoded_id;
        nlohmann::json shell_data = makeGetRequest(shell_endpoint);

        if (!shell_data.contains("submodels") || !shell_data["submodels"].is_array())
        {
            std::cerr << "Shell missing submodels array" << std::endl;
            return std::nullopt;
        }

        // Step 2: Find the ProcessInformation submodel reference
        std::string submodel_id;
        for (const auto &submodel_ref : shell_data["submodels"])
        {
            if (submodel_ref.contains("keys") && submodel_ref["keys"].is_array())
            {
                std::string ref_value = submodel_ref["keys"][0]["value"];
                if (ref_value.find("ProcessInformation") != std::string::npos)
                {
                    submodel_id = ref_value;
                    break;
                }
            }
        }

        if (submodel_id.empty())
        {
            std::cerr << "ProcessInformation submodel reference not found for AAS: " << aas_shell_id << std::endl;
            return std::nullopt;
        }

        std::cout << "Found ProcessInformation submodel reference: " << submodel_id << std::endl;

        // Step 3: Fetch the submodel using base64url-encoded ID
        std::string submodel_id_b64 = base64url_encode(submodel_id);
        std::string submodel_url = "/submodels/" + submodel_id_b64;

        nlohmann::json submodel_data = makeGetRequest(submodel_url);
        std::cout << "Successfully fetched ProcessInformation submodel" << std::endl;

        return submodel_data;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error fetching ProcessInformation: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<std::string> AASClient::fetchPolicyBTUrl(const std::string &aas_shell_id)
{
    try
    {
        std::cout << "Fetching Policy submodel for AAS: " << aas_shell_id << std::endl;

        // Step 1: Fetch the full shell to get submodel references
        std::string encoded_id = base64url_encode(aas_shell_id);
        std::string shell_endpoint = "/shells/" + encoded_id;
        nlohmann::json shell_data = makeGetRequest(shell_endpoint);

        if (!shell_data.contains("submodels") || !shell_data["submodels"].is_array())
        {
            std::cerr << "Shell missing submodels array" << std::endl;
            return std::nullopt;
        }

        // Step 2: Find the Policy submodel reference
        std::string submodel_id;
        for (const auto &submodel_ref : shell_data["submodels"])
        {
            if (submodel_ref.contains("keys") && submodel_ref["keys"].is_array())
            {
                std::string ref_value = submodel_ref["keys"][0]["value"];
                if (ref_value.find("Policy") != std::string::npos)
                {
                    submodel_id = ref_value;
                    break;
                }
            }
        }

        if (submodel_id.empty())
        {
            std::cerr << "Policy submodel reference not found for AAS: " << aas_shell_id << std::endl;
            return std::nullopt;
        }

        std::cout << "Found Policy submodel reference: " << submodel_id << std::endl;

        // Step 3: Fetch the submodel using base64url-encoded ID
        std::string submodel_id_b64 = base64url_encode(submodel_id);
        std::string submodel_url = "/submodels/" + submodel_id_b64;

        nlohmann::json submodel_data = makeGetRequest(submodel_url);

        // Step 4: Navigate through submodel to find the Policy element with File property
        // Structure: Policy submodel -> submodelElements -> Policy (SMC) -> value -> File
        if (!submodel_data.contains("submodelElements") || !submodel_data["submodelElements"].is_array())
        {
            std::cerr << "Policy submodel missing submodelElements array" << std::endl;
            return std::nullopt;
        }

        for (const auto &element : submodel_data["submodelElements"])
        {
            if (!element.contains("idShort"))
                continue;

            std::string id_short = element["idShort"].get<std::string>();
            std::string model_type = element.value("modelType", "");

            // Check for File type element (AAS File element with modelType: "File")
            // The File element can have any idShort (commonly "Policy" or "File")
            if (model_type == "File" && element.contains("value"))
            {
                std::string bt_url = element["value"].get<std::string>();
                std::cout << "Found BT description URL in File element '" << id_short << "': " << bt_url << std::endl;
                return bt_url;
            }

            // Also check for SubmodelElementCollection containing a File element
            if (model_type == "SubmodelElementCollection" &&
                element.contains("value") && element["value"].is_array())
            {
                for (const auto &nested_elem : element["value"])
                {
                    std::string nested_model_type = nested_elem.value("modelType", "");
                    if (nested_model_type == "File" && nested_elem.contains("value"))
                    {
                        std::string bt_url = nested_elem["value"].get<std::string>();
                        std::cout << "Found BT description URL in nested File element: " << bt_url << std::endl;
                        return bt_url;
                    }
                }
            }
        }

        std::cerr << "Could not find File property in Policy submodel" << std::endl;
        return std::nullopt;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error fetching Policy BT URL: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<nlohmann::json> AASClient::lookupAssetById(const std::string &asset_id)
{
    try
    {
        std::string encoded_id = base64url_encode(asset_id);
        std::string endpoint = "/shell-descriptors/" + encoded_id;
        nlohmann::json response = makeGetRequest(endpoint, true);
        return response;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error looking up asset: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<std::string> AASClient::lookupAasIdFromAssetId(const std::string &asset_id)
{
    try
    {
        std::cout << "Looking up AAS shell ID for asset: " << asset_id << std::endl;

        // Query the registry for all shell descriptors
        std::string endpoint = "/shell-descriptors";
        nlohmann::json response = makeGetRequest(endpoint, true);

        if (!response.contains("result") || !response["result"].is_array())
        {
            std::cerr << "Invalid response from registry" << std::endl;
            return std::nullopt;
        }

        // Search for shell with matching globalAssetId
        // In the registry response, globalAssetId is directly in the shell descriptor
        for (const auto &shell_descriptor : response["result"])
        {
            if (shell_descriptor.contains("globalAssetId") &&
                shell_descriptor["globalAssetId"].get<std::string>() == asset_id)
            {
                if (shell_descriptor.contains("id"))
                {
                    std::string shell_id = shell_descriptor["id"].get<std::string>();
                    std::cout << "  ✓ Found matching AAS shell ID: " << shell_id << std::endl;
                    return shell_id;
                }
            }
        }

        std::cerr << "No AAS shell found for asset ID: " << asset_id << std::endl;
        return std::nullopt;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error looking up AAS ID from asset ID: " << e.what() << std::endl;
        return std::nullopt;
    }
}

// ---------------------------------------------------------------------------
// PR2/PR3 additions
// ---------------------------------------------------------------------------

nlohmann::json AASClient::makePostRequest(const std::string &endpoint,
                                          const nlohmann::json &body,
                                          bool use_registry)
{
    if (!curl_)
    {
        throw std::runtime_error("CURL not initialized");
    }

    std::string readBuffer;
    std::string base_url = use_registry ? registry_url_ : aas_server_url_;
    std::string full_url = base_url + endpoint;
    std::string body_str = body.dump();

    // Reset CURL handle state from any prior GET configuration that would
    // otherwise leak into this POST.
    curl_easy_setopt(curl_, CURLOPT_URL, full_url.c_str());
    curl_easy_setopt(curl_, CURLOPT_POST, 1L);
    curl_easy_setopt(curl_, CURLOPT_POSTFIELDS, body_str.c_str());
    curl_easy_setopt(curl_, CURLOPT_POSTFIELDSIZE, static_cast<long>(body_str.size()));
    curl_easy_setopt(curl_, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl_, CURLOPT_WRITEDATA, &readBuffer);
    curl_easy_setopt(curl_, CURLOPT_TIMEOUT, 30L);

    struct curl_slist *headers = nullptr;
    headers = curl_slist_append(headers, "Accept: application/json");
    headers = curl_slist_append(headers, "Content-Type: application/json");
    curl_easy_setopt(curl_, CURLOPT_HTTPHEADER, headers);

    CURLcode res = curl_easy_perform(curl_);
    long response_code = 0;
    curl_easy_getinfo(curl_, CURLINFO_RESPONSE_CODE, &response_code);

    curl_slist_free_all(headers);

    // Reset POST flag so subsequent makeGetRequest calls behave correctly.
    curl_easy_setopt(curl_, CURLOPT_POST, 0L);
    curl_easy_setopt(curl_, CURLOPT_POSTFIELDS, nullptr);

    if (res != CURLE_OK)
    {
        throw std::runtime_error(std::string("CURL error: ") + curl_easy_strerror(res));
    }

    if (response_code < 200 || response_code >= 300)
    {
        std::string error_msg = "HTTP error code: " + std::to_string(response_code) +
                                " for POST URL: " + full_url;
        if (!readBuffer.empty())
        {
            error_msg += ", Response: " + readBuffer;
        }
        throw std::runtime_error(error_msg);
    }

    if (readBuffer.empty())
    {
        return nlohmann::json::object();
    }
    return nlohmann::json::parse(readBuffer);
}

namespace
{
    // Convert a slash-delimited idShort path ("Capabilities/Dispense/Transformation")
    // to the dot-delimited form expected by the AAS submodel-elements endpoint.
    std::string slashToDotPath(const std::string &slash_path)
    {
        std::string dot_path = slash_path;
        // Strip leading slashes
        while (!dot_path.empty() && dot_path.front() == '/')
        {
            dot_path.erase(dot_path.begin());
        }
        // Strip trailing slashes
        while (!dot_path.empty() && dot_path.back() == '/')
        {
            dot_path.pop_back();
        }
        std::replace(dot_path.begin(), dot_path.end(), '/', '.');
        return dot_path;
    }
}

std::optional<nlohmann::json> AASClient::fetchSubmodelById(const std::string &submodel_id)
{
    try
    {
        if (submodel_id.empty())
        {
            return std::nullopt;
        }
        std::string sm_b64 = base64url_encode(submodel_id);
        nlohmann::json result = makeGetRequest("/submodels/" + sm_b64);
        if (result.is_null())
        {
            return std::nullopt;
        }
        return result;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception fetching submodel by id '" << submodel_id
                  << "': " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<nlohmann::json> AASClient::fetchSubmodelElementByPath(
    const std::string &asset_id,
    const std::string &submodel_id_short,
    const std::string &slash_path)
{
    try
    {
        auto submodel_data = fetchSubmodelData(asset_id, submodel_id_short);
        if (!submodel_data.has_value())
        {
            std::cerr << "fetchSubmodelElementByPath: could not load submodel '"
                      << submodel_id_short << "' for asset '" << asset_id << "'" << std::endl;
            return std::nullopt;
        }

        // Walk the slash path through the in-memory submodel structure.
        // This avoids an extra round trip and works against any AAS server
        // that returns a fully-expanded submodel from /submodels/<id>.
        std::string normalized = slash_path;
        while (!normalized.empty() && normalized.front() == '/')
        {
            normalized.erase(normalized.begin());
        }
        while (!normalized.empty() && normalized.back() == '/')
        {
            normalized.pop_back();
        }
        if (normalized.empty())
        {
            return submodel_data;
        }

        std::vector<std::string> segments;
        std::string current;
        for (char c : normalized)
        {
            if (c == '/')
            {
                if (!current.empty())
                {
                    segments.push_back(current);
                    current.clear();
                }
            }
            else
            {
                current.push_back(c);
            }
        }
        if (!current.empty())
        {
            segments.push_back(current);
        }

        const nlohmann::json *cursor = &(*submodel_data);
        if (!cursor->contains("submodelElements") || !(*cursor)["submodelElements"].is_array())
        {
            std::cerr << "fetchSubmodelElementByPath: submodel has no submodelElements" << std::endl;
            return std::nullopt;
        }
        const nlohmann::json *elements = &(*cursor)["submodelElements"];
        const nlohmann::json *match = nullptr;

        for (size_t i = 0; i < segments.size(); ++i)
        {
            const std::string &segment = segments[i];
            match = nullptr;
            if (!elements->is_array())
            {
                std::cerr << "fetchSubmodelElementByPath: expected array at segment '"
                          << segment << "'" << std::endl;
                return std::nullopt;
            }
            // First pass: match by idShort (covers SMC children).
            for (const auto &elem : *elements)
            {
                if (elem.contains("idShort") && elem["idShort"] == segment)
                {
                    match = &elem;
                    break;
                }
            }
            // Second pass: SubmodelElementList children carry no idShort,
            // only a displayName[].text (and they live in a list whose
            // ordering can also be indexed positionally). Match either.
            if (match == nullptr)
            {
                for (const auto &elem : *elements)
                {
                    if (elem.contains("displayName") && elem["displayName"].is_array())
                    {
                        for (const auto &dn : elem["displayName"])
                        {
                            if (dn.contains("text") && dn["text"].is_string() &&
                                dn["text"].get<std::string>() == segment)
                            {
                                match = &elem;
                                break;
                            }
                        }
                        if (match != nullptr)
                            break;
                    }
                }
            }
            if (match == nullptr && !segment.empty() &&
                std::all_of(segment.begin(), segment.end(),
                            [](unsigned char c)
                            { return std::isdigit(c); }))
            {
                size_t idx = static_cast<size_t>(std::stoul(segment));
                if (idx < elements->size())
                {
                    match = &(*elements)[idx];
                }
            }
            if (match == nullptr)
            {
                std::cerr << "fetchSubmodelElementByPath: segment '" << segment
                          << "' not found in path '" << slash_path << "'" << std::endl;
                return std::nullopt;
            }
            if (i + 1 < segments.size())
            {
                if (!match->contains("value") || !(*match)["value"].is_array())
                {
                    std::cerr << "fetchSubmodelElementByPath: cannot descend past '"
                              << segment << "'" << std::endl;
                    return std::nullopt;
                }
                elements = &(*match)["value"];
            }
        }

        if (match == nullptr)
        {
            return std::nullopt;
        }
        return *match;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception in fetchSubmodelElementByPath: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<nlohmann::json> AASClient::invokeOperation(
    const std::string &asset_id,
    const std::string &submodel_id_short,
    const std::string &operation_aas_path,
    const nlohmann::json &input_json)
{
    try
    {
        // Resolve the submodel id for this asset by reusing the existing
        // shell-descriptor lookup logic (which already handles the registry).
        // We re-walk the registry just to obtain the full submodel id.
        std::string registry_url = "/shell-descriptors";
        nlohmann::json registry_response = makeGetRequest(registry_url, true);
        if (!registry_response.contains("result") || !registry_response["result"].is_array())
        {
            std::cerr << "invokeOperation: invalid registry response" << std::endl;
            return std::nullopt;
        }

        std::string shell_path;
        for (const auto &shell : registry_response["result"])
        {
            bool matches = false;
            if (shell.contains("id") && shell["id"].get<std::string>() == asset_id)
            {
                matches = true;
            }
            else if (shell.contains("idShort"))
            {
                std::string id_short = shell["idShort"].get<std::string>();
                if (id_short == asset_id || asset_id.find(id_short) != std::string::npos)
                {
                    matches = true;
                }
            }
            if (matches && shell.contains("endpoints") && shell["endpoints"].is_array() &&
                !shell["endpoints"].empty())
            {
                std::string ep = shell["endpoints"][0]["protocolInformation"]["href"];
                size_t pos = ep.find("/shells/");
                if (pos != std::string::npos)
                {
                    shell_path = ep.substr(pos);
                }
                break;
            }
        }
        if (shell_path.empty())
        {
            std::cerr << "invokeOperation: shell endpoint not found for asset '" << asset_id << "'" << std::endl;
            return std::nullopt;
        }

        nlohmann::json shell_data = makeGetRequest(shell_path);
        std::string submodel_id;
        if (shell_data.contains("submodels") && shell_data["submodels"].is_array())
        {
            for (const auto &submodel_ref : shell_data["submodels"])
            {
                if (submodel_ref.contains("keys") && submodel_ref["keys"].is_array())
                {
                    std::string ref_value = submodel_ref["keys"][0]["value"];
                    if (ref_value.find(submodel_id_short) != std::string::npos)
                    {
                        submodel_id = ref_value;
                        break;
                    }
                }
            }
        }
        if (submodel_id.empty())
        {
            std::cerr << "invokeOperation: submodel '" << submodel_id_short
                      << "' not found on asset '" << asset_id << "'" << std::endl;
            return std::nullopt;
        }

        std::string submodel_id_b64 = base64url_encode(submodel_id);
        std::string dot_path = slashToDotPath(operation_aas_path);
        std::string endpoint =
            "/submodels/" + submodel_id_b64 +
            "/submodel-elements/" + dot_path + "/invoke";

        // BaSyx expects an InvocationRequest envelope. We send a minimal
        // envelope that exposes the caller-supplied JSON as the operation
        // input arguments. Concrete servers may ignore additional fields.
        nlohmann::json envelope = {
            {"requestId", ""},
            {"timeout", 30000},
            {"inoutputArguments", nlohmann::json::array()},
            {"inputArguments", nlohmann::json::array({{{"value", input_json}}})}};

        std::cout << "invokeOperation POST " << endpoint << std::endl;
        return makePostRequest(endpoint, envelope);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception in invokeOperation: " << e.what() << std::endl;
        return std::nullopt;
    }
}

// ── JSONata context helpers ──────────────────────────────────────────

namespace
{
    nlohmann::json coerceProperty(const nlohmann::json &elem)
    {
        if (!elem.contains("value"))
            return nlohmann::json(nullptr);
        const auto &raw = elem["value"];
        if (!raw.is_string())
            return raw;
        const std::string s = raw.get<std::string>();
        std::string vt = elem.value("valueType", "");
        try
        {
            if (vt == "xs:boolean")
                return s == "true" || s == "1";
            if (vt == "xs:integer" || vt == "xs:int" || vt == "xs:long" ||
                vt == "xs:short" || vt == "xs:byte" ||
                vt == "xs:nonNegativeInteger" || vt == "xs:positiveInteger" ||
                vt == "xs:unsignedInt" || vt == "xs:unsignedLong")
                return std::stoll(s);
            if (vt == "xs:double" || vt == "xs:float" || vt == "xs:decimal")
                return std::stod(s);
        }
        catch (const std::exception &)
        {
        }
        if (!s.empty() && (s.front() == '[' || s.front() == '{'))
        {
            try
            {
                return nlohmann::json::parse(s);
            }
            catch (const std::exception &)
            {
            }
        }
        return s;
    }

    nlohmann::json flattenAasElement(const nlohmann::json &elem)
    {
        if (!elem.is_object())
            return elem;
        const std::string mt = elem.value("modelType", "");
        if (mt == "Property")
            return coerceProperty(elem);
        if (mt == "SubmodelElementList")
        {
            nlohmann::json out = nlohmann::json::array();
            if (elem.contains("value") && elem["value"].is_array())
                for (const auto &child : elem["value"])
                    out.push_back(flattenAasElement(child));
            return out;
        }
        if (elem.contains("submodelElements") && elem["submodelElements"].is_array())
        {
            nlohmann::json out = nlohmann::json::object();
            for (const auto &child : elem["submodelElements"])
                if (child.is_object() && child.contains("idShort"))
                    out[child["idShort"].get<std::string>()] = flattenAasElement(child);
            return out;
        }
        if (elem.contains("value") && elem["value"].is_array())
        {
            if (mt == "SubmodelElementCollection" && elem["value"].size() == 1)
            {
                const auto &only = elem["value"][0];
                if (only.is_object() && only.value("modelType", "") == "Property" &&
                    only.value("idShort", "") == "value")
                    return coerceProperty(only);
            }
            nlohmann::json out = nlohmann::json::object();
            for (const auto &child : elem["value"])
                if (child.is_object() && child.contains("idShort"))
                    out[child["idShort"].get<std::string>()] = flattenAasElement(child);
            return out;
        }
        if (elem.contains("value"))
            return elem["value"];
        return nlohmann::json(nullptr);
    }

    std::string parentSlashPath(const std::string &slash_path)
    {
        if (slash_path.empty())
            return slash_path;
        auto pos = slash_path.find_last_of('/');
        return pos == std::string::npos ? std::string() : slash_path.substr(0, pos);
    }
} // anonymous namespace

std::vector<nlohmann::json> AASClient::fetchParamSnapshots(
    const std::vector<bt_exec_refs::ParameterRef> &parameter_refs,
    bool include_variables,
    std::vector<std::optional<nlohmann::json>> *raw_variables)
{
    std::vector<nlohmann::json> params;
    params.reserve(parameter_refs.size());
    if (raw_variables)
    {
        raw_variables->clear();
        raw_variables->reserve(parameter_refs.size());
    }
    for (const auto &p : parameter_refs)
    {
        nlohmann::json snapshot = nlohmann::json::object();
        std::optional<nlohmann::json> vars_raw;
        if (p.aas_id.empty())
        {
            params.push_back(std::move(snapshot));
            if (raw_variables)
                raw_variables->push_back(std::nullopt);
            continue;
        }

        auto [submodel, remainder] = bt_exec_refs::splitSubmodelPath(p.aas_path);
        if (submodel.empty())
        {
            submodel = "AIPlanning";
            remainder = p.aas_path;
        }
        auto object_smc = fetchSubmodelElementByPath(p.aas_id, submodel, remainder);

        std::string ref_type, ref_value;
        if (object_smc.has_value() && object_smc->is_object() &&
            object_smc->value("modelType", "") == "ReferenceElement" &&
            object_smc->contains("value") && (*object_smc)["value"].is_object())
        {
            const auto &v = (*object_smc)["value"];
            if (v.contains("keys") && v["keys"].is_array() && !v["keys"].empty())
            {
                ref_type = v["keys"][0].value("type", "");
                ref_value = v["keys"][0].value("value", "");
            }
        }

        std::optional<nlohmann::json> params_sm;
        if (ref_type == "AssetAdministrationShell" && !ref_value.empty())
        {
            params_sm = fetchSubmodelElementByPath(ref_value, "Parameters", "");
            if (include_variables)
                vars_raw = fetchSubmodelElementByPath(ref_value, "Variables", "");
        }
        else if (ref_type == "Submodel" && !ref_value.empty())
        {
            params_sm = fetchSubmodelById(ref_value);
        }
        else
        {
            params_sm = fetchSubmodelElementByPath(p.aas_id, "Parameters", "");
            if (include_variables)
                vars_raw = fetchSubmodelElementByPath(p.aas_id, "Variables", "");
        }

        if (params_sm.has_value())
            snapshot["Parameters"] = flattenAasElement(*params_sm);
        if (include_variables && vars_raw.has_value())
            snapshot["Variables"] = flattenAasElement(*vars_raw);
        params.push_back(std::move(snapshot));
        if (raw_variables)
            raw_variables->push_back(std::move(vars_raw));
    }
    return params;
}

nlohmann::json AASClient::fetchSiblingConstants(
    const std::string &source_aas_id,
    const std::string &transformation_aas_path)
{
    nlohmann::json constants = nlohmann::json::object();
    if (source_aas_id.empty() || transformation_aas_path.empty())
        return constants;

    auto [submodel, remainder] = bt_exec_refs::splitSubmodelPath(transformation_aas_path);
    if (submodel.empty())
    {
        submodel = "AIPlanning";
        remainder = transformation_aas_path;
    }
    const std::string parent_remainder = parentSlashPath(remainder);
    if (parent_remainder.empty())
        return constants;

    auto constants_smc = fetchSubmodelElementByPath(source_aas_id, submodel, parent_remainder + "/Constants");
    if (constants_smc.has_value())
        constants = flattenAasElement(*constants_smc);
    return constants;
}

// ── Submodel parser delegation ───────────────────────────────────────

void AASClient::registerProtocolParser(IProtocolAidParser &parser)
{
    aid_parser_->registerProtocolParser(parser);
}

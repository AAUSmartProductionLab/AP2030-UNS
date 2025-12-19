#include "aas/aas_client.h"
#include <stdexcept>
#include <iostream>
#include <sstream>
#include <algorithm>
#include <openssl/evp.h>
#include "utils.h"

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

std::optional<mqtt_utils::Topic> AASClient::fetchInterface(const std::string &asset_id, const std::string &interaction, const std::string &endpoint)
{
    try
    {
        std::cout << "Fetching interface from AAS - Asset: " << asset_id
                  << ", Interaction: " << interaction
                  << ", Endpoint: " << endpoint << std::endl;

        // Validate endpoint parameter
        if (endpoint != "input" && endpoint != "output")
        {
            std::cerr << "Invalid endpoint type: " << endpoint << ". Must be 'input' or 'output'" << std::endl;
            return std::nullopt;
        }

        std::string shell_id_b64 = base64url_encode(asset_id);
        std::string shell_path = "/shells/" + shell_id_b64;

        // Step 2: Get the shell to find submodel references
        nlohmann::json shell_data = makeGetRequest(shell_path);

        if (!shell_data.contains("submodels") || !shell_data["submodels"].is_array())
        {
            std::cerr << "Shell missing submodels array" << std::endl;
            return std::nullopt;
        }

        // Find AssetInterfacesDescription submodel reference
        std::string submodel_id;
        for (const auto &submodel_ref : shell_data["submodels"])
        {
            if (submodel_ref.contains("keys") && submodel_ref["keys"].is_array())
            {
                std::string ref_value = submodel_ref["keys"][0]["value"];
                if (ref_value.find("AssetInterfacesDescription") != std::string::npos ||
                    ref_value.find("AssetInterfaceDescription") != std::string::npos)
                {
                    submodel_id = ref_value;
                    break;
                }
            }
        }

        if (submodel_id.empty())
        {
            std::cerr << "Could not find AssetInterfacesDescription submodel" << std::endl;
            return std::nullopt;
        }

        std::cout << "Found submodel ID: " << submodel_id << std::endl;

        // Step 3: Fetch the submodel using base64url-encoded ID
        // AAS specification requires base64url encoding for IDs in URLs
        std::string submodel_id_b64 = base64url_encode(submodel_id);

        std::string submodel_url = "/submodels/" + submodel_id_b64;
        std::cout << "Fetching submodel from URL: " << submodel_url << std::endl;

        nlohmann::json submodel_data = makeGetRequest(submodel_url);

        // Step 4: Navigate through the submodel structure
        if (!submodel_data.contains("submodelElements") || !submodel_data["submodelElements"].is_array())
        {
            std::cerr << "Submodel missing submodelElements array" << std::endl;
            return std::nullopt;
        }

        // Find InterfaceMQTT
        nlohmann::json interface_mqtt;
        for (const auto &elem : submodel_data["submodelElements"])
        {
            if (elem.contains("idShort") && elem["idShort"] == "InterfaceMQTT")
            {
                interface_mqtt = elem;
                break;
            }
        }

        if (interface_mqtt.empty())
        {
            std::cerr << "Could not find InterfaceMQTT element" << std::endl;
            return std::nullopt;
        }

        // Get base topic from EndpointMetadata
        std::string base_topic;
        for (const auto &elem : interface_mqtt["value"])
        {
            if (elem["idShort"] == "EndpointMetadata")
            {
                for (const auto &metadata_elem : elem["value"])
                {
                    if (metadata_elem["idShort"] == "base")
                    {
                        base_topic = metadata_elem["value"];
                        // Remove mqtt:// or mqtts:// prefix if present
                        if (base_topic.find("mqtts://") == 0)
                        {
                            base_topic = base_topic.substr(8); // Remove "mqtts://"
                            // Remove host:port, keep only topic path
                            size_t slash_pos = base_topic.find('/');
                            if (slash_pos != std::string::npos)
                            {
                                base_topic = base_topic.substr(slash_pos);
                            }
                        }
                        else if (base_topic.find("mqtt://") == 0)
                        {
                            base_topic = base_topic.substr(7); // Remove "mqtt://"
                            // Remove host:port, keep only topic path
                            size_t slash_pos = base_topic.find('/');
                            if (slash_pos != std::string::npos)
                            {
                                base_topic = base_topic.substr(slash_pos);
                            }
                        }
                        break;
                    }
                }
                break;
            }
        }

        // Step 5: Find InteractionMetadata and locate the interaction (action or property)
        nlohmann::json interaction_data;
        bool is_action = false;

        for (const auto &elem : interface_mqtt["value"])
        {
            if (elem["idShort"] == "InteractionMetadata")
            {
                // Search in actions first
                for (const auto &interaction_type_elem : elem["value"])
                {
                    if (interaction_type_elem["idShort"] == "actions")
                    {
                        for (const auto &action : interaction_type_elem["value"])
                        {
                            if (action["idShort"] == interaction)
                            {
                                interaction_data = action;
                                is_action = true;
                                break;
                            }
                        }
                    }
                    else if (interaction_type_elem["idShort"] == "properties")
                    {
                        for (const auto &property : interaction_type_elem["value"])
                        {
                            if (property["idShort"] == interaction)
                            {
                                interaction_data = property;
                                is_action = false;
                                break;
                            }
                        }
                    }

                    if (!interaction_data.empty())
                        break;
                }
                break;
            }
        }

        if (interaction_data.empty())
        {
            std::cerr << "Could not find interaction: " << interaction << std::endl;
            return std::nullopt;
        }

        std::cout << "Found interaction: " << interaction << " (Type: "
                  << (is_action ? "action" : "property") << ")" << std::endl;

        // Step 6: Extract schema URL and forms data
        nlohmann::json forms_data;
        std::string schema_url;

        for (const auto &elem : interaction_data["value"])
        {
            if (elem["idShort"] == "forms")
            {
                forms_data = elem;
            }
            // Get schema URL based on endpoint type
            else if (endpoint == "input" && elem["idShort"] == "input" && elem["modelType"] == "File")
            {
                schema_url = elem["value"];
            }
            else if (endpoint == "output" && elem["idShort"] == "output" && elem["modelType"] == "File")
            {
                schema_url = elem["value"];
            }
        }

        if (forms_data.empty())
        {
            std::cerr << "Could not find forms in interaction" << std::endl;
            return std::nullopt;
        }

        // Step 7: Parse forms to extract topic information
        std::string href;
        int qos = 0;
        bool retain = false;

        // First, extract default values from the main forms data
        for (const auto &form_elem : forms_data["value"])
        {
            if (form_elem["idShort"] == "href")
            {
                href = form_elem["value"].get<std::string>();
            }
            else if (form_elem["idShort"] == "mqv_qos")
            {
                // Handle both int and string representations
                if (form_elem["value"].is_number())
                {
                    qos = form_elem["value"].get<int>();
                }
                else if (form_elem["value"].is_string())
                {
                    qos = std::stoi(form_elem["value"].get<std::string>());
                }
            }
            else if (form_elem["idShort"] == "mqv_retain")
            {
                // Handle both bool and string representations
                if (form_elem["value"].is_boolean())
                {
                    retain = form_elem["value"].get<bool>();
                }
                else if (form_elem["value"].is_string())
                {
                    std::string val = form_elem["value"].get<std::string>();
                    retain = (val == "true" || val == "True" || val == "TRUE" || val == "1");
                }
            }
        }

        // For actions with output endpoint, check if there's a specific response form
        if (is_action && endpoint == "output")
        {
            for (const auto &form_elem : forms_data["value"])
            {
                if (form_elem["idShort"] == "response" && form_elem["modelType"] == "SubmodelElementCollection")
                {
                    std::cout << "Found specific response form, overriding default values" << std::endl;

                    // Override with response-specific values
                    for (const auto &resp_elem : form_elem["value"])
                    {
                        if (resp_elem["idShort"] == "href")
                        {
                            href = resp_elem["value"].get<std::string>();
                        }
                        else if (resp_elem["idShort"] == "mqv_qos")
                        {
                            if (resp_elem["value"].is_number())
                            {
                                qos = resp_elem["value"].get<int>();
                            }
                            else if (resp_elem["value"].is_string())
                            {
                                qos = std::stoi(resp_elem["value"].get<std::string>());
                            }
                        }
                        else if (resp_elem["idShort"] == "mqv_retain")
                        {
                            if (resp_elem["value"].is_boolean())
                            {
                                retain = resp_elem["value"].get<bool>();
                            }
                            else if (resp_elem["value"].is_string())
                            {
                                std::string val = resp_elem["value"].get<std::string>();
                                retain = (val == "true" || val == "True" || val == "TRUE" || val == "1");
                            }
                        }
                    }
                    break;
                }
            }
        }

        if (href.empty())
        {
            std::cerr << "Could not extract href from forms for endpoint: " << endpoint << std::endl;
            return std::nullopt;
        }

        // Construct full topic path
        std::string full_topic = base_topic + href;

        // Step 8: Fetch the JSON schema from URL
        nlohmann::json schema;
        if (!schema_url.empty())
        {
            // Use the cached fetchSchemaFromUrl method which already handles HTTP requests
            schema = fetchSchemaFromUrl(schema_url);

            if (!schema.empty())
            {
                // Resolve any $ref references in the schema
                resolveSchemaReferences(schema);
                std::cout << "Successfully fetched and resolved schema" << std::endl;
            }
        }

        std::cout << "Successfully fetched interface - Topic: " << full_topic
                  << ", QoS: " << qos << ", Retain: " << retain << std::endl;

        return mqtt_utils::Topic(full_topic, schema, qos, retain);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Failed to fetch interface from AAS for asset: " << asset_id
                  << ", interaction: " << interaction
                  << ", endpoint: " << endpoint
                  << " - Error: " << e.what() << std::endl;
        return std::nullopt;
    }
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

        // Find the AAS with matching idShort
        std::string expected_id_short = asset_id + "AAS";
        std::string shell_endpoint;
        for (const auto &shell : registry_response["result"])
        {
            if (shell.contains("idShort") && shell["idShort"] == expected_id_short)
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

std::optional<nlohmann::json> AASClient::fetchHierarchicalStructure(const std::string &aas_shell_id)
{
    try
    {
        std::cout << "Fetching HierarchicalStructures submodel for AAS: " << aas_shell_id << std::endl;

        // Step 1: Fetch the full shell to get submodel references
        std::string encoded_id = base64url_encode(aas_shell_id);
        std::string shell_endpoint = "/shells/" + encoded_id;
        nlohmann::json shell_data = makeGetRequest(shell_endpoint);

        if (!shell_data.contains("submodels") || !shell_data["submodels"].is_array())
        {
            std::cerr << "Shell missing submodels array" << std::endl;
            return std::nullopt;
        }

        // Step 2: Find the HierarchicalStructures submodel reference
        std::string submodel_id;
        for (const auto &submodel_ref : shell_data["submodels"])
        {
            if (submodel_ref.contains("keys") && submodel_ref["keys"].is_array())
            {
                std::string ref_value = submodel_ref["keys"][0]["value"];
                if (ref_value.find("HierarchicalStructures") != std::string::npos)
                {
                    submodel_id = ref_value;
                    break;
                }
            }
        }

        if (submodel_id.empty())
        {
            std::cerr << "HierarchicalStructures submodel reference not found for AAS: " << aas_shell_id << std::endl;
            return std::nullopt;
        }

        std::cout << "Found HierarchicalStructures submodel reference: " << submodel_id << std::endl;

        // Step 3: Fetch the submodel using base64url-encoded ID
        std::string submodel_id_b64 = base64url_encode(submodel_id);
        std::string submodel_url = "/submodels/" + submodel_id_b64;

        nlohmann::json submodel_data = makeGetRequest(submodel_url);
        std::cout << "Successfully fetched HierarchicalStructures submodel" << std::endl;

        return submodel_data;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error fetching HierarchicalStructures: " << e.what() << std::endl;
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

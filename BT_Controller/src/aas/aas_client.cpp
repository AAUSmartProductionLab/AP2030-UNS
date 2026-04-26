#include "aas/aas_client.h"
#include <stdexcept>
#include <iostream>
#include <sstream>
#include <algorithm>
#include <regex>
#include <openssl/evp.h>
#include "utils.h"

namespace
{
    // Case-insensitive string comparison helper
    std::string toLower(const std::string &s)
    {
        std::string result = s;
        std::transform(result.begin(), result.end(), result.begin(),
                       [](unsigned char c)
                       { return std::tolower(c); });
        return result;
    }

    bool equalsIgnoreCase(const std::string &a, const std::string &b)
    {
        return toLower(a) == toLower(b);
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
                        // Remove slash between port and base topic if present
                        if (!base_topic.empty() && base_topic[0] == '/')
                        {
                            base_topic = base_topic.substr(1);
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
                            if (equalsIgnoreCase(action["idShort"].get<std::string>(), interaction))
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
                            if (equalsIgnoreCase(property["idShort"].get<std::string>(), interaction))
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
            // Interaction not found directly - try to resolve via Variables submodel InterfaceReference
            std::cout << "Interaction '" << interaction << "' not found directly, checking Variables submodel..." << std::endl;

            std::optional<std::string> resolved_interface =
                resolveInterfaceReference(asset_id, interaction);

            // Variables-based resolution covers raw data variables aliased
            // by the planner. Higher-level planner-emitted names (PDDL
            // fluents like ``Free``/``Operational``/``ResourceAt`` and
            // actions like ``Move``/``Transport``) are declared in the
            // ``AIPlanning`` submodel instead and route through ``Skills``
            // (for actions) or ``Variables`` (for fluents, via the
            // transformation expression). Fall back to those paths if the
            // direct Variables lookup did not resolve.
            if (!resolved_interface || *resolved_interface == interaction)
            {
                if (auto via_skill = resolveActionViaAIPlanning(asset_id, interaction))
                {
                    resolved_interface = via_skill;
                }
                else if (auto via_fluent = resolveFluentViaAIPlanning(asset_id, interaction))
                {
                    resolved_interface = via_fluent;
                }
            }

            if (resolved_interface && *resolved_interface != interaction)
            {
                // Found an InterfaceReference - search again with the resolved name
                std::cout << "Retrying with resolved interface name: " << *resolved_interface << std::endl;

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
                                    if (equalsIgnoreCase(action["idShort"].get<std::string>(), *resolved_interface))
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
                                    if (equalsIgnoreCase(property["idShort"].get<std::string>(), *resolved_interface))
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
            // Check for "Forms" (capital F as per AAS convention) or "forms" (lowercase)
            if (elem["idShort"] == "Forms" || elem["idShort"] == "forms")
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

std::optional<std::string> AASClient::resolveInterfaceReference(
    const std::string &asset_id,
    const std::string &interaction)
{
    try
    {
        std::cout << "Resolving interface reference for interaction: " << interaction
                  << " in Variables submodel of asset: " << asset_id << std::endl;

        // Fetch the Variables submodel
        auto variables_data = fetchSubmodelData(asset_id, "Variables");
        if (!variables_data)
        {
            std::cout << "No Variables submodel found for asset: " << asset_id << std::endl;
            return std::nullopt;
        }

        // Look for a collection with the interaction name
        if (!variables_data->contains("submodelElements") ||
            !(*variables_data)["submodelElements"].is_array())
        {
            std::cout << "Variables submodel has no submodelElements" << std::endl;
            return std::nullopt;
        }

        for (const auto &elem : (*variables_data)["submodelElements"])
        {
            if (!elem.contains("idShort") || elem["idShort"] != interaction)
            {
                continue;
            }

            // Found the matching collection, look for InterfaceReference
            if (!elem.contains("value") || !elem["value"].is_array())
            {
                continue;
            }

            for (const auto &child : elem["value"])
            {
                if (!child.contains("idShort") || child["idShort"] != "InterfaceReference")
                {
                    continue;
                }

                // Found InterfaceReference - extract the target interface name from the keys
                // The value is a ReferenceElement with keys array
                if (!child.contains("value") || !child["value"].contains("keys") ||
                    !child["value"]["keys"].is_array())
                {
                    std::cerr << "InterfaceReference has invalid structure" << std::endl;
                    return std::nullopt;
                }

                // The last key in the path is the actual interface name
                // Keys structure: Submodel -> InterfaceMQTT -> InteractionMetadata -> properties -> <InterfaceName>
                const auto &keys = child["value"]["keys"];
                if (keys.empty())
                {
                    std::cerr << "InterfaceReference has no keys" << std::endl;
                    return std::nullopt;
                }

                // Get the last key which is the interface name
                const auto &last_key = keys[keys.size() - 1];
                if (!last_key.contains("value"))
                {
                    std::cerr << "InterfaceReference last key has no value" << std::endl;
                    return std::nullopt;
                }

                std::string resolved_interface = last_key["value"].get<std::string>();
                std::cout << "Resolved interface reference: " << interaction
                          << " -> " << resolved_interface << std::endl;
                return resolved_interface;
            }
        }

        std::cout << "No InterfaceReference found for interaction: " << interaction << std::endl;
        return std::nullopt;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error resolving interface reference: " << e.what() << std::endl;
        return std::nullopt;
    }
}

// ---------------------------------------------------------------------------
// AI-Planning resolution helpers
// ---------------------------------------------------------------------------
namespace
{
    // Locate ``submodelElements[idShort==a].value[idShort==b]...`` style
    // children. Returns nullptr when the chain breaks. Operates on raw
    // SMC ``value`` arrays / submodel ``submodelElements`` arrays
    // transparently.
    const nlohmann::json *findChildByIdShort(const nlohmann::json &collection,
                                             const std::string &id_short)
    {
        const nlohmann::json *children = nullptr;
        if (collection.contains("submodelElements") && collection["submodelElements"].is_array())
            children = &collection["submodelElements"];
        else if (collection.contains("value") && collection["value"].is_array())
            children = &collection["value"];
        if (!children)
            return nullptr;
        for (const auto &c : *children)
        {
            if (c.contains("idShort") && c["idShort"].is_string() &&
                c["idShort"].get<std::string>() == id_short)
            {
                return &c;
            }
        }
        return nullptr;
    }

    // Extract the *last* key value of a ReferenceElement's keys array.
    // Returns std::nullopt for malformed references.
    std::optional<std::string> lastKeyValue(const nlohmann::json &reference_element)
    {
        if (!reference_element.contains("value") ||
            !reference_element["value"].is_object())
            return std::nullopt;
        const auto &val = reference_element["value"];
        if (!val.contains("keys") || !val["keys"].is_array() || val["keys"].empty())
            return std::nullopt;
        const auto &last = val["keys"].back();
        if (!last.contains("value") || !last["value"].is_string())
            return std::nullopt;
        return last["value"].get<std::string>();
    }
} // namespace

std::optional<std::string> AASClient::resolveActionViaAIPlanning(
    const std::string &asset_id,
    const std::string &action_name)
{
    try
    {
        auto ai_planning = fetchSubmodelData(asset_id, "AIPlanning");
        if (!ai_planning)
            return std::nullopt;

        // AIPlanning > Domain > Actions > <action_name> > SkillReference
        const auto *domain = findChildByIdShort(*ai_planning, "Domain");
        if (!domain)
            return std::nullopt;
        const auto *actions = findChildByIdShort(*domain, "Actions");
        if (!actions)
            return std::nullopt;
        const auto *action = findChildByIdShort(*actions, action_name);
        if (!action)
            return std::nullopt;
        const auto *skill_ref = findChildByIdShort(*action, "SkillReference");
        if (!skill_ref)
            return std::nullopt;

        auto skill_name = lastKeyValue(*skill_ref);
        if (!skill_name)
            return std::nullopt;

        // Skills > <skill_name> > InterfaceReference -> last key is the
        // ``InteractionMetadata.actions.<X>`` key we need.
        auto skills_sm = fetchSubmodelData(asset_id, "Skills");
        if (!skills_sm)
            return std::nullopt;
        const auto *skill = findChildByIdShort(*skills_sm, *skill_name);
        if (!skill)
            return std::nullopt;
        const auto *iref = findChildByIdShort(*skill, "InterfaceReference");
        if (!iref)
            return std::nullopt;

        auto resolved = lastKeyValue(*iref);
        if (resolved)
        {
            std::cout << "AIPlanning action '" << action_name
                      << "' resolved via Skills." << *skill_name
                      << " -> InteractionMetadata.actions." << *resolved << std::endl;
        }
        return resolved;
    }
    catch (const std::exception &e)
    {
        std::cerr << "resolveActionViaAIPlanning error: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::optional<std::string> AASClient::resolveFluentViaAIPlanning(
    const std::string &asset_id,
    const std::string &fluent_name)
{
    try
    {
        auto ai_planning = fetchSubmodelData(asset_id, "AIPlanning");
        if (!ai_planning)
            return std::nullopt;

        // AIPlanning > Domain > Fluents > <fluent_name> > Transformation
        const auto *domain = findChildByIdShort(*ai_planning, "Domain");
        if (!domain)
            return std::nullopt;
        const auto *fluents = findChildByIdShort(*domain, "Fluents");
        if (!fluents)
            return std::nullopt;
        const auto *fluent = findChildByIdShort(*fluents, fluent_name);
        if (!fluent)
            return std::nullopt;
        const auto *trans = findChildByIdShort(*fluent, "Transformation");
        if (!trans || !trans->contains("value") || !(*trans)["value"].is_string())
            return std::nullopt;

        const std::string expr = (*trans)["value"].get<std::string>();

        // Preferred path: an explicit ``Binding`` Property sibling of
        // ``Transformation`` names the Variable whose InterfaceReference
        // identifies the MQTT interaction this fluent subscribes to. New
        // transformations (``data.Position[0] - params[1].*``) declare
        // this explicitly because they no longer reference
        // ``parameter1.Variables.<X>`` for the resolver to grep.
        std::string var_name;
        const auto *binding = findChildByIdShort(*fluent, "Binding");
        if (binding && binding->contains("value") && (*binding)["value"].is_string())
        {
            var_name = (*binding)["value"].get<std::string>();
        }
        else
        {
            // Legacy fallback: scan the transformation text for the first
            // ``parameter1.Variables.<VarName>`` reference. ``parameter1``
            // always refers to the resource on whose AAS we are operating
            // (PDDL convention: first parameter of a resource fluent is
            // the resource itself), so the Variables lookup happens on
            // the current ``asset_id``.
            static const std::regex var_re(R"(parameter1\.Variables\.([A-Za-z_][A-Za-z0-9_]*))");
            std::smatch m;
            if (!std::regex_search(expr, m, var_re))
            {
                std::cout << "AIPlanning fluent '" << fluent_name
                          << "' transformation has no Binding child and no "
                          << "parameter1.Variables.* reference: " << expr << std::endl;
                return std::nullopt;
            }
            var_name = m[1].str();
        }

        auto vars_sm = fetchSubmodelData(asset_id, "Variables");
        if (!vars_sm)
            return std::nullopt;
        const auto *var = findChildByIdShort(*vars_sm, var_name);
        if (!var)
            return std::nullopt;
        const auto *iref = findChildByIdShort(*var, "InterfaceReference");
        if (!iref)
            return std::nullopt;

        auto resolved = lastKeyValue(*iref);
        if (resolved)
        {
            std::cout << "AIPlanning fluent '" << fluent_name
                      << "' resolved via Variables." << var_name
                      << " -> InteractionMetadata.properties." << *resolved << std::endl;
        }
        return resolved;
    }
    catch (const std::exception &e)
    {
        std::cerr << "resolveFluentViaAIPlanning error: " << e.what() << std::endl;
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
            for (const auto &elem : *elements)
            {
                if (elem.contains("idShort") && elem["idShort"] == segment)
                {
                    match = &elem;
                    break;
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

std::optional<std::pair<std::string, std::string>> AASClient::resolveSkillReference(
    const std::string &asset_id,
    const std::string &action_aas_path)
{
    try
    {
        // Walk the AIPlanning submodel to the requested Action SMC.
        auto action_smc = fetchSubmodelElementByPath(asset_id, "AIPlanning", action_aas_path);
        if (!action_smc.has_value())
        {
            std::cerr << "resolveSkillReference: action SMC not found at "
                      << action_aas_path << std::endl;
            return std::nullopt;
        }
        if (!action_smc->is_object() || !action_smc->contains("value") ||
            !(*action_smc)["value"].is_array())
        {
            std::cerr << "resolveSkillReference: action SMC has no nested value array" << std::endl;
            return std::nullopt;
        }

        // Locate the SkillReference child element.
        const nlohmann::json *skill_ref_elem = nullptr;
        for (const auto &child : (*action_smc)["value"])
        {
            if (child.is_object() && child.value("idShort", "") == "SkillReference")
            {
                skill_ref_elem = &child;
                break;
            }
        }
        if (!skill_ref_elem)
        {
            std::cerr << "resolveSkillReference: no SkillReference inside "
                      << action_aas_path << std::endl;
            return std::nullopt;
        }

        // The SkillReference value is a ModelReference whose keys[] points
        // into the Skills submodel. We need the trailing
        // SubmodelElementCollection key (the skill SMC id_short).
        if (!skill_ref_elem->contains("value"))
        {
            std::cerr << "resolveSkillReference: SkillReference has no value" << std::endl;
            return std::nullopt;
        }
        const auto &value = (*skill_ref_elem)["value"];

        // BaSyx serializations differ slightly; accept either {keys: [...]}
        // directly or wrapped in a Reference object.
        const nlohmann::json *keys_array = nullptr;
        if (value.is_object() && value.contains("keys") && value["keys"].is_array())
        {
            keys_array = &value["keys"];
        }
        else if (value.is_array())
        {
            keys_array = &value;
        }
        if (!keys_array || keys_array->empty())
        {
            std::cerr << "resolveSkillReference: SkillReference keys missing or empty" << std::endl;
            return std::nullopt;
        }

        std::string skill_smc_name;
        for (const auto &key_obj : *keys_array)
        {
            if (!key_obj.is_object())
            {
                continue;
            }
            const std::string type_str = key_obj.value("type", "");
            if (type_str == "SubmodelElementCollection" || type_str == "SubmodelElement")
            {
                skill_smc_name = key_obj.value("value", "");
                // We want the last SMC key, so keep iterating.
            }
        }
        if (skill_smc_name.empty())
        {
            std::cerr << "resolveSkillReference: no SubmodelElementCollection key in SkillReference" << std::endl;
            return std::nullopt;
        }

        // The Operation inside a Skill SMC shares the SMC's id_short
        // (see Registration_Service skills_builder.py _create_operation).
        // Return the slash path "<skill>/<skill>" so invokeOperation can
        // convert to dot-path form.
        return std::make_pair(std::string("Skills"),
                              skill_smc_name + "/" + skill_smc_name);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception in resolveSkillReference: " << e.what() << std::endl;
        return std::nullopt;
    }
}

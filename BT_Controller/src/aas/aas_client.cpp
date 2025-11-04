#include "aas/aas_client.h"
#include <stdexcept>
#include <iostream>
#include <sstream>
#include <algorithm>
#include "utils.h"

static size_t WriteCallback(void *contents, size_t size, size_t nmemb, void *userp)
{
    ((std::string *)userp)->append((char *)contents, size * nmemb);
    return size * nmemb;
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
        throw std::runtime_error("HTTP error code: " + std::to_string(response_code));
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

std::optional<mqtt_utils::Topic> AASClient::fetchInterface(const std::string &asset_id, const std::string &skill, const std::string &endpoint)
{
    try
    {
        std::cout << "Fetching interface from AAS - Asset: " << asset_id
                  << ", Skill: " << skill
                  << ", Endpoint: " << endpoint << std::endl;

        // Step 1: Get the shell descriptor from registry to find the shell endpoint
        std::string registry_url = "/shell-descriptors";
        nlohmann::json registry_response = makeGetRequest(registry_url, true);

        if (!registry_response.contains("result") || !registry_response["result"].is_array())
        {
            std::cerr << "Invalid registry response structure" << std::endl;
            return std::nullopt;
        }

        // Find the AAS with matching idShort
        std::string shell_endpoint;
        for (const auto &shell : registry_response["result"])
        {
            if (shell.contains("idShort") && shell["idShort"] == asset_id)
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

        // Step 3: Fetch the submodel using base64-encoded ID
        std::string submodel_id_b64;
        CURL *temp_curl = curl_easy_init();
        char *encoded = curl_easy_escape(temp_curl, submodel_id.c_str(), submodel_id.length());
        submodel_id_b64 = std::string(encoded);
        curl_free(encoded);
        curl_easy_cleanup(temp_curl);

        std::string submodel_url = "/submodels/" + submodel_id_b64;
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

        // Find InteractionMetadata → actions → [skill]
        nlohmann::json action_data;
        for (const auto &elem : interface_mqtt["value"])
        {
            if (elem["idShort"] == "InteractionMetadata")
            {
                for (const auto &interaction_elem : elem["value"])
                {
                    if (interaction_elem["idShort"] == "actions")
                    {
                        for (const auto &action : interaction_elem["value"])
                        {
                            if (action["idShort"] == skill)
                            {
                                action_data = action;
                                break;
                            }
                        }
                        break;
                    }
                }
                break;
            }
        }

        if (action_data.empty())
        {
            std::cerr << "Could not find action: " << skill << std::endl;
            return std::nullopt;
        }

        // Step 5: Extract interface details from forms
        nlohmann::json forms_data;
        std::string schema_url;

        for (const auto &elem : action_data["value"])
        {
            if (elem["idShort"] == "forms")
            {
                forms_data = elem;
            }
            // Get schema URL based on endpoint type
            if (endpoint == "request" && elem["idShort"] == "input" && elem["modelType"] == "File")
            {
                schema_url = elem["value"];
            }
            else if (endpoint == "response" && elem["idShort"] == "output" && elem["modelType"] == "File")
            {
                schema_url = elem["value"];
            }
        }

        if (forms_data.empty())
        {
            std::cerr << "Could not find forms in action" << std::endl;
            return std::nullopt;
        }

        // Step 6: Parse forms based on endpoint type
        std::string href;
        int qos = 0;
        bool retain = false;
        std::string content_type;

        if (endpoint == "request")
        {
            // Get main form href
            for (const auto &form_elem : forms_data["value"])
            {
                if (form_elem["idShort"] == "href")
                {
                    href = form_elem["value"];
                }
                else if (form_elem["idShort"] == "mqv_qos")
                {
                    qos = form_elem["value"];
                }
                else if (form_elem["idShort"] == "mqv_retain")
                {
                    retain = form_elem["value"];
                }
            }
        }
        else if (endpoint == "response")
        {
            // Get response form
            for (const auto &form_elem : forms_data["value"])
            {
                if (form_elem["idShort"] == "response")
                {
                    for (const auto &resp_elem : form_elem["value"])
                    {
                        if (resp_elem["idShort"] == "href")
                        {
                            href = resp_elem["value"];
                        }
                    }
                    // QoS and retain from main form
                    break;
                }
            }
            // Get qos and retain from main form
            for (const auto &form_elem : forms_data["value"])
            {
                if (form_elem["idShort"] == "mqv_qos")
                {
                    qos = form_elem["value"];
                }
                else if (form_elem["idShort"] == "mqv_retain")
                {
                    retain = form_elem["value"];
                }
            }
        }
        else
        {
            // Handle additionalResponses
            for (const auto &form_elem : forms_data["value"])
            {
                if (form_elem["idShort"] == "additionalResponses")
                {
                    for (const auto &add_resp_elem : form_elem["value"])
                    {
                        if (add_resp_elem["idShort"] == "href")
                        {
                            href = add_resp_elem["value"];
                        }
                        else if (add_resp_elem["idShort"] == "schema")
                        {
                            schema_url = add_resp_elem["value"];
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

        // Step 7: Fetch the JSON schema from URL
        nlohmann::json schema;
        if (!schema_url.empty())
        {
            std::cout << "Fetching schema from: " << schema_url << std::endl;

            // Make a direct HTTP request to fetch schema
            CURL *schema_curl = curl_easy_init();
            if (schema_curl)
            {
                std::string schema_buffer;
                curl_easy_setopt(schema_curl, CURLOPT_URL, schema_url.c_str());
                curl_easy_setopt(schema_curl, CURLOPT_WRITEFUNCTION, WriteCallback);
                curl_easy_setopt(schema_curl, CURLOPT_WRITEDATA, &schema_buffer);
                curl_easy_setopt(schema_curl, CURLOPT_TIMEOUT, 10L);
                curl_easy_setopt(schema_curl, CURLOPT_FOLLOWLOCATION, 1L);

                struct curl_slist *headers = nullptr;
                headers = curl_slist_append(headers, "Accept: application/json");
                curl_easy_setopt(schema_curl, CURLOPT_HTTPHEADER, headers);

                CURLcode res = curl_easy_perform(schema_curl);
                curl_slist_free_all(headers);
                curl_easy_cleanup(schema_curl);

                if (res == CURLE_OK && !schema_buffer.empty())
                {
                    schema = nlohmann::json::parse(schema_buffer);
                    std::cout << "Successfully fetched schema" << std::endl;
                }
                else
                {
                    std::cerr << "Failed to fetch schema from URL: " << schema_url << std::endl;
                }
            }
        }

        std::cout << "Successfully fetched interface - Topic: " << full_topic
                  << ", QoS: " << qos << ", Retain: " << retain << std::endl;

        return mqtt_utils::Topic(full_topic, schema, qos, retain);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Failed to fetch interface from AAS for asset: " << asset_id
                  << ", skill: " << skill
                  << ", endpoint: " << endpoint
                  << " - Error: " << e.what() << std::endl;
        return std::nullopt;
    }
}

std::string AASClient::getInstanceNameByAssetName(const std::string &asset_name)
{
    try
    {
        // Check if Stations array exists
        if (!station_config.contains("Stations") || !station_config["Stations"].is_array())
        {
            throw std::runtime_error("Station configuration does not contain 'Stations' array");
        }

        const auto &stations = station_config["Stations"];

        // Use std::find_if to search for the station
        auto it = std::find_if(stations.begin(), stations.end(),
                               [&asset_name](const nlohmann::json &station)
                               {
                                   return station.contains("Name") && station["Name"] == asset_name;
                               });

        // Check if station was found
        if (it != stations.end())
        {
            // Check if InstanceName exists
            if (it->contains("Instance Name") && (*it)["Instance Name"].is_string())
            {
                std::string instance_name = (*it)["Instance Name"].get<std::string>();
                std::cout << "Found Instance Name: " << instance_name << " for Asset Name: " << asset_name << std::endl;
                return instance_name;
            }
            else
            {
                throw std::runtime_error("Station '" + asset_name + "' found but has no valid InstanceName");
            }
        }

        // Asset name not found
        throw std::runtime_error("Asset '" + asset_name + "' not found in station configuration");
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error in getInstanceNameByAssetName: " << e.what() << std::endl;
        throw; // Re-throw to allow caller to handle
    }
}

std::string AASClient::getStationIdByAssetName(const std::string &asset_name)
{
    try
    {
        // Check if Stations array exists
        if (!station_config.contains("Stations") || !station_config["Stations"].is_array())
        {
            throw std::runtime_error("Station configuration does not contain 'Stations' array");
        }

        const auto &stations = station_config["Stations"];

        // Use std::find_if to search for the station
        auto it = std::find_if(stations.begin(), stations.end(),
                               [&asset_name](const nlohmann::json &station)
                               {
                                   return station.contains("Name") && station["Name"] == asset_name;
                               });

        // Check if station was found
        if (it != stations.end())
        {
            // Check if InstanceName exists
            if (it->contains("StationId") && (*it)["StationId"].is_string())
            {
                return (*it)["StationId"].get<std::string>();
            }
            else
            {
                throw std::runtime_error("Station '" + asset_name + "' found but has no valid StationId");
            }
        }

        // Asset name not found
        throw std::runtime_error("Asset '" + asset_name + "' not found in station configuration");
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error in getStationIdByAssetName: " << e.what() << std::endl;
        throw; // Re-throw to allow caller to handle
    }
}

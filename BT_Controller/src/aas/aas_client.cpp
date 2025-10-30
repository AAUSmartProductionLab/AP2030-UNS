#include "aas/aas_client.h"
#include <stdexcept>
#include <iostream>
#include <sstream>
#include "utils.h"
static size_t WriteCallback(void *contents, size_t size, size_t nmemb, void *userp)
{
    ((std::string *)userp)->append((char *)contents, size * nmemb);
    return size * nmemb;
}

AASClient::AASClient(const std::string &aas_server_url)
    : aas_server_url_(aas_server_url), curl_(nullptr)
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

nlohmann::json AASClient::makeGetRequest(const std::string &endpoint)
{
    if (!curl_)
    {
        throw std::runtime_error("CURL not initialized");
    }

    std::string readBuffer;
    std::string full_url = aas_server_url_ + endpoint;

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

std::optional<mqtt_utils::Topic> AASClient::fetchInterface(const std::string &asset_id, const std::string &operation, const std::string &endpoint)
{
    try
    {
        // Example endpoint structure - adjust based on your BaSyx AAS structure
        std::ostringstream url;
        url << "/" << asset_id << "/operations/" << operation << "/interface/" << endpoint;

        nlohmann::json response = makeGetRequest(url.str());

        std::string topic_;
        nlohmann::json schema_;
        int qos_;
        bool retain_;
        // Parse the AAS response - structure depends on your AAS model
        if (response.contains("value"))
        {
            auto value = response["value"];

            if (value.is_array())
            {
                // Parse SubmodelElementCollection
                for (const auto &elem : value)
                {
                    std::string idShort = elem["idShort"].get<std::string>();

                    if (idShort == "topic")
                    {
                        topic_ = elem["topic"].get<std::string>();
                    }
                    if (idShort == "schema")
                    {
                        schema_ = elem["schema"].get<nlohmann::json>();
                    }
                    if (idShort == "qos")
                    {
                        qos_ = elem["qos"].get<int>();
                    }
                    if (idShort == "retain")
                    {
                        retain_ = elem["retain"].get<bool>();
                    }
                }

                return mqtt_utils::Topic(topic_, schema_, qos_, retain_);
            }
        }

        return std::nullopt;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Failed to fetch command topic for " << asset_id
                  << ": " << e.what() << std::endl;
        return std::nullopt;
    }
}
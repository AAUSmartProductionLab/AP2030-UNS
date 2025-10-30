#pragma once

#include <string>
#include <optional>
#include <nlohmann/json.hpp>
#include <curl/curl.h>
#include "utils.h"

class AASClient
{
public:
    AASClient(const std::string &aas_server_url);
    ~AASClient();

    // Fetch topic configuration for a specific node type and instance
    // The node_params can contain parameters from the BT XML (e.g., station_id, device_name)
    std::optional<mqtt_utils::Topic> fetchInterface(
        const std::string &asset_id,
        const std::string &skill,
        const std::string &interfaceProp);

private:
    std::string aas_server_url_;
    CURL *curl_;

    // Helper to make HTTP GET requests
    nlohmann::json makeGetRequest(const std::string &endpoint);

    // Helper to substitute parameters in topic patterns
    std::string substituteParams(const std::string &pattern, const nlohmann::json &params);
};
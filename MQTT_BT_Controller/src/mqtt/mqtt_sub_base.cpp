#include "mqtt/mqtt_sub_base.h"
#include "mqtt/node_message_distributor.h"
#include <iostream>
#include <fstream>
#include <filesystem>
#include <nlohmann/json-schema.hpp>

namespace fs = std::filesystem;
// Initialize the static member
NodeMessageDistributor *MqttSubBase::node_message_distributor_ = nullptr;

MqttSubBase::MqttSubBase(MqttClient &mqtt_client,
                         const std::string &response_topic = "",
                         const std::string &response_schema_path = "")
    : mqtt_client_(mqtt_client),
      response_topic_(response_topic),
      response_schema_path_(response_schema_path),
      response_topic_pattern_(response_topic)
{
    // Load schema if path is provided
    if (!response_schema_path_.empty())
    {
        try
        {
            fs::path schema_dir = fs::path(response_schema_path_).parent_path();
            auto schema_loader = [schema_dir](const json_uri &uri, json &schema)
            {
                std::string path_str = uri.path();
                if (!path_str.empty() && path_str[0] == '/')
                {
                    path_str = path_str.substr(1);
                }
                fs::path ref_path = schema_dir / path_str;
                std::string full_path = ref_path.string();
                std::ifstream ref_file(full_path);
                if (!ref_file.is_open())
                {
                    throw std::runtime_error("Failed to open referenced schema: " + full_path);
                }
                schema = json::parse(ref_file);
                return true;
            };

            std::ifstream schema_file(response_schema_path_);
            if (!schema_file.is_open())
            {
                throw std::runtime_error("Failed to open schema file: " + response_schema_path_);
            }

            json schema_json = json::parse(schema_file);

            response_schema_validator_ = std::make_unique<nlohmann::json_schema::json_validator>(schema_loader);
            response_schema_validator_->set_root_schema(schema_json);
        }
        catch (const std::exception &e)
        {
            std::cerr << "Error loading schema: " << e.what() << std::endl;
        }
    }
}

void MqttSubBase::processMessage(const json &msg, mqtt::properties props)
{
    if (response_schema_validator_)
    {
        try
        {
            response_schema_validator_->validate(msg);
        }
        catch (const std::exception &e)
        {
            std::cerr << "JSON validation failed: " << e.what() << std::endl;
            return;
        }
    }
    callback(msg, props);
}

bool MqttSubBase::isInterestedIn(const json &msg)
{
    std::cout << "Base isInterestedIn called - this should be overridden!" << std::endl;
    return false;
}

void MqttSubBase::setNodeMessageDistributor(NodeMessageDistributor *manager)
{
    node_message_distributor_ = manager;
}
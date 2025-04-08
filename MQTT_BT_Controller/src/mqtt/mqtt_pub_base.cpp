#include "mqtt/mqtt_pub_base.h"
#include "mqtt/mqtt_client.h"
#include <iostream>
#include <fstream>
#include <filesystem>
#include <nlohmann/json-schema.hpp>

namespace fs = std::filesystem;

MqttPubBase::MqttPubBase(MqttClient &mqtt_client,
                         const std::string &request_topic = "",
                         const std::string &request_schema_path = "",
                         const int &qos = 0,
                         const bool &retain = false)
    : mqtt_client_(mqtt_client),
      request_topic_(request_topic),
      request_schema_path_(request_schema_path),
      qos_(qos),
      retain_(retain),
      schema_validator_(nullptr)
{
  // Load schema if path is provided
  if (!request_schema_path_.empty())
  {
    try
    {
      fs::path schema_dir = fs::path(request_schema_path_).parent_path();
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

      std::ifstream schema_file(request_schema_path_);
      if (!schema_file.is_open())
      {
        throw std::runtime_error("Failed to open schema file: " + request_schema_path_);
      }

      json schema_json = json::parse(schema_file);

      schema_validator_ = std::make_unique<nlohmann::json_schema::json_validator>(schema_loader);
      schema_validator_->set_root_schema(schema_json);
    }
    catch (const std::exception &e)
    {
      std::cerr << "Error loading schema: " << e.what() << std::endl;
    }
  }
}

void MqttPubBase::publish(const json &msg)
{
  // TODO this should do json validation
  // Validate JSON against schema if validator is available
  if (schema_validator_)
  {
    try
    {
      schema_validator_->validate(msg);
    }
    catch (const std::exception &e)
    {
      std::cerr << "JSON validation failed: " << e.what() << std::endl;
      return; // Don't publish invalid messages
    }
  }
  mqtt_client_.publish(request_topic_, msg.dump(), qos_, retain_);
}

#include "mqtt/utils.h"
#include <iostream>
#include <fstream>
#include <filesystem>
#include <memory>
#include <uuid/uuid.h>
#include <nlohmann/json-schema.hpp>
namespace fs = std::filesystem;
namespace mqtt_utils
{

    std::string generate_uuid()
    {
        uuid_t uuid;
        char uuid_str[37];
        uuid_generate_random(uuid);
        uuid_unparse(uuid, uuid_str);
        return std::string(uuid_str);
    }

    nlohmann::json load_schema(const std::string &schema_path)
    {
        std::ifstream file(schema_path);

        if (!file)
        {
            std::cerr << "Couldn't open file: " << schema_path << std::endl;
            return nlohmann::json();
        }
        return nlohmann::json::parse(file);
    }

    std::string formatWildcardTopic(const std::string &topic_pattern, const std::string &replacement)
    {
        std::string formatted_topic = topic_pattern;
        size_t pos = formatted_topic.find("+");
        if (pos != std::string::npos)
        {
            formatted_topic.replace(pos, 1, replacement);
        }
        return formatted_topic;
    }
    std::unique_ptr<nlohmann::json_schema::json_validator> createSchemaValidator(const std::string &schema_path)
    {
        if (schema_path.empty())
        {
            return nullptr;
        }

        try
        {
            fs::path schema_dir = fs::path(schema_path).parent_path();
            auto schema_loader = [schema_dir](const nlohmann::json_uri &uri, nlohmann::json &schema)
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
                schema = nlohmann::json::parse(ref_file);
                return true;
            };

            std::ifstream schema_file(schema_path);
            if (!schema_file.is_open())
            {
                throw std::runtime_error("Failed to open schema file: " + schema_path);
            }

            nlohmann::json schema_json = nlohmann::json::parse(schema_file);

            auto validator = std::make_unique<nlohmann::json_schema::json_validator>(schema_loader);
            validator->set_root_schema(schema_json);
            return validator;
        }
        catch (const std::exception &e)
        {
            std::cerr << "Error loading schema: " << e.what() << std::endl;
            return nullptr;
        }
    }
} // namespace mqtt_utils
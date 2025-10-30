#include "utils.h"
#include <iostream>
#include <fstream>
#include <filesystem>
#include <memory>
#include <uuid/uuid.h>
#include <nlohmann/json-schema.hpp>
#include <fmt/chrono.h>
#include <chrono>
namespace fs = std::filesystem;

namespace bt_utils
{
    std::string getCurrentTimestampISO()
    {
        auto now = std::chrono::system_clock::now();
        auto time_point_ms = std::chrono::floor<std::chrono::milliseconds>(now);
        auto time_point_s = std::chrono::time_point_cast<std::chrono::seconds>(time_point_ms);
        auto fraction_ms = time_point_ms - time_point_s;
        return fmt::format("{:%Y-%m-%dT%H:%M:%S}.{:03}Z",
                           time_point_s,
                           fraction_ms.count());
    }
    int saveXmlToFile(const std::string &xml_content, const std::string &filename)
    {
        std::filesystem::path abs_path = std::filesystem::absolute(filename);
        std::cout << "Attempting to save to absolute path: " << abs_path << std::endl;

        std::ofstream file(filename);
        if (file.is_open())
        {
            file << xml_content;
            file.close();
            std::cout << "Successfully saved XML models to " << filename << std::endl;
            return 0;
        }
        else
        {
            std::cerr << "Failed to open file for writing: " << filename << std::endl;
            return 1;
        }
    }
    bool loadConfigFromYaml(const std::string &filename,
                            bool &generate_xml_models,
                            std::string &serverURI,
                            std::string &clientId,
                            std::string &unsTopicPrefix,
                            std::string &aasServerUri,
                            int &groot2_port,
                            std::string &bt_description_path,
                            std::string &bt_nodes_path)
    {
        try
        {
            if (!std::filesystem::exists(filename))
            {
                std::cerr << "Config file not found: " << filename << std::endl;
                return false;
            }

            YAML::Node config = YAML::LoadFile(filename);

            // Parse MQTT section
            if (config["mqtt"])
            {
                auto mqtt = config["mqtt"];

                if (mqtt["broker_uri"])
                {
                    serverURI = mqtt["broker_uri"].as<std::string>();
                    // Add "tcp://" prefix if not present
                    if (serverURI.find("://") == std::string::npos)
                    {
                        serverURI = "tcp://" + serverURI;
                    }
                }

                if (mqtt["client_id"])
                {
                    clientId = mqtt["client_id"].as<std::string>();
                }

                if (mqtt["uns_topic"])
                {
                    unsTopicPrefix = mqtt["uns_topic"].as<std::string>();
                }
            }

            // Parse AAS section
            if (config["aas"])
            {
                auto aas = config["aas"];

                if (aas["server_url"])
                {
                    aasServerUri = aas["server_url"].as<std::string>();
                }
            }

            // Parse Groot2 section
            if (config["groot2"])
            {
                auto groot2 = config["groot2"];

                if (groot2["port"])
                {
                    groot2_port = groot2["port"].as<int>();
                }
            }

            // Parse Behavior Tree section
            if (config["behavior_tree"])
            {
                auto bt = config["behavior_tree"];

                if (bt["generate_xml_models"])
                {
                    generate_xml_models = bt["generate_xml_models"].as<bool>();
                }

                if (bt["description_path"])
                {
                    bt_description_path = bt["description_path"].as<std::string>();
                }

                if (bt["nodes_path"])
                {
                    bt_nodes_path = bt["nodes_path"].as<std::string>();
                }
            }

            std::cout << "Configuration loaded from: " << filename << std::endl;
            std::cout << "  MQTT Broker: " << serverURI << std::endl;
            std::cout << "  Client ID: " << clientId << std::endl;
            std::cout << "  UNS Topic Prefix: " << unsTopicPrefix << std::endl;
            std::cout << "  AAS Server: " << aasServerUri << std::endl;
            std::cout << "  Groot2 Port: " << groot2_port << std::endl;

            return true;
        }
        catch (const YAML::Exception &e)
        {
            std::cerr << "Error parsing YAML config: " << e.what() << std::endl;
            return false;
        }
    }
}

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

    // New overload that accepts a vector of replacements
    std::string formatWildcardTopic(const std::string &topic_pattern, const std::vector<std::string> &replacements)
    {
        std::string formatted_topic = topic_pattern;
        size_t pos = 0;
        size_t replacement_index = 0;

        // Replace each "+" wildcard with corresponding replacement value
        while ((pos = formatted_topic.find("+", pos)) != std::string::npos &&
               replacement_index < replacements.size())
        {
            formatted_topic.replace(pos, 1, replacements[replacement_index]);
            // Move position past the inserted replacement
            pos += replacements[replacement_index].length();
            replacement_index++;
        }

        return formatted_topic;
    }

    // generates a  schema with respect to references within schemas.
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

    bool topicMatches(const std::string &pattern, const std::string &topic)
    {
        std::istringstream patternStream(pattern);
        std::istringstream topicStream(topic);
        std::string patternSegment, topicSegment;

        while (std::getline(patternStream, patternSegment, '/') &&
               std::getline(topicStream, topicSegment, '/'))
        {
            if (patternSegment == "+" || topicSegment == "+")
            {
                continue;
            }
            else if (patternSegment == "#" || topicSegment == "#")
            {
                return true;
            }
            else if (patternSegment != topicSegment)
            {
                return false;
            }
        }

        bool patternDone = !std::getline(patternStream, patternSegment, '/');
        bool topicDone = !std::getline(topicStream, topicSegment, '/');

        return patternDone && topicDone;
    }

    // Constructor with JSON schema directly
    Topic::Topic(const std::string &topic,
                 const nlohmann::json &schema,
                 int qos,
                 bool retain)
        : topic_(topic),
          pattern_(topic),
          schema_(schema),
          schema_validator_(nullptr),
          qos_(qos),
          retain_(retain)
    {
        initValidator();
    }

    // Constructor that loads schema from file path
    Topic Topic::fromSchemaPath(const std::string &topic,
                                const std::string &schema_path,
                                int qos,
                                bool retain)
    {
        nlohmann::json schema = load_schema(schema_path);
        return Topic(topic, schema, qos, retain);
    }

    // Copy Constructor
    Topic::Topic(const Topic &other)
        : topic_(other.topic_),
          pattern_(other.pattern_),
          schema_(other.schema_),
          schema_validator_(nullptr),
          qos_(other.qos_),
          retain_(other.retain_)
    {
        initValidator();
    }

    // Move Constructor
    Topic::Topic(Topic &&other) noexcept
        : topic_(std::move(other.topic_)),
          pattern_(std::move(other.pattern_)),
          schema_(std::move(other.schema_)),
          schema_validator_(std::move(other.schema_validator_)),
          qos_(other.qos_),
          retain_(other.retain_)
    {
    }

    // Copy Assignment Operator
    Topic &Topic::operator=(const Topic &other)
    {
        if (this != &other)
        {
            topic_ = other.topic_;
            pattern_ = other.pattern_;
            schema_ = other.schema_;
            schema_validator_.reset();
            initValidator();
            qos_ = other.qos_;
            retain_ = other.retain_;
        }
        return *this;
    }

    // Move Assignment Operator
    Topic &Topic::operator=(Topic &&other) noexcept
    {
        if (this != &other)
        {
            topic_ = std::move(other.topic_);
            pattern_ = std::move(other.pattern_);
            schema_ = std::move(other.schema_);
            schema_validator_ = std::move(other.schema_validator_);
            qos_ = other.qos_;
            retain_ = other.retain_;
        }
        return *this;
    }

    // Initialize schema validator
    void Topic::initValidator()
    {
        if (!schema_.is_null() && !schema_.empty())
        {
            try
            {
                auto validator = std::make_unique<nlohmann::json_schema::json_validator>(
                    [](const nlohmann::json_uri &uri, nlohmann::json &schema)
                    {
                        // Extract the file name from the URI
                        std::string schema_file = uri.path();

                        // Remove leading slash if present
                        if (!schema_file.empty() && schema_file[0] == '/')
                        {
                            schema_file = schema_file.substr(1);
                        }

                        // Build the full path relative to the schemas directory
                        std::string schema_path = "../../schemas/" + schema_file;

                        // Load the referenced schema
                        schema = load_schema(schema_path);
                    },
                    nlohmann::json_schema::default_string_format_check);
                validator->set_root_schema(schema_);
                schema_validator_ = std::move(validator);
            }
            catch (const std::exception &e)
            {
                std::cerr << "Error creating schema validator for topic '" << topic_ << "': " << e.what() << std::endl;
                schema_validator_.reset();
            }
        }
    }

    void Topic::setSchema(const nlohmann::json &schema)
    {
        schema_ = schema;
        schema_validator_.reset();
        initValidator();
    }
    void Topic::setSchemaFromPath(const std::string &schema_path)
    {
        schema_ = load_schema(schema_path);
        schema_validator_.reset();
        initValidator();
    }

    // Validate message against schema
    bool Topic::validateMessage(const nlohmann::json &message) const
    {
        if (schema_validator_)
        {
            try
            {
                schema_validator_->validate(message);
                return true;
            }
            catch (const std::exception &e)
            {
                std::cerr << "JSON validation failed for topic '" << topic_ << "': " << e.what() << std::endl;
                return false;
            }
        }
        return false;
    }
} // namespace mqtt_utils

namespace BT
{
    // Define here instead
    StringView trim_string_view(StringView sv)
    {
        if (sv.empty())
        {
            return sv;
        }
        size_t first = 0;
        while (first < sv.size() && std::isspace(static_cast<unsigned char>(sv[first])))
        {
            ++first;
        }
        if (first == sv.size()) // All whitespace
        {
            return StringView(sv.data() + first, 0);
        }

        size_t last = sv.size() - 1;
        while (last > first && std::isspace(static_cast<unsigned char>(sv[last])))
        {
            --last;
        }
        return sv.substr(first, (last - first) + 1);
    }
}
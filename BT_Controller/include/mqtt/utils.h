#pragma once
#include <string>
#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include <iostream>
namespace mqtt_utils
{
    // Generate a random UUID string
    std::string generate_uuid();

    // Load and parse a JSON schema from file
    nlohmann::json load_schema(const std::string &schema_path);

    std::string formatWildcardTopic(const std::string &topic, const std::string &id);
    std::string formatWildcardTopic(const std::string &topic_pattern, const std::vector<std::string> &replacements);
    std::unique_ptr<nlohmann::json_schema::json_validator> createSchemaValidator(const std::string &schema_path);
    class Topic
    {
    public:
        Topic(const std::string &topic = "",
              const std::string &schema_path = "",
              int qos = 0,
              bool retain = false)
            : topic_(topic),
              pattern_(topic),
              schema_path_(schema_path),
              schema_validator_(nullptr),
              qos_(qos),
              retain_(retain) {}
        Topic(const Topic &other)
            : topic_(other.topic_),
              pattern_(other.topic_),
              schema_path_(other.schema_path_),
              schema_validator_(nullptr),
              qos_(other.qos_),
              retain_(other.retain_)
        {
        }
        // Initialize schema validator
        void initValidator()
        {
            if (!schema_path_.empty())
            {
                schema_validator_ = createSchemaValidator(schema_path_);
            }
        }

        // Getters
        const std::string &getTopic() const { return topic_; }
        const std::string &getPattern() const { return pattern_; }
        const std::string &getSchemaPath() const { return schema_path_; }
        int getQos() const { return qos_; }
        bool getRetain() const { return retain_; }

        // Setters
        void setTopic(const std::string &topic) { topic_ = topic; }
        void setPattern(const std::string &pattern) { pattern_ = pattern; }
        void setSchemaPath(const std::string &schema_path)
        {
            schema_path_ = schema_path;
            schema_validator_.reset(); // Reset existing validator
        }
        void setQos(int qos) { qos_ = qos; }
        void setRetain(bool retain) { retain_ = retain; }

        // Update topic using wildcards
        void applyPattern(const std::string &id)
        {
            if (!pattern_.empty())
            {
                topic_ = formatWildcardTopic(pattern_, id);
            }
        }

        void applyPattern(const std::vector<std::string> &replacements)
        {
            if (!pattern_.empty())
            {
                topic_ = formatWildcardTopic(pattern_, replacements);
            }
        }

        // Validate message against schema
        bool validateMessage(const nlohmann::json &message)
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
                    std::cerr << "JSON validation failed: " << e.what() << std::endl;
                    return false;
                }
            }
            return true; // If no validator, assume valid
        }

    private:
        std::string topic_;
        std::string pattern_;
        std::string schema_path_;
        std::unique_ptr<nlohmann::json_schema::json_validator> schema_validator_;
        int qos_;
        bool retain_;
    };
}
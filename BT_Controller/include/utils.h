#pragma once
#include <string>
#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>
#include <iostream>
#include <magic_enum/magic_enum.hpp>
#include <chrono>
#include <functional>
#include <iostream>
#include <fstream>
#include <filesystem>
#include <yaml-cpp/yaml.h>

#include <behaviortree_cpp/bt_factory.h>

namespace PackML
{
    // Define the state machine states
    enum class State
    {
        IDLE,
        STARTING,
        EXECUTE,
        COMPLETING,
        COMPLETE,
        RESETTING,
        HOLDING,
        HELD,
        UNHOLDING,
        SUSPENDING,
        SUSPENDED,
        UNSUSPENDING,
        ABORTING,
        ABORTED,
        CLEARING,
        STOPPING,
        STOPPED,
    };
    inline std::string stateToString(State state)
    {
        return std::string(magic_enum::enum_name(state));
    }

    inline std::optional<State> stringToState(const std::string &str)
    {
        return magic_enum::enum_cast<State>(str);
    }
}

namespace bt_utils
{
    /**
     * Saves a string to a file
     */
    std::string getCurrentTimestampISO();
    int saveXmlToFile(const std::string &xml_content, const std::string &filename);
    bool loadConfigFromYaml(const std::string &filename,
                            bool &generate_xml_models,
                            std::string &serverURI,
                            std::string &clientId,
                            std::string &unsTopicPrefix,
                            std::string &aasServerUri,
                            int &groot2_port,
                            std::string &bt_description_path,
                            std::string &bt_nodes_path);
}

namespace BT
{
    // Declare only, don't define
    StringView trim_string_view(StringView sv);

    // Template must stay inline in header
    template <>
    inline nlohmann::json convertFromString<nlohmann::json>(StringView str_param)
    {
        StringView s = trim_string_view(str_param);
        if (s.size() >= 2 && s.front() == '\'' && s.back() == '\'')
        {
            StringView inner_content = s.substr(1, s.size() - 2);
            try
            {
                return nlohmann::json::parse(inner_content);
            }
            catch (const nlohmann::json::parse_error &e)
            {
                std::string error_message = "Failed to parse JSON from single-quoted string. Inner content: '";
                error_message.append(inner_content);
                error_message += "'. Details: ";
                error_message += e.what();
                throw RuntimeError(error_message);
            }
        }
        else
            throw RuntimeError(
                "Invalid Parameter format. Expected single-quoted json string like '\"{\\\"key\\\": \\\"value\\\"}\"'");
    }
};

namespace mqtt_utils
{
    // Generate a random UUID string
    std::string generate_uuid();

    // Load and parse a JSON schema from file
    nlohmann::json load_schema(const std::string &schema_path);

    std::string formatWildcardTopic(const std::string &topic, const std::string &id);
    std::string formatWildcardTopic(const std::string &topic_pattern, const std::vector<std::string> &replacements);
    std::unique_ptr<nlohmann::json_schema::json_validator> createSchemaValidator(const std::string &schema_path);
    bool topicMatches(const std::string &pattern, const std::string &topic);
    class Topic
    {
    public:
        // Constructor with JSON schema directly
        Topic(const std::string &topic = "",
              const nlohmann::json &schema = nlohmann::json(),
              int qos = 0,
              bool retain = false)
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
        static Topic fromSchemaPath(const std::string &topic,
                                    const std::string &schema_path,
                                    int qos = 0,
                                    bool retain = false)
        {
            nlohmann::json schema = load_schema(schema_path);
            return Topic(topic, schema, qos, retain);
        }

        // Copy Constructor
        Topic(const Topic &other)
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
        Topic(Topic &&other) noexcept
            : topic_(std::move(other.topic_)),
              pattern_(std::move(other.pattern_)),
              schema_(std::move(other.schema_)),
              schema_validator_(std::move(other.schema_validator_)),
              qos_(other.qos_),
              retain_(other.retain_)
        {
        }

        Topic &operator=(const Topic &other)
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
        Topic &operator=(Topic &&other) noexcept
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
        void initValidator()
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

        // Getters
        const std::string &getTopic() const { return topic_; }
        const std::string &getPattern() const { return pattern_; }
        const nlohmann::json &getSchema() const { return schema_; }
        int getQos() const { return qos_; }
        bool getRetain() const { return retain_; }

        // Setters
        void setTopic(const std::string &topic) { topic_ = topic; }
        void setPattern(const std::string &pattern) { pattern_ = pattern; }
        void setSchema(const nlohmann::json &schema)
        {
            schema_ = schema;
            schema_validator_.reset();
            initValidator();
        }
        void setSchemaFromPath(const std::string &schema_path)
        {
            schema_ = load_schema(schema_path);
            schema_validator_.reset();
            initValidator();
        }
        void setQos(int qos) { qos_ = qos; }
        void setRetain(bool retain) { retain_ = retain; }

        // Validate message against schema
        bool validateMessage(const nlohmann::json &message) const
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

    private:
        std::string topic_;
        std::string pattern_;
        nlohmann::json schema_;
        std::unique_ptr<nlohmann::json_schema::json_validator> schema_validator_;
        int qos_;
        bool retain_;
    };
}
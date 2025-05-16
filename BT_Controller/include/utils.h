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
                            int &groot2_port,
                            std::string &bt_description_path,
                            std::string &bt_nodes_path);
}

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
        Topic(const std::string &topic = "",
              const std::string &schema_path = "",
              int qos = 0,
              bool retain = false)
            : topic_(topic),
              pattern_(topic), // Assuming pattern is initially the same as topic
              schema_path_(schema_path),
              schema_validator_(nullptr),
              qos_(qos),
              retain_(retain)
        {
        }

        // Copy Constructor
        Topic(const Topic &other)
            : topic_(other.topic_),
              pattern_(other.pattern_),
              schema_path_(other.schema_path_),
              schema_validator_(nullptr), // New validator must be initialized via initValidator()
              qos_(other.qos_),
              retain_(other.retain_)
        {
            // If you want the copied Topic to also have a validator immediately,
            // you might call initValidator() here.
            // Or, if the validator itself can be "cloned" (if json_validator supports it):
            // if (other.schema_validator_) {
            //    schema_validator_ = std::make_unique<nlohmann::json_schema::json_validator>(*other.schema_validator_); // Requires validator to be copyable
            // }
        }

        // Move Constructor
        Topic(Topic &&other) noexcept
            : topic_(std::move(other.topic_)),
              pattern_(std::move(other.pattern_)),
              schema_path_(std::move(other.schema_path_)),
              schema_validator_(std::move(other.schema_validator_)),
              qos_(other.qos_),
              retain_(other.retain_)
        {
        }

        // Copy Assignment Operator
        // If you need copy assignment, implement it carefully.
        // A simple member-wise copy is problematic with unique_ptr.
        // You'd need to decide how to handle schema_validator_.
        // Option 1: Delete it (prevents copy assignment)
        // Topic& operator=(const Topic& other) = delete;

        // Option 2: Implement it (example, similar to copy constructor)
        Topic &operator=(const Topic &other)
        {
            if (this != &other)
            {
                topic_ = other.topic_;
                pattern_ = other.pattern_;
                schema_path_ = other.schema_path_;
                // Handle schema_validator_ (e.g., reset and optionally re-init or clone)
                schema_validator_.reset(); // Reset current validator
                // if (other.schema_validator_) { // If you want to clone
                //    schema_validator_ = std::make_unique<nlohmann::json_schema::json_validator>(*other.schema_validator_);
                // } else if (!schema_path_.empty()) { // Or re-initialize if path exists
                //    initValidator();
                // }
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
                schema_path_ = std::move(other.schema_path_);
                schema_validator_ = std::move(other.schema_validator_);
                qos_ = other.qos_;
                retain_ = other.retain_;
            }
            return *this;
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
            // Consider calling initValidator() here if a new path means a new validator should be immediately ready
            // initValidator();
        }
        void setQos(int qos) { qos_ = qos; }
        void setRetain(bool retain) { retain_ = retain; }

        // Update topic using wildcards
        void applyPattern(const std::string &replacement)
        {
            if (!pattern_.empty())
            {
                topic_ = formatWildcardTopic(pattern_, replacement);
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
        bool validateMessage(const nlohmann::json &message) const // Added const
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
                    // You might want to log the message itself for debugging:
                    // std::cerr << "Message: " << message.dump(2) << std::endl;
                    return false;
                }
            }
            // If there's no schema path, and thus no validator, consider it valid or invalid based on requirements.
            // Current: if no validator, it's not validated, so effectively "passes" this check if not strict.
            // If a schema_path is provided but validator creation failed, schema_validator_ would be null.
            // If strict validation is required even if schema_path is empty, this logic might change.
            // For now, if no validator, it returns false. If you want it to be true:
            return schema_path_.empty(); // Returns true if no schema path was ever set, false otherwise if validator is null.
                                         // Or simply: return true; // if no validator means "don't care, it's valid"
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
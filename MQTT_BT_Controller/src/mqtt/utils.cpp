#include "mqtt/utils.h"
#include <iostream>
#include <fstream>
#include <uuid/uuid.h>

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
} // namespace mqtt_utils
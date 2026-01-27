#include "aas/aas_interface_cache.h"
#include "aas/aas_client.h"
#include "utils.h"
#include <iostream>
#include <algorithm>
#include <cctype>

namespace {
    std::string toLower(const std::string& s) {
        std::string result = s;
        std::transform(result.begin(), result.end(), result.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        return result;
    }
}

AASInterfaceCache::AASInterfaceCache(AASClient &aas_client)
    : aas_client_(aas_client)
{
}

bool AASInterfaceCache::prefetchInterfaces(const std::map<std::string, std::string> &asset_ids)
{
    std::lock_guard<std::mutex> lock(mutex_);

    std::cout << "AASInterfaceCache: Pre-fetching interfaces for " << asset_ids.size() << " assets..." << std::endl;

    clear();

    size_t success_count = 0;

    for (const auto &[equipment_name, asset_id] : asset_ids)
    {
        std::cout << "  Fetching interfaces for: " << equipment_name << " (" << asset_id << ")" << std::endl;

        if (fetchAssetInterfaces(asset_id))
        {
            success_count++;
        }
        else
        {
            failed_assets_.insert(asset_id);
            std::cerr << "  Warning: Failed to fetch interfaces for " << equipment_name << std::endl;
        }
    }

    std::cout << "AASInterfaceCache: Pre-fetch complete. "
              << success_count << "/" << asset_ids.size() << " assets cached successfully." << std::endl << std::flush;

    std::cout << "AASInterfaceCache: Returning from prefetchInterfaces with " << (success_count > 0 ? "true" : "false") << std::endl << std::flush;

    return success_count > 0;
}

bool AASInterfaceCache::fetchAssetInterfaces(const std::string &asset_id)
{
    try
    {
        // Fetch the AssetInterfacesDescription submodel
        // We'll parse it to extract all actions and properties

        // First, get the shell to find the submodel reference
        std::string shell_id_b64 = aas_client_.base64url_encode(asset_id);
        std::string shell_path = "/shells/" + shell_id_b64;

        nlohmann::json shell_data;
        try
        {
            shell_data = aas_client_.makeGetRequest(shell_path);
        }
        catch (const std::exception &e)
        {
            std::cerr << "    Failed to fetch shell: " << e.what() << std::endl;
            return false;
        }

        if (!shell_data.contains("submodels") || !shell_data["submodels"].is_array())
        {
            std::cerr << "    Shell missing submodels array" << std::endl;
            return false;
        }

        // Find AssetInterfacesDescription submodel reference
        std::string submodel_id;
        for (const auto &submodel_ref : shell_data["submodels"])
        {
            if (submodel_ref.contains("keys") && submodel_ref["keys"].is_array())
            {
                std::string ref_value = submodel_ref["keys"][0]["value"];
                if (ref_value.find("AssetInterfacesDescription") != std::string::npos ||
                    ref_value.find("AssetInterfaceDescription") != std::string::npos)
                {
                    submodel_id = ref_value;
                    break;
                }
            }
        }

        if (submodel_id.empty())
        {
            std::cerr << "    Could not find AssetInterfacesDescription submodel" << std::endl;
            return false;
        }

        // Fetch the submodel
        std::string submodel_id_b64 = aas_client_.base64url_encode(submodel_id);
        std::string submodel_url = "/submodels/" + submodel_id_b64;

        nlohmann::json submodel_data;
        try
        {
            submodel_data = aas_client_.makeGetRequest(submodel_url);
        }
        catch (const std::exception &e)
        {
            std::cerr << "    Failed to fetch submodel: " << e.what() << std::endl;
            return false;
        }

        if (!submodel_data.contains("submodelElements") || !submodel_data["submodelElements"].is_array())
        {
            std::cerr << "    Submodel missing submodelElements array" << std::endl;
            return false;
        }

        // Find InterfaceMQTT
        nlohmann::json interface_mqtt;
        for (const auto &elem : submodel_data["submodelElements"])
        {
            if (elem.contains("idShort") && elem["idShort"] == "InterfaceMQTT")
            {
                interface_mqtt = elem;
                break;
            }
        }

        if (interface_mqtt.empty())
        {
            std::cerr << "    Could not find InterfaceMQTT element" << std::endl;
            return false;
        }

        // Get base topic from EndpointMetadata
        std::string base_topic;
        for (const auto &elem : interface_mqtt["value"])
        {
            if (elem["idShort"] == "EndpointMetadata")
            {
                for (const auto &metadata_elem : elem["value"])
                {
                    if (metadata_elem["idShort"] == "base")
                    {
                        base_topic = metadata_elem["value"];
                        // Remove mqtt:// or mqtts:// prefix if present
                        if (base_topic.find("mqtts://") == 0)
                        {
                            base_topic = base_topic.substr(8);
                            size_t slash_pos = base_topic.find('/');
                            if (slash_pos != std::string::npos)
                            {
                                base_topic = base_topic.substr(slash_pos);
                            }
                        }
                        else if (base_topic.find("mqtt://") == 0)
                        {
                            base_topic = base_topic.substr(7);
                            size_t slash_pos = base_topic.find('/');
                            if (slash_pos != std::string::npos)
                            {
                                base_topic = base_topic.substr(slash_pos);
                            }
                        }
                        if (!base_topic.empty() && base_topic[0] == '/')
                        {
                            base_topic = base_topic.substr(1);
                        }
                        break;
                    }
                }
                break;
            }
        }

        // Store the base topic for this asset
        if (!base_topic.empty())
        {
            asset_base_topics_[asset_id] = base_topic;
        }

        // Find InteractionMetadata and extract all actions and properties
        for (const auto &elem : interface_mqtt["value"])
        {
            if (elem["idShort"] != "InteractionMetadata")
            {
                continue;
            }

            for (const auto &interaction_type_elem : elem["value"])
            {
                bool is_action = (interaction_type_elem["idShort"] == "actions");
                bool is_property = (interaction_type_elem["idShort"] == "properties");

                if (!is_action && !is_property)
                {
                    continue;
                }

                for (const auto &interaction : interaction_type_elem["value"])
                {
                    std::string interaction_name = toLower(interaction["idShort"].get<std::string>());
                    InterfaceData interface_data;

                    // First pass: collect all data from form elements
                    std::string href;
                    int qos = 0;
                    bool retain = false;
                    std::string response_href;
                    std::string input_schema_url;
                    std::string output_schema_url;

                    for (const auto &form_elem : interaction["value"])
                    {
                        if (form_elem["idShort"] == "Forms" || form_elem["idShort"] == "forms")
                        {
                            for (const auto &f : form_elem["value"])
                            {
                                std::string f_id = f["idShort"];
                                if (f_id == "href")
                                {
                                    href = f["value"].get<std::string>();
                                }
                                else if (f_id == "mqv_qos")
                                {
                                    if (f["value"].is_number())
                                        qos = f["value"].get<int>();
                                    else if (f["value"].is_string())
                                        qos = std::stoi(f["value"].get<std::string>());
                                }
                                else if (f_id == "mqv_retain")
                                {
                                    if (f["value"].is_boolean())
                                        retain = f["value"].get<bool>();
                                    else if (f["value"].is_string())
                                    {
                                        std::string val = f["value"].get<std::string>();
                                        retain = (val == "true" || val == "1");
                                    }
                                }
                                else if (f_id == "response" && f["modelType"] == "SubmodelElementCollection")
                                {
                                    for (const auto &resp_elem : f["value"])
                                    {
                                        if (resp_elem["idShort"] == "href")
                                        {
                                            response_href = resp_elem["value"].get<std::string>();
                                        }
                                    }
                                }
                            }
                        }
                        else if (form_elem["idShort"] == "input" && form_elem["modelType"] == "File")
                        {
                            // Extract input schema URL
                            if (form_elem.contains("value") && form_elem["value"].is_string())
                            {
                                input_schema_url = form_elem["value"].get<std::string>();
                            }
                        }
                        else if (form_elem["idShort"] == "output" && form_elem["modelType"] == "File")
                        {
                            // Extract output schema URL
                            if (form_elem.contains("value") && form_elem["value"].is_string())
                            {
                                output_schema_url = form_elem["value"].get<std::string>();
                            }
                        }
                    }

                    // Fetch schemas if URLs are provided
                    nlohmann::json input_schema;
                    nlohmann::json output_schema;

                    if (!input_schema_url.empty())
                    {
                        try
                        {
                            input_schema = schema_utils::fetchSchemaFromUrl(input_schema_url);
                        }
                        catch (const std::exception &e)
                        {
                            // Schema fetch failed, continue without validation
                        }
                    }

                    if (!output_schema_url.empty())
                    {
                        try
                        {
                            output_schema = schema_utils::fetchSchemaFromUrl(output_schema_url);
                        }
                        catch (const std::exception &e)
                        {
                            // Schema fetch failed, continue without validation
                        }
                    }

                    // Build input topic with schema
                    if (!href.empty())
                    {
                        std::string full_topic = base_topic;
                        if (!href.empty() && href[0] != '/')
                        {
                            full_topic += "/";
                        }
                        full_topic += href;
                        if (!full_topic.empty() && full_topic[0] == '/')
                        {
                            full_topic = full_topic.substr(1);
                        }

                        interface_data.input_topic = mqtt_utils::Topic(full_topic, input_schema, qos, retain);
                        interface_data.has_input = true;
                    }

                    // Build output topic with schema
                    std::string output_href = response_href.empty() ? href : response_href;
                    if (!output_href.empty())
                    {
                        std::string full_topic = base_topic;
                        if (!output_href.empty() && output_href[0] != '/')
                        {
                            full_topic += "/";
                        }
                        full_topic += output_href;
                        if (!full_topic.empty() && full_topic[0] == '/')
                        {
                            full_topic = full_topic.substr(1);
                        }

                        interface_data.output_topic = mqtt_utils::Topic(full_topic, output_schema, qos, retain);
                        interface_data.has_output = true;
                    }

                    interface_cache_[asset_id][interaction_name] = interface_data;
                }
            }
        }

        size_t num_interfaces = interface_cache_[asset_id].size();
        std::cout << "    Cached " << num_interfaces << " interfaces" << std::endl;
        
        // Also fetch variable aliases for this asset
        fetchVariableAliases(asset_id);

        return num_interfaces > 0;
    }
    catch (const std::exception &e)
    {
        std::cerr << "    Exception fetching interfaces: " << e.what() << std::endl;
        return false;
    }
}

std::optional<mqtt_utils::Topic> AASInterfaceCache::getInterface(
    const std::string &asset_id,
    const std::string &interaction,
    const std::string &endpoint) const
{
    std::lock_guard<std::mutex> lock(mutex_);

    auto asset_it = interface_cache_.find(asset_id);
    if (asset_it == interface_cache_.end())
    {
        return std::nullopt;
    }

    std::string resolved_interaction = toLower(interaction);
    
    // Check if the interaction is a Variable alias that needs to be resolved
    auto alias_asset_it = variable_alias_cache_.find(asset_id);
    if (alias_asset_it != variable_alias_cache_.end())
    {
        auto alias_it = alias_asset_it->second.find(resolved_interaction);
        if (alias_it != alias_asset_it->second.end())
        {
            resolved_interaction = alias_it->second;  // Use the resolved interface name
        }
    }

    auto interaction_it = asset_it->second.find(resolved_interaction);
    if (interaction_it == asset_it->second.end())
    {
        return std::nullopt;
    }

    const InterfaceData &data = interaction_it->second;

    if (endpoint == "input" && data.has_input)
    {
        return data.input_topic;
    }
    else if (endpoint == "output" && data.has_output)
    {
        return data.output_topic;
    }

    return std::nullopt;
}

std::set<std::string> AASInterfaceCache::getWildcardTopicPatterns() const
{
    std::lock_guard<std::mutex> lock(mutex_);

    std::set<std::string> patterns;

    for (const auto &[asset_id, base_topic] : asset_base_topics_)
    {
        if (base_topic.empty())
        {
            continue;
        }

        // Create wildcard pattern for all DATA and CMD topics under this base
        // e.g., "NN/Nybrovej/InnoLab/Planar/Xbot3" -> "NN/Nybrovej/InnoLab/Planar/Xbot3/#"
        patterns.insert(base_topic + "/#");
    }

    return patterns;
}

std::vector<mqtt_utils::Topic> AASInterfaceCache::getAssetOutputTopics(const std::string &asset_id) const
{
    std::lock_guard<std::mutex> lock(mutex_);

    std::vector<mqtt_utils::Topic> topics;

    auto asset_it = interface_cache_.find(asset_id);
    if (asset_it == interface_cache_.end())
    {
        return topics;
    }

    for (const auto &[interaction_name, data] : asset_it->second)
    {
        if (data.has_output)
        {
            topics.push_back(data.output_topic);
        }
    }

    return topics;
}

bool AASInterfaceCache::hasAsset(const std::string &asset_id) const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return interface_cache_.find(asset_id) != interface_cache_.end();
}

void AASInterfaceCache::clear()
{
    // Note: mutex should already be locked by caller
    interface_cache_.clear();
    variable_alias_cache_.clear();
    asset_base_topics_.clear();
    failed_assets_.clear();
}

AASInterfaceCache::CacheStats AASInterfaceCache::getStats() const
{
    std::lock_guard<std::mutex> lock(mutex_);

    CacheStats stats;
    stats.total_assets = interface_cache_.size();
    stats.failed_assets = failed_assets_.size();
    stats.total_interfaces = 0;

    for (const auto &[asset_id, interfaces] : interface_cache_)
    {
        stats.total_interfaces += interfaces.size();
    }

    return stats;
}

std::string AASInterfaceCache::extractBaseTopic(const std::string &topic) const
{
    // Extract the base path before /DATA or /CMD
    size_t data_pos = topic.find("/DATA");
    size_t cmd_pos = topic.find("/CMD");

    size_t split_pos = std::string::npos;
    if (data_pos != std::string::npos && cmd_pos != std::string::npos)
    {
        split_pos = std::min(data_pos, cmd_pos);
    }
    else if (data_pos != std::string::npos)
    {
        split_pos = data_pos;
    }
    else if (cmd_pos != std::string::npos)
    {
        split_pos = cmd_pos;
    }

    if (split_pos != std::string::npos)
    {
        return topic.substr(0, split_pos);
    }

    return topic;
}
void AASInterfaceCache::fetchVariableAliases(const std::string &asset_id)
{
    try
    {
        // Fetch the Variables submodel to extract variable-to-interface mappings
        auto variables_data = aas_client_.fetchSubmodelData(asset_id, "Variables");
        if (!variables_data)
        {
            // No Variables submodel - this is normal for some assets
            return;
        }

        if (!variables_data->contains("submodelElements") ||
            !(*variables_data)["submodelElements"].is_array())
        {
            return;
        }

        std::map<std::string, std::string> aliases;

        for (const auto &elem : (*variables_data)["submodelElements"])
        {
            if (!elem.contains("idShort") || !elem.contains("value") || !elem["value"].is_array())
            {
                continue;
            }

            std::string variable_name = toLower(elem["idShort"].get<std::string>());

            // Look for InterfaceReference within the variable's elements
            for (const auto &child : elem["value"])
            {
                if (!child.contains("idShort") || child["idShort"] != "InterfaceReference")
                {
                    continue;
                }

                // InterfaceReference is a ReferenceElement with a keys array
                if (!child.contains("value") || !child["value"].contains("keys") ||
                    !child["value"]["keys"].is_array())
                {
                    continue;
                }

                const auto &keys = child["value"]["keys"];
                if (keys.empty())
                {
                    continue;
                }

                // The last key in the path is the actual interface name
                const auto &last_key = keys[keys.size() - 1];
                if (last_key.contains("value"))
                {
                    std::string interface_name = toLower(last_key["value"].get<std::string>());
                    aliases[variable_name] = interface_name;
                    std::cout << "    Variable alias: " << variable_name << " -> " << interface_name << std::endl;
                }
                break;
            }
        }

        if (!aliases.empty())
        {
            variable_alias_cache_[asset_id] = aliases;
            std::cout << "    Cached " << aliases.size() << " variable aliases" << std::endl;
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "    Exception fetching variable aliases: " << e.what() << std::endl;
    }
}
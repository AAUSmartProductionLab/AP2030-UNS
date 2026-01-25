#pragma once

#include <behaviortree_cpp/aas_provider.h>
#include "aas/aas_client.h"
#include <memory>
#include <sstream>
#include <vector>
#include <algorithm>
#include <iostream>

/**
 * @brief AAS Provider implementation that uses the existing AASClient.
 * 
 * This bridges the BehaviorTree.CPP AAS extension with the project's
 * AASClient implementation.
 * 
 * Path format follows basyx ModelReference structure (AASd-123, AASd-125, AASd-128):
 *   - First key: AasIdentifiable (AAS shell ID)
 *   - Second key: Submodel idShort
 *   - Following keys: idShort-based navigation through SMC/SML/Property
 * 
 * Format:
 *   "AAS_ID/SubmodelIdShort/SMC1/.../PropertyIdShort"
 * 
 * Example paths:
 *   "https://smartproductionlab.aau.dk/aas/FillingLine/HierarchicalStructures/EntryNode/Dispensing/Location/x"
 *   "FillingLineAAS/HierarchicalStructures/EntryNode/Dispensing/Location/x"
 *   "MyAAS/SubmodelName/MyList/0/value"  (SML index per AASd-128)
 * 
 * The path is split at the boundary between the AAS ID and the submodel idShort.
 * For URL-based IDs, we look for common AAS URL patterns to find this boundary.
 */
class AASClientProvider : public BT::AASProvider
{
public:
    /**
     * @brief Construct provider with existing AASClient.
     * @param client Shared pointer to AASClient
     */
    explicit AASClientProvider(std::shared_ptr<AASClient> client)
      : client_(std::move(client))
    {}
    
    /**
     * @brief Fetch a value from AAS following ModelReference path format.
     * 
     * @param path ModelReference-style path: "AAS_ID/SubmodelIdShort/ElementPath..."
     * @return The value as Any, or empty if not found
     */
    std::optional<BT::Any> get(const std::string& path) override
    {
        auto parsed = parsePath(path);
        if(!parsed.has_value())
        {
            std::cerr << "AASClientProvider: Failed to parse path: " << path << std::endl;
            return std::nullopt;
        }
        
        const auto& [aas_id, submodel_id_short, element_path] = parsed.value();
        
        // Use AASClient's path-based property lookup
        auto json_result = client_->fetchPropertyValue(aas_id, submodel_id_short, element_path);
        if(!json_result.has_value())
        {
            std::cerr << "AASClientProvider: Failed to fetch property: " << path << std::endl;
            return std::nullopt;
        }
        
        return jsonToAny(json_result.value());
    }
    
    bool set(const std::string& path, const BT::Any& value) override
    {
        // TODO: Implement write support when AASClient supports it
        (void)path;
        (void)value;
        return false;
    }

private:
    std::shared_ptr<AASClient> client_;
    
    struct ParsedPath
    {
        std::string aas_id;
        std::string submodel_id_short;
        std::vector<std::string> element_path;
    };
    
    /**
     * @brief Parse a ModelReference-style path.
     * 
     * For URL-based AAS IDs (starting with http://, https://, or urn:):
     *   The URL is the AAS ID, followed by SubmodelIdShort, then element path.
     *   We detect the boundary by looking for "/aas/" pattern in the URL.
     * 
     * For simple idShort-based paths:
     *   First part is AAS idShort, second is Submodel idShort, rest is element path.
     */
    std::optional<ParsedPath> parsePath(const std::string& path)
    {
        ParsedPath result;
        
        // Check if path starts with URL scheme
        bool is_url = (path.find("http://") == 0 || path.find("https://") == 0 || 
                       path.find("urn:") == 0);
        
        if(is_url)
        {
            // For URLs, we need to find where the AAS ID ends
            // Look for "/aas/" pattern - the segment after is the AAS name
            
            size_t aas_marker = path.find("/aas/");
            if(aas_marker != std::string::npos)
            {
                // Find the AAS name after /aas/
                size_t aas_name_start = aas_marker + 5;  // After "/aas/"
                size_t aas_name_end = path.find('/', aas_name_start);
                
                if(aas_name_end == std::string::npos)
                {
                    // No more slashes - malformed path (need submodel + elements)
                    return std::nullopt;
                }
                
                // AAS ID is everything up to and including the AAS name
                result.aas_id = path.substr(0, aas_name_end);
                
                // Parse remaining path for submodel and elements
                std::string remaining = path.substr(aas_name_end + 1);
                return parseRemainingPath(result, remaining);
            }
            
            // No /aas/ pattern found - try to find boundary heuristically
            // Look for first segment that looks like an idShort after URL base
            size_t search_start = 0;
            if(path.find("http://") == 0) search_start = 7;
            else if(path.find("https://") == 0) search_start = 8;
            else if(path.find("urn:") == 0) search_start = 4;
            
            // Find all slash positions
            std::vector<size_t> slash_positions;
            for(size_t i = search_start; i < path.size(); ++i)
            {
                if(path[i] == '/') slash_positions.push_back(i);
            }
            
            // Look for the transition from URL to idShort navigation
            for(size_t i = 0; i < slash_positions.size(); ++i)
            {
                size_t start = slash_positions[i] + 1;
                size_t end = (i + 1 < slash_positions.size()) ? slash_positions[i + 1] : path.size();
                std::string segment = path.substr(start, end - start);
                
                // Check if segment looks like an idShort
                if(!segment.empty() && std::isalpha(static_cast<unsigned char>(segment[0])))
                {
                    bool is_id_short = std::all_of(segment.begin(), segment.end(), 
                        [](unsigned char c) { return std::isalnum(c) || c == '_'; });
                    
                    // Skip common URL words
                    if(is_id_short && segment != "aas" && segment != "shells" && 
                       segment != "submodels" && segment != "api" && segment != "v1" && segment != "v2")
                    {
                        // Found likely submodel idShort - AAS ID ends before this
                        result.aas_id = path.substr(0, slash_positions[i]);
                        std::string remaining = path.substr(start);
                        return parseRemainingPath(result, remaining);
                    }
                }
            }
            
            // Fallback: couldn't parse URL-based path
            return std::nullopt;
        }
        else
        {
            // Simple idShort-based path: AASIdShort/SubmodelIdShort/Element/Path
            return parseRemainingPath(result, path);
        }
    }
    
    std::optional<ParsedPath> parseRemainingPath(ParsedPath& result, const std::string& remaining)
    {
        std::vector<std::string> parts;
        std::istringstream iss(remaining);
        std::string part;
        while(std::getline(iss, part, '/'))
        {
            if(!part.empty())
            {
                parts.push_back(part);
            }
        }
        
        if(parts.empty())
        {
            return std::nullopt;
        }
        
        // If aas_id is already set (URL case), first part is submodel
        if(!result.aas_id.empty())
        {
            if(parts.size() < 2)
            {
                // Need at least submodel + one element
                return std::nullopt;
            }
            result.submodel_id_short = parts[0];
            for(size_t i = 1; i < parts.size(); ++i)
            {
                result.element_path.push_back(parts[i]);
            }
        }
        else
        {
            // Simple path: first = AAS, second = Submodel, rest = elements
            if(parts.size() < 3)
            {
                return std::nullopt;
            }
            result.aas_id = parts[0];
            result.submodel_id_short = parts[1];
            for(size_t i = 2; i < parts.size(); ++i)
            {
                result.element_path.push_back(parts[i]);
            }
        }
        
        return result;
    }
    
    BT::Any jsonToAny(const nlohmann::json& json_value)
    {
        if(json_value.is_number_integer())
        {
            return BT::Any(static_cast<double>(json_value.get<int64_t>()));
        }
        else if(json_value.is_number_float())
        {
            return BT::Any(json_value.get<double>());
        }
        else if(json_value.is_boolean())
        {
            return BT::Any(json_value.get<bool>() ? 1.0 : 0.0);
        }
        else if(json_value.is_string())
        {
            return BT::Any(json_value.get<std::string>());
        }
        else if(json_value.is_array())
        {
            // For numeric arrays, return vector<double>
            std::vector<double> nums;
            bool all_numbers = true;
            for(const auto& elem : json_value)
            {
                if(elem.is_number())
                {
                    nums.push_back(elem.get<double>());
                }
                else
                {
                    all_numbers = false;
                    break;
                }
            }
            
            if(all_numbers && !nums.empty())
            {
                return BT::Any(nums);
            }
            // Fallback: return as JSON string
            return BT::Any(json_value.dump());
        }
        else if(json_value.is_object())
        {
            return BT::Any(json_value.dump());
        }
        
        return BT::Any();
    }
};

/**
 * @brief Create a caching AAS provider from an AASClient.
 * 
 * @param client The AASClient to use
 * @param cache_ttl Cache time-to-live (default 60 seconds)
 * @return Shared pointer to caching AAS provider
 */
inline BT::AASProvider::Ptr createCachingAASProvider(
    std::shared_ptr<AASClient> client,
    std::chrono::seconds cache_ttl = std::chrono::seconds(60))
{
    auto base_provider = std::make_shared<AASClientProvider>(std::move(client));
    return std::make_shared<BT::CachingAASProvider>(base_provider, cache_ttl);
}

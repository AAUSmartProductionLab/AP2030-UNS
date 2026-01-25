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
 *   - First key: Submodel ID (AasIdentifiable - full global identifier)
 *   - Following keys: FragmentKeys (idShorts - local identifiers within submodel)
 * 
 * Format:
 *   "SubmodelId/SMC1/.../PropertyIdShort"
 *   → Fetches directly from Submodel repository
 * 
 * Example paths:
 *   "https://smartproductionlab.aau.dk/sm/HierarchicalStructures/EntryNode/Dispensing/Location/x"
 *   "urn:submodel:HierarchicalStructures/EntryNode/Dispensing/Location/x"
 * 
 * NOTE: AAS-first paths (starting with AAS ID) are NOT supported for property access.
 * Per the AAS metamodel, a ModelReference to submodel content must start with the
 * Submodel ID, not the AAS ID. The AAS only *references* submodels, it doesn't
 * *contain* their elements.
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
     * @param path ModelReference-style path
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
        
        const auto& [submodel_id, element_path] = parsed.value();
        
        // Fetch directly from submodel repository using Submodel ID
        auto json_result = client_->fetchPropertyValueBySubmodelId(submodel_id, element_path);
        
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
        std::string submodel_id;               // Submodel ID (AasIdentifiable)
        std::vector<std::string> element_path; // FragmentKeys (idShort navigation)
    };
    
    /**
     * @brief Find the boundary where a URL-based Submodel identifier ends.
     * 
     * For URLs like "https://example.org/sm/MySubmodel",
     * we need to find where the identifier ends and the idShort navigation begins.
     */
    size_t findSubmodelIdEnd(const std::string& path) const
    {
        // Look for patterns that indicate Submodel identifier
        std::vector<std::string> markers = {"/sm/", "/submodel/"};
        
        for(const auto& marker : markers)
        {
            size_t pos = path.find(marker);
            if(pos != std::string::npos)
            {
                // Find the identifier name after the marker
                size_t name_start = pos + marker.size();
                size_t name_end = path.find('/', name_start);
                if(name_end == std::string::npos)
                {
                    return path.size();  // Identifier goes to end
                }
                return name_end;
            }
        }
        
        // No marker found - for simple paths, find first slash
        size_t slash = path.find('/');
        return (slash != std::string::npos) ? slash : path.size();
    }
    
    /**
     * @brief Parse a ModelReference-style path (Submodel-first only).
     * 
     * Format: SubmodelId/element/path
     * First key is Submodel ID (full identifier), rest are idShorts.
     */
    std::optional<ParsedPath> parsePath(const std::string& path)
    {
        ParsedPath result;
        
        // Check if path starts with URL scheme
        bool is_url = (path.find("http://") == 0 || path.find("https://") == 0 || 
                       path.find("urn:") == 0);
        
        size_t submodel_id_end;
        
        if(is_url)
        {
            // Find where Submodel ID ends
            submodel_id_end = findSubmodelIdEnd(path);
            
            // Validate it looks like a Submodel ID (not AAS ID)
            std::string potential_id = path.substr(0, submodel_id_end);
            if(potential_id.find("/aas/") != std::string::npos || 
               potential_id.find("/shell") != std::string::npos ||
               potential_id.find("urn:aas:") != std::string::npos)
            {
                std::cerr << "AASClientProvider: AAS-first paths not supported. "
                          << "Use Submodel ID as first key. Path: " << path << std::endl;
                return std::nullopt;
            }
        }
        else
        {
            // Simple path: first segment is the Submodel ID
            submodel_id_end = path.find('/');
            if(submodel_id_end == std::string::npos)
            {
                // No path separator - invalid
                return std::nullopt;
            }
        }
        
        result.submodel_id = path.substr(0, submodel_id_end);
        
        if(submodel_id_end >= path.size())
        {
            // No element path after Submodel ID
            return std::nullopt;
        }
        
        // Parse remaining as element path (idShorts)
        std::string remaining = path.substr(submodel_id_end + 1);
        std::istringstream iss(remaining);
        std::string part;
        while(std::getline(iss, part, '/'))
        {
            if(!part.empty())
            {
                result.element_path.push_back(part);
            }
        }
        
        if(result.element_path.empty())
        {
            return std::nullopt;
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

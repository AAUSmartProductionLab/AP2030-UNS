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
 *   - First key: AasIdentifiable (AAS ID or Submodel ID - both are valid starting points)
 *   - Following keys: FragmentKeys (idShort-based navigation through SMC/SML/Property)
 * 
 * Two valid path formats:
 * 
 * Format 1 - Submodel-first (direct submodel access):
 *   "SubmodelId/SMC1/.../PropertyIdShort"
 *   → Fetches directly from Submodel repository
 *   
 * Format 2 - AAS-first (navigate via AAS context):
 *   "AAS_ID/SubmodelId/SMC1/.../PropertyIdShort"
 *   → Fetches from AAS repository, second key is also a full identifier
 * 
 * Example paths:
 *   Submodel-first:
 *     "https://smartproductionlab.aau.dk/sm/HierarchicalStructures/EntryNode/Dispensing/Location/x"
 *     "urn:submodel:HierarchicalStructures/EntryNode/Dispensing/Location/x"
 *   
 *   AAS-first:
 *     "https://smartproductionlab.aau.dk/aas/FillingLine/https://smartproductionlab.aau.dk/sm/HierarchicalStructures/EntryNode/Location/x"
 *     "urn:aas:FillingLine/urn:sm:HierarchicalStructures/EntryNode/Location/x"
 * 
 * Detection: 
 *   - Contains "/sm/" or "/submodel" → Submodel ID
 *   - Contains "/aas/" or "/shell" → AAS ID
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
        
        const auto& [first_id, second_id, element_path, is_submodel_first] = parsed.value();
        
        std::optional<nlohmann::json> json_result;
        
        if(is_submodel_first)
        {
            // Submodel-first: first_id is Submodel ID, fetch directly from submodel repository
            json_result = client_->fetchPropertyValueBySubmodelId(first_id, element_path);
        }
        else
        {
            // AAS-first: first_id is AAS ID, second_id is Submodel ID
            json_result = client_->fetchPropertyValueViaAAS(first_id, second_id, element_path);
        }
        
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
        std::string first_id;           // First AasIdentifiable (AAS ID or Submodel ID)
        std::string second_id;          // Second AasIdentifiable (Submodel ID, only for AAS-first)
        std::vector<std::string> element_path;  // FragmentKeys (idShort navigation)
        bool is_submodel_first;         // true if first_id is a Submodel ID
    };
    
    /**
     * @brief Check if an identifier looks like a Submodel ID.
     */
    bool looksLikeSubmodelId(const std::string& id) const
    {
        if(id.find("/sm/") != std::string::npos) return true;
        if(id.find("/submodel") != std::string::npos) return true;
        if(id.find("urn:sm:") != std::string::npos) return true;
        if(id.find("Submodel") != std::string::npos) return true;
        return false;
    }
    
    /**
     * @brief Check if an identifier looks like an AAS ID.
     */
    bool looksLikeAASId(const std::string& id) const
    {
        if(id.find("/aas/") != std::string::npos) return true;
        if(id.find("/shell") != std::string::npos) return true;
        if(id.find("urn:aas:") != std::string::npos) return true;
        return false;
    }
    
    /**
     * @brief Find the boundary where a URL-based identifier ends.
     * 
     * For URLs like "https://example.org/aas/MyAAS" or "https://example.org/sm/MySubmodel",
     * we need to find where the identifier ends and the idShort navigation begins.
     */
    size_t findIdentifierEnd(const std::string& path, size_t start) const
    {
        // Look for patterns that indicate end of identifier
        // After /aas/Name or /sm/Name, the next slash starts idShort navigation
        
        std::vector<std::string> markers = {"/aas/", "/sm/", "/shell/", "/submodel/"};
        
        for(const auto& marker : markers)
        {
            size_t pos = path.find(marker, start);
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
        size_t slash = path.find('/', start);
        return (slash != std::string::npos) ? slash : path.size();
    }
    
    /**
     * @brief Parse a ModelReference-style path.
     */
    std::optional<ParsedPath> parsePath(const std::string& path)
    {
        ParsedPath result;
        
        // Check if path starts with URL scheme
        bool is_url = (path.find("http://") == 0 || path.find("https://") == 0 || 
                       path.find("urn:") == 0);
        
        if(is_url)
        {
            // Find where first identifier ends
            size_t first_id_end = findIdentifierEnd(path, 0);
            result.first_id = path.substr(0, first_id_end);
            
            // Determine if this is Submodel-first or AAS-first
            result.is_submodel_first = looksLikeSubmodelId(result.first_id);
            
            if(first_id_end >= path.size())
            {
                // No more content after first ID
                return std::nullopt;
            }
            
            std::string remaining = path.substr(first_id_end + 1);
            
            if(result.is_submodel_first)
            {
                // Submodel-first: remaining is all element path (idShorts)
                return parseElementPath(result, remaining);
            }
            else
            {
                // AAS-first: need to find second identifier (Submodel ID)
                // Check if remaining starts with a URL or identifier pattern
                bool second_is_url = (remaining.find("http://") == 0 || 
                                      remaining.find("https://") == 0 || 
                                      remaining.find("urn:") == 0);
                
                if(second_is_url)
                {
                    // Second identifier is also a URL
                    size_t second_id_end = findIdentifierEnd(remaining, 0);
                    result.second_id = remaining.substr(0, second_id_end);
                    
                    if(second_id_end < remaining.size())
                    {
                        std::string element_remaining = remaining.substr(second_id_end + 1);
                        return parseElementPath(result, element_remaining);
                    }
                    else
                    {
                        // No element path - need at least one element
                        return std::nullopt;
                    }
                }
                else
                {
                    // Second identifier might be a simple ID or this is idShort navigation
                    // Use SubmodelIdShort approach - first segment is submodel idShort
                    return parseWithSubmodelIdShort(result, remaining);
                }
            }
        }
        else
        {
            // Simple path without URL scheme
            // Could be: SubmodelIdShort/path or AASIdShort/SubmodelIdShort/path
            // We need context to know which - default to requiring both for safety
            return parseSimplePath(path);
        }
    }
    
    /**
     * @brief Parse remaining path as element path (idShorts).
     */
    std::optional<ParsedPath> parseElementPath(ParsedPath& result, const std::string& remaining)
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
        
        result.element_path = std::move(parts);
        return result;
    }
    
    /**
     * @brief Parse with SubmodelIdShort as second component (convenience format).
     * 
     * This handles: AAS_URL/SubmodelIdShort/element/path
     * Which is a convenience format, not strictly ModelReference compliant.
     */
    std::optional<ParsedPath> parseWithSubmodelIdShort(ParsedPath& result, const std::string& remaining)
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
        
        if(parts.size() < 2)
        {
            // Need submodel idShort + at least one element
            return std::nullopt;
        }
        
        // First part is submodel idShort (will need to resolve to full ID)
        result.second_id = parts[0];
        
        for(size_t i = 1; i < parts.size(); ++i)
        {
            result.element_path.push_back(parts[i]);
        }
        
        return result;
    }
    
    /**
     * @brief Parse a simple (non-URL) path.
     * 
     * Format: AASIdShort/SubmodelIdShort/element/path
     * OR: SubmodelId/element/path (if SubmodelId contains special pattern)
     */
    std::optional<ParsedPath> parseSimplePath(const std::string& path)
    {
        ParsedPath result;
        
        std::vector<std::string> parts;
        std::istringstream iss(path);
        std::string part;
        while(std::getline(iss, part, '/'))
        {
            if(!part.empty())
            {
                parts.push_back(part);
            }
        }
        
        if(parts.size() < 2)
        {
            return std::nullopt;
        }
        
        // Check if first part looks like a submodel identifier
        if(looksLikeSubmodelId(parts[0]))
        {
            result.is_submodel_first = true;
            result.first_id = parts[0];
            for(size_t i = 1; i < parts.size(); ++i)
            {
                result.element_path.push_back(parts[i]);
            }
        }
        else
        {
            // Assume AAS-first with idShort format
            result.is_submodel_first = false;
            
            if(parts.size() < 3)
            {
                // Need AAS + Submodel + at least one element
                return std::nullopt;
            }
            
            result.first_id = parts[0];      // AAS idShort
            result.second_id = parts[1];     // Submodel idShort
            
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

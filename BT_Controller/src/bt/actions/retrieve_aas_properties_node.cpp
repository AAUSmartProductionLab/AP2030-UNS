#include "bt/actions/retrieve_aas_properties_node.h"
#include <iostream>

BT::PortsList RetrieveAASPropertyNode::providedPorts()
{
    return {
        BT::InputPort<std::string>("Asset", "The asset name to retrieve the property from"),
        BT::InputPort<std::string>("Submodel", "The submodel idShort containing the property"),
        BT::InputPort<std::string>("Property", "The property idShort or path (use | as delimiter, e.g., 'Filling|Location|x')"),
        BT::BidirectionalPort<std::string>("output_key", "Name of the blackboard entry where the value should be written")};
}

BT::NodeStatus RetrieveAASPropertyNode::tick()
{
    // Get the output key where we'll write the value
    std::string output_key;
    if (!getInput("output_key", output_key))
    {
        throw BT::RuntimeError("missing port [output_key]");
    }

    // Get the asset name
    std::string asset_name;
    if (!getInput("Asset", asset_name))
    {
        throw BT::RuntimeError("missing port [Asset]");
    }

    // Get the submodel idShort
    std::string submodel_id_short;
    if (!getInput("Submodel", submodel_id_short))
    {
        throw BT::RuntimeError("missing port [Submodel]");
    }

    // Get the property idShort or path
    std::string property_input;
    if (!getInput("Property", property_input))
    {
        throw BT::RuntimeError("missing port [Property]");
    }

    try
    {
        // Resolve asset name to asset ID
        std::string asset_id = aas_client_.getInstanceNameByAssetName(asset_name);

        // Parse property input to detect if it's a path (contains |)
        std::optional<nlohmann::json> property_value_opt;

        if (property_input.find('|') != std::string::npos)
        {
            // Parse as path - split by pipe delimiter
            std::vector<std::string> property_path;
            std::stringstream ss(property_input);
            std::string segment;
            while (std::getline(ss, segment, '|'))
            {
                property_path.push_back(segment);
            }

            std::cout << "Retrieving property path [";
            for (size_t i = 0; i < property_path.size(); ++i)
            {
                std::cout << property_path[i];
                if (i < property_path.size() - 1)
                    std::cout << " | ";
            }
            std::cout << "] from submodel '" << submodel_id_short
                      << "' of asset '" << asset_name << "' (ID: " << asset_id << ")" << std::endl;

            // Fetch using path-based method
            property_value_opt = aas_client_.fetchPropertyValue(
                asset_id, submodel_id_short, property_path);
        }
        else
        {
            // Simple property name
            std::cout << "Retrieving property '" << property_input
                      << "' from submodel '" << submodel_id_short
                      << "' of asset '" << asset_name << "' (ID: " << asset_id << ")" << std::endl;

            // Fetch using simple method (which internally uses path-based with single element)
            property_value_opt = aas_client_.fetchPropertyValue(
                asset_id, submodel_id_short, property_input);
        }

        if (!property_value_opt.has_value())
        {
            std::cerr << "Failed to retrieve property from AAS" << std::endl;
            return BT::NodeStatus::FAILURE;
        }

        nlohmann::json property_value = property_value_opt.value();

        // Get the blackboard entry for output_key (may be null if it doesn't exist yet)
        std::shared_ptr<BT::Blackboard::Entry> dst_entry =
            config().blackboard->getEntry(output_key);

        BT::Any out_value;

        // Check if this is an AAS property with valueType metadata
        if (property_value.is_object() && property_value.contains("valueType") && property_value.contains("value"))
        {
            // AAS property structure - use valueType to determine conversion
            std::string value_type = property_value["valueType"].get<std::string>();
            nlohmann::json value = property_value["value"];

            if (value_type == "xs:int" || value_type == "xs:integer" ||
                value_type == "xs:long" || value_type == "xs:short")
            {
                out_value = BT::Any(std::stoi(value.get<std::string>()));
            }
            else if (value_type == "xs:float" || value_type == "xs:double" || value_type == "xs:decimal")
            {
                out_value = BT::Any(std::stod(value.get<std::string>()));
            }
            else if (value_type == "xs:boolean" || value_type == "xs:bool")
            {
                std::string val_str = value.get<std::string>();
                out_value = BT::Any(val_str == "true" || val_str == "True" || val_str == "TRUE" || val_str == "1");
            }
            else if (value_type == "xs:string")
            {
                out_value = BT::Any(value.get<std::string>());
            }
            else
            {
                // Unknown valueType, store as string
                out_value = BT::Any(value.is_string() ? value.get<std::string>() : value.dump());
            }
        }
        else if (property_value.is_string())
        {
            // Plain string value
            out_value = BT::Any(property_value.get<std::string>());
        }
        else
        {
            // Complex structure or array without valueType - output as JSON string
            out_value = BT::Any(property_value.dump());
        }

        if (out_value.empty())
        {
            std::cerr << "Property value is empty" << std::endl;
            return BT::NodeStatus::FAILURE;
        }

        // Handle type conversion if the destination already exists with a specific type
        if (dst_entry && dst_entry->info.type() != typeid(std::string) && out_value.isString())
        {
            try
            {
                out_value = dst_entry->info.parseString(out_value.cast<std::string>());
            }
            catch (const std::exception &e)
            {
                throw BT::LogicError("Can't convert string [", out_value.cast<std::string>(),
                                     "] to type [", BT::demangle(dst_entry->info.type()),
                                     "]: ", e.what());
            }
        }

        // Write the value to the blackboard
        config().blackboard->set(output_key, out_value);

        std::cout << "Successfully wrote property value to blackboard key '" << output_key << "'" << std::endl;

        return BT::NodeStatus::SUCCESS;
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception in RetrieveAASPropertyNode: " << e.what() << std::endl;
        return BT::NodeStatus::FAILURE;
    }
}

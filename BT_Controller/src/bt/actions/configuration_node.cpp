#include "bt/actions/configuration_node.h"
#include "utils.h"

BT::PortsList ConfigurationNode::providedPorts()
{
    return {
        BT::InputPort<std::string>("Product", "{product}", "Product AAS ID to fetch batch information from"),
        BT::details::PortWithDefault<BT::SharedQueue<std::string>>(BT::PortDirection::OUTPUT,
                                                                   "ProductIDs",
                                                                   "{ProductIDs}",
                                                                   "List of product IDs to produce")};
}

BT::NodeStatus ConfigurationNode::onStart()
{
    // Get product AAS ID from input port
    auto product_input = getInput<std::string>("Product");
    if (!product_input.has_value() || product_input.value().empty())
    {
        std::cerr << "No Product AAS ID provided" << std::endl;
        return BT::NodeStatus::FAILURE;
    }
    std::string product_aas_id = product_input.value();

    // Fetch the Quantity from the BatchInformation submodel
    auto quantity_opt = aas_client_.fetchPropertyValue(product_aas_id, "BatchInformation", "Quantity");
    if (!quantity_opt.has_value())
    {
        std::cerr << "Failed to fetch Quantity from BatchInformation submodel" << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    // Parse the quantity value - it comes as a string in the AAS
    int batchSize = 0;
    try
    {
        const auto &quantity_value = quantity_opt.value();
        if (quantity_value.is_string())
        {
            batchSize = std::stoi(quantity_value.get<std::string>());
        }
        else if (quantity_value.is_number())
        {
            batchSize = quantity_value.get<int>();
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Failed to parse Quantity value: " << e.what() << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    if (batchSize <= 0)
    {
        std::cerr << "Invalid batch size: " << batchSize << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    std::cout << "ConfigurationNode: Creating queue with " << batchSize << " product IDs" << std::endl;

    // Generate UUIDs for each product in the batch
    for (int i = 0; i < batchSize; ++i)
    {
        std::string id = mqtt_utils::generate_uuid();
        shared_queue->push_back(id);
    }

    // Store the queue in the blackboard
    config().blackboard->set("ProductIDs", shared_queue);

    return BT::NodeStatus::SUCCESS;
}

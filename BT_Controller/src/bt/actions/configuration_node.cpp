#include "bt/actions/configuration_node.h"
#include "utils.h"

BT::PortsList ConfigurationNode::providedPorts()
{
    return {
        BT::InputPort<std::string>("Product", "{product}", "Product AAS ID to fetch batch information from"),
        BT::details::PortWithDefault<BT::SharedQueue<std::string>>(BT::PortDirection::OUTPUT,
                                                                   "ProductIDs",
                                                                   "{ProductIDs}",
                                                                   "List of product IDs to produce"),
        BT::OutputPort<int>("BatchSize", "{BatchSize}", "Initial size of the product queue"),
        BT::OutputPort<int>("IPCInspection", "{IPCInspection}", "In-process control inspection sampling rate (0-100)")};
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

    // Store the initial queue size for QualityControlGate
    setOutput("BatchSize", batchSize);
    std::cout << "ConfigurationNode: Set BatchSize = " << batchSize << std::endl;

    // Fetch IPC inspection rate from Requirements submodel
    // Path: Requirements -> InProcessControls -> IPCInspection
    int ipcInspection = 100; // Default to 100% if not found
    
    auto qc_opt = aas_client_.fetchPropertyValue(
        product_aas_id, 
        "Requirements", 
        std::vector<std::string>{"InProcessControls", "IPCInspection"});
    
    if (qc_opt.has_value())
    {
        try
        {
            const auto &qc_value = qc_opt.value();
            if (qc_value.is_string())
            {
                ipcInspection = std::stoi(qc_value.get<std::string>());
            }
            else if (qc_value.is_number())
            {
                ipcInspection = qc_value.get<int>();
            }
            std::cout << "ConfigurationNode: Fetched IPCInspection = " << ipcInspection << "%" << std::endl;
        }
        catch (const std::exception &e)
        {
            std::cerr << "Failed to parse IPCInspection, using default 100%: " << e.what() << std::endl;
        }
    }
    else
    {
        std::cout << "ConfigurationNode: IPCInspection not found in AAS, using default 100%" << std::endl;
    }

    setOutput("IPCInspection", ipcInspection);

    return BT::NodeStatus::SUCCESS;
}

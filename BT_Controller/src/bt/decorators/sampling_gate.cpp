#include "bt/decorators/sampling_gate.h"
#include <behaviortree_cpp/bt_factory.h>
#include <iostream>
#include <cmath>

BT::NodeStatus SamplingGate::tick()
{
    // Get sampling rate from input port
    auto sampling_rate_input = getInput<int>("SamplingRate");
    if (!sampling_rate_input.has_value())
    {
        // Default to 100% if not specified (always execute)
        sampling_rate_input = 100;
    }
    int sampling_rate = sampling_rate_input.value();

    // Clamp to valid range
    if (sampling_rate < 0) sampling_rate = 0;
    if (sampling_rate > 100) sampling_rate = 100;

    // If 100%, always execute child
    if (sampling_rate == 100)
    {
        setStatus(BT::NodeStatus::RUNNING);
        return child_node_->executeTick();
    }

    // If 0%, never execute child
    if (sampling_rate == 0)
    {
        std::cout << "[SamplingGate] Node '" << this->name() 
                  << "' sampling disabled (0%), skipping child" << std::endl;
        return BT::NodeStatus::SUCCESS;
    }

    // Get the initial batch size to calculate product index
    auto batch_size_input = getInput<int>("BatchSize");
    if (!batch_size_input.has_value() || batch_size_input.value() <= 0)
    {
        std::cerr << "[SamplingGate] Node '" << this->name() 
                  << "' no valid BatchSize, defaulting to execute child" << std::endl;
        setStatus(BT::NodeStatus::RUNNING);
        return child_node_->executeTick();
    }
    int batch_size = batch_size_input.value();

    // Get current queue size
    BT::AnyPtrLocked any_ref = getLockedPortContent("Queue");
    int current_size = 0;
    
    if (any_ref)
    {
        auto queue_expected = any_ref.get()->cast<BT::SharedQueue<std::string>>();
        if (queue_expected)
        {
            auto queue_ptr = queue_expected.value();
            if (queue_ptr)
            {
                current_size = static_cast<int>(queue_ptr->size());
            }
        }
    }

    // Calculate product index (0-based, counting from start of batch)
    // When queue has N items left out of initial I, we're processing product (I - N)
    // This is called AFTER PopElement, so if initial was 10 and current is 9,
    // we're processing product index 0 (first product)
    int product_index = batch_size - current_size;
    
    bool should_execute = shouldExecute(product_index, sampling_rate);

    std::cout << "[SamplingGate] Node '" << this->name() 
              << "' product " << (product_index + 1) << "/" << batch_size 
              << " (index=" << product_index << ")"
              << " rate=" << sampling_rate << "%" 
              << " -> " << (should_execute ? "EXECUTE" : "SKIP") << std::endl;

    if (should_execute)
    {
        setStatus(BT::NodeStatus::RUNNING);
        return child_node_->executeTick();
    }
    else
    {
        // Skip execution, return success
        return BT::NodeStatus::SUCCESS;
    }
}

bool SamplingGate::shouldExecute(int productIndex, int samplingRate) const
{
    // Use modular arithmetic with period of 100 for precise control
    // productIndex % 100 gives us position in a 100-product cycle
    // We execute if (productIndex % 100) < samplingRate
    //
    // Examples:
    // - 90% rate: products 0-89 out of every 100 get executed
    // - 85% rate: products 0-84 out of every 100 get executed
    // - 50% rate: products 0-49 out of every 100 get executed
    
    int position_in_cycle = productIndex % 100;
    return position_in_cycle < samplingRate;
}

BT::PortsList SamplingGate::providedPorts()
{
    return {
        BT::InputPort<int>(
            "SamplingRate",
            100,
            "Percentage of products that should be processed (0-100). Default: 100%"),
        BT::InputPort<int>(
            "BatchSize",
            "{BatchSize}",
            "The initial size of the product queue (typically set by Configure node)"),
        BT::InputPort<BT::SharedQueue<std::string>>(
            "Queue",
            "{ProductIDs}",
            "The queue of product IDs to determine current product index")
    };
}

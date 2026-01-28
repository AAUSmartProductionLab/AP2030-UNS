#include "bt/decorators/quality_control_gate.h"
#include <behaviortree_cpp/bt_factory.h>
#include <iostream>
#include <cmath>

BT::NodeStatus QualityControlGate::tick()
{
    // Get QC percentage from input port
    auto qc_percentage_input = getInput<int>("QCPercentage");
    if (!qc_percentage_input.has_value())
    {
        // Default to 100% if not specified (always do QC)
        qc_percentage_input = 100;
    }
    int qc_percentage = qc_percentage_input.value();

    // Clamp to valid range
    if (qc_percentage < 0) qc_percentage = 0;
    if (qc_percentage > 100) qc_percentage = 100;

    // If 100%, always perform QC
    if (qc_percentage == 100)
    {
        setStatus(BT::NodeStatus::RUNNING);
        return child_node_->executeTick();
    }

    // If 0%, never perform QC
    if (qc_percentage == 0)
    {
        std::cout << "[QualityControlGate] Node '" << this->name() 
                  << "' QC disabled (0%), skipping child" << std::endl;
        return BT::NodeStatus::SUCCESS;
    }

    // Get the initial queue size and current queue to calculate product index
    auto initial_size_input = getInput<int>("BatchSize");
    if (!initial_size_input.has_value() || initial_size_input.value() <= 0)
    {
        std::cerr << "[QualityControlGate] Node '" << this->name() 
                  << "' no valid BatchSize, defaulting to perform QC" << std::endl;
        setStatus(BT::NodeStatus::RUNNING);
        return child_node_->executeTick();
    }
    int initial_size = initial_size_input.value();

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
    // But this is called AFTER PopElement, so if initial was 10 and current is 9,
    // we're processing product index 0 (first product)
    int product_index = initial_size - current_size;
    
    // Adjust for the fact we're called after the product was popped
    // Actually, let's use the remaining count more directly
    // product_index represents which product in the batch we're on (0-indexed)
    
    bool should_qc = shouldPerformQC(product_index, qc_percentage);

    std::cout << "[QualityControlGate] Node '" << this->name() 
              << "' product " << (product_index + 1) << "/" << initial_size 
              << " (index=" << product_index << ")"
              << " QC%=" << qc_percentage 
              << " -> " << (should_qc ? "PERFORM QC" : "SKIP QC") << std::endl;

    if (should_qc)
    {
        setStatus(BT::NodeStatus::RUNNING);
        return child_node_->executeTick();
    }
    else
    {
        // Skip QC, return success
        return BT::NodeStatus::SUCCESS;
    }
}

bool QualityControlGate::shouldPerformQC(int productIndex, int qcPercentage) const
{
    // Calculate the interval at which we skip QC
    // For 90% QC: we do QC for 9 out of every 10 products, skip every 10th
    // For 85% QC: we do QC for 17 out of every 20 products, skip 3 out of every 20
    
    // Simple approach: calculate which products to skip
    // With X% QC, we skip (100-X)% of products
    // Interval = 100 / (100 - X) tells us "every Nth product is skipped"
    // For 90%: 100/10 = 10, so every 10th product is skipped
    // For 85%: 100/15 ≈ 6.67, so roughly every 6-7th product is skipped
    
    int skip_percentage = 100 - qcPercentage;
    if (skip_percentage <= 0)
    {
        return true; // 100% QC, always perform
    }

    // Use modular arithmetic with period of 100 for precise control
    // productIndex % 100 gives us position in a 100-product cycle
    // We do QC if (productIndex % 100) < qcPercentage
    int position_in_cycle = productIndex % 100;
    
    return position_in_cycle < qcPercentage;
}

BT::PortsList QualityControlGate::providedPorts()
{
    return {
        BT::InputPort<int>(
            "QCPercentage",
            100,
            "Percentage of products that should undergo quality control (0-100)"),
        BT::InputPort<int>(
            "BatchSize",
            "{BatchSize}",
            "The initial size of the product queue (set by Configure node)"),
        BT::InputPort<BT::SharedQueue<std::string>>(
            "Queue",
            "{ProductIDs}",
            "The queue of product IDs to determine current product index")
    };
}

#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/decorator_node.h>
#include <string>

/**
 * @brief QualityControlGate decorator that conditionally executes QC based on sampling rate.
 * 
 * This decorator determines whether quality control should be performed on the current product
 * based on a configurable percentage. It uses the current queue size to determine the product index
 * and calculates whether this product should be quality controlled.
 * 
 * For example, with 90% QC rate:
 * - Products at indices 0-8 get QC (indices where index % 10 < 9)
 * - Product at index 9 skips QC (every 10th product)
 * 
 * Inputs:
 * - QCPercentage: The percentage of products that should undergo quality control (0-100)
 * - Queue: The product queue to determine current product index from initial size
 * - BatchSize: The initial size of the queue (set by Configure node)
 * 
 * Behavior:
 * - If QC should be performed: tick child and return its status
 * - If QC should be skipped: return SUCCESS immediately without ticking child
 */
class QualityControlGate : public BT::DecoratorNode
{
public:
    QualityControlGate(const std::string &name, const BT::NodeConfig &config)
        : BT::DecoratorNode(name, config)
    {
    }

    BT::NodeStatus tick() override;
    
    static BT::PortsList providedPorts();

private:
    /**
     * @brief Determine if QC should be performed for the given product index.
     * 
     * Uses modular arithmetic to determine if this product falls within the QC sampling.
     * For 90% QC: products where (productIndex % interval) < (interval * percentage / 100) get QC
     * 
     * @param productIndex The 0-based index of the current product in the batch
     * @param qcPercentage The percentage of products that should get QC (0-100)
     * @return true if QC should be performed, false to skip
     */
    bool shouldPerformQC(int productIndex, int qcPercentage) const;
};

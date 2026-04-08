#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/decorator_node.h>
#include <string>

/**
 * @brief SamplingGate decorator that conditionally executes its child based on a sampling rate.
 * 
 * This is a generic decorator that determines whether to execute its child node for the current
 * product based on a configurable percentage. It uses the current queue size to determine the 
 * product index and calculates whether this product should be processed.
 * 
 * Use cases:
 * - Quality control / inspection sampling (e.g., inspect 90% of products)
 * - In-process weighing sampling
 * - Any operation where only a percentage of products should be processed
 * 
 * For example, with 90% sampling rate:
 * - Products at indices 0-8 are processed (indices where index % 10 < 9)
 * - Product at index 9 is skipped (every 10th product)
 * 
 * Inputs:
 * - SamplingRate: The percentage of products that should be processed (0-100)
 * - Queue: The product queue to determine current product index from initial size
 * - BatchSize: The initial size of the queue (set by Configure node)
 * 
 * Behavior:
 * - If product should be processed: tick child and return its status
 * - If product should be skipped: return SUCCESS immediately without ticking child
 */
class SamplingGate : public BT::DecoratorNode
{
public:
    SamplingGate(const std::string &name, const BT::NodeConfig &config)
        : BT::DecoratorNode(name, config)
    {
    }

    BT::NodeStatus tick() override;
    
    static BT::PortsList providedPorts();

private:
    /**
     * @brief Determine if the child should be executed for the given product index.
     * 
     * Uses modular arithmetic to determine if this product falls within the sampling.
     * For 90% rate: products where (productIndex % 100) < 90 get processed
     * 
     * @param productIndex The 0-based index of the current product in the batch
     * @param samplingRate The percentage of products that should be processed (0-100)
     * @return true if child should be executed, false to skip
     */
    bool shouldExecute(int productIndex, int samplingRate) const;
};

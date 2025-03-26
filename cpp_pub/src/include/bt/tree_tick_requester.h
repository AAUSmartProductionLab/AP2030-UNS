#ifndef TREE_TICK_REQUESTER_H
#define TREE_TICK_REQUESTER_H

#include <condition_variable>
#include <mutex>
#include <chrono>
#include <iostream>

/**
 * @brief A utility class that allows any node to request a behavior tree tick.
 *
 * This class provides a centralized mechanism for any node type to signal
 * that the behavior tree should be ticked again. It uses a static condition
 * variable to synchronize between the tree execution thread and node threads.
 */
class TreeTickRequester
{
public:
    /**
     * @brief Request a tick of the behavior tree
     *
     * Called by any node that needs to trigger a tree evaluation
     */
    static void requestTick();

    /**
     * @brief Wait for a tick request with a timeout
     *
     * Called by the main execution loop to wait for node signals
     *
     * @param timeout Maximum time to wait before returning
     * @return true if a tick was requested, false if timeout occurred
     */
    static bool waitForTickRequest(const std::chrono::milliseconds &timeout);

    /**
     * @brief Wait for a tick request indefinitely
     *
     * Called by the main execution loop to wait for node signals
     */
    static void waitForTickRequest();

private:
    /// Condition variable for signaling tick requests
    static std::condition_variable tick_request_signal_;

    /// Mutex for protecting shared state
    static std::mutex tick_request_mutex_;

    /// Flag indicating if a tick has been requested
    static bool tick_requested_;
};

#endif // TREE_TICK_REQUESTER_H
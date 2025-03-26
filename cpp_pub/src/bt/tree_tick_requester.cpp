#include "bt/tree_tick_requester.h"

std::condition_variable TreeTickRequester::tick_request_signal_;
std::mutex TreeTickRequester::tick_request_mutex_;
bool TreeTickRequester::tick_requested_ = false;

void TreeTickRequester::requestTick()
{
    {
        std::lock_guard<std::mutex> lock(tick_request_mutex_);
        tick_requested_ = true;
    }
    tick_request_signal_.notify_all();
}

bool TreeTickRequester::waitForTickRequest(const std::chrono::milliseconds &timeout)
{
    std::unique_lock<std::mutex> lock(tick_request_mutex_);
    bool result = tick_request_signal_.wait_for(lock, timeout, []()
                                                { return tick_requested_; });

    if (result)
    {
        // Reset the flag if a tick was actually requested
        tick_requested_ = false;
    }

    return result;
}

void TreeTickRequester::waitForTickRequest()
{
    std::unique_lock<std::mutex> lock(tick_request_mutex_);
    tick_request_signal_.wait(lock, []()
                              { return tick_requested_; });

    // Reset the flag
    tick_requested_ = false;
}
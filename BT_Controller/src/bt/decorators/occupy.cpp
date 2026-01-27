#include "bt/decorators/occupy.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
#include <iomanip>
#include <utils.h>
#include <algorithm>

// Helper to get current timestamp for logging
static std::string getOccupyLogTimestamp()
{
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
    auto time = std::chrono::system_clock::to_time_t(now);
    std::tm tm = *std::localtime(&time);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%H:%M:%S") << '.' << std::setfill('0') << std::setw(3) << ms.count();
    return oss.str();
}

// Helper functions to generate unique topic keys per asset
std::string Occupy::getOccupyRequestKey(const std::string &asset_id) const
{
    return "occupyRequest_" + asset_id;
}

std::string Occupy::getReleaseRequestKey(const std::string &asset_id) const
{
    return "releaseRequest_" + asset_id;
}

std::string Occupy::getOccupyResponseKey(const std::string &asset_id) const
{
    return "occupyResponse_" + asset_id;
}

std::string Occupy::getReleaseResponseKey(const std::string &asset_id) const
{
    return "releaseResponse_" + asset_id;
}

void Occupy::initializeTopicsFromAAS()
{
    // Already initialized, skip
    if (topics_initialized_)
    {
        return;
    }

    try
    {
        // Get the list of assets from input
        auto assets_input = getInput<std::vector<std::string>>("Assets");
        if (!assets_input.has_value() || assets_input.value().empty())
        {
            std::cerr << "Node '" << this->name() << "' has no Assets input configured or list is empty" << std::endl;
            return;
        }

        asset_ids_ = assets_input.value();
        std::cout << "Node '" << this->name() << "' initializing for " << asset_ids_.size() << " assets" << std::endl;

        // Initialize topics for each asset
        bool all_initialized = true;
        for (const auto &asset_id : asset_ids_)
        {
            std::cout << "  - Fetching interfaces for asset: " << asset_id << std::endl;

            auto occupy_req = aas_client_.fetchInterface(asset_id, "Occupy", "input");
            auto occupy_resp = aas_client_.fetchInterface(asset_id, "Occupy", "output");
            auto release_req = aas_client_.fetchInterface(asset_id, "Release", "input");
            auto release_resp = aas_client_.fetchInterface(asset_id, "Release", "output");

            if (!occupy_req.has_value() || !occupy_resp.has_value() ||
                !release_req.has_value() || !release_resp.has_value())
            {
                std::cerr << "Failed to fetch interfaces from AAS for asset: " << asset_id
                          << " in node: " << this->name() << std::endl;
                all_initialized = false;
                continue;
            }

            // Set topics with asset-specific keys
            MqttPubBase::setTopic(getOccupyRequestKey(asset_id), occupy_req.value());
            MqttPubBase::setTopic(getReleaseRequestKey(asset_id), release_req.value());
            MqttSubBase::setTopic(getOccupyResponseKey(asset_id), occupy_resp.value());
            MqttSubBase::setTopic(getReleaseResponseKey(asset_id), release_resp.value());
        }

        // Only mark initialized if we set up at least one asset
        if (!asset_ids_.empty() && all_initialized)
        {
            topics_initialized_ = true;
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Exception initializing topics from AAS: " << e.what() << std::endl;
    }
}

BT::NodeStatus Occupy::tick()
{
    // Ensure lazy initialization is done
    if (!ensureInitialized())
    {
        auto assets = getInput<std::vector<std::string>>("Assets");
        std::cerr << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                  << "' FAILED - could not initialize. "
                  << "Assets count=" << (assets.has_value() ? std::to_string(assets.value().size()) : "<not set>") << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    if (status() == BT::NodeStatus::IDLE)
    {
        current_phase_ = PackML::State::STARTING;
        selected_asset_id_.clear();
        pending_assets_.clear();
        assets_to_release_.clear();
        assets_with_pending_requests_.clear();
        occupy_uuid_.clear();
        sendRegisterCommandToAll();
        return BT::NodeStatus::RUNNING;
    }

    if (current_phase_ == PackML::State::EXECUTE)
    {
        BT::NodeStatus child_state = child_node_->executeTick();
        if (child_state == BT::NodeStatus::FAILURE)
        {
            std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                      << "' child FAILED, releasing " << selected_asset_id_ << std::endl;
            current_phase_ = PackML::State::STOPPING;
            sendUnregisterCommand(selected_asset_id_);
            return BT::NodeStatus::RUNNING;
        }
        else if (child_state == BT::NodeStatus::SUCCESS)
        {
            std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                      << "' child SUCCESS, releasing " << selected_asset_id_ << std::endl;
            resetChild();
            current_phase_ = PackML::State::COMPLETING;
            sendUnregisterCommand(selected_asset_id_);
            return BT::NodeStatus::RUNNING;
        }
    }
    else if (current_phase_ == PackML::State::STOPPED)
    {
        current_phase_ = PackML::State::IDLE;
        return BT::NodeStatus::FAILURE;
    }
    else if (current_phase_ == PackML::State::COMPLETE)
    {
        current_phase_ = PackML::State::IDLE;
        return BT::NodeStatus::SUCCESS;
    }

    return BT::NodeStatus::RUNNING;
}

void Occupy::halt()
{
    std::lock_guard<std::mutex> lock(mutex_);

    std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
              << "' HALT called, releasing all assets with UUID=" << occupy_uuid_ << std::endl;

    // Release all assets that still have pending requests
    // Make a copy since sendUnregisterCommand modifies the set
    std::set<std::string> to_release = assets_with_pending_requests_;
    for (const auto &asset_id : to_release)
    {
        std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                  << "' halt: releasing " << asset_id << std::endl;
        sendUnregisterCommand(asset_id);
    }

    DecoratorNode::halt();
}

void Occupy::sendRegisterCommandToAll()
{
    // Generate ONE UUID for this entire occupy operation - same UUID sent to all assets
    // This makes it traceable which Occupy node made which requests
    occupy_uuid_ = mqtt_utils::generate_uuid();
    
    std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
              << "' starting occupation with UUID=" << occupy_uuid_ 
              << " for " << asset_ids_.size() << " assets" << std::endl;

    for (const auto &asset_id : asset_ids_)
    {
        // Check if we have valid topics for this asset
        if (MqttPubBase::topics_.find(getOccupyRequestKey(asset_id)) == MqttPubBase::topics_.end())
        {
            std::cerr << "[" << getOccupyLogTimestamp() << "] [Occupy] No occupy topic configured for asset: " 
                      << asset_id << std::endl;
            continue;
        }

        sendRegisterCommand(asset_id);
    }
}

void Occupy::sendRegisterCommand(const std::string &asset_id)
{
    json message;

    // Use the single UUID for all assets in this occupy operation
    // Track that we sent a request to this asset
    assets_with_pending_requests_.insert(asset_id);
    pending_assets_.insert(asset_id);

    message["Uuid"] = occupy_uuid_;

    std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
              << "' -> OCCUPY REQUEST to " << asset_id 
              << " with UUID=" << occupy_uuid_ << std::endl;
    MqttPubBase::publish(getOccupyRequestKey(asset_id), message);
}

void Occupy::sendUnregisterCommand(const std::string &asset_id)
{
    if (occupy_uuid_.empty())
    {
        std::cerr << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                  << "' - No UUID set - cannot send release to " << asset_id << std::endl;
        return;
    }

    // Check if we actually sent a request to this asset
    if (assets_with_pending_requests_.find(asset_id) == assets_with_pending_requests_.end())
    {
        std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                  << "' - No pending request for " << asset_id << " - skipping release" << std::endl;
        return;
    }

    json message;
    message["Uuid"] = occupy_uuid_;

    std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
              << "' -> RELEASE REQUEST to " << asset_id 
              << " with UUID=" << occupy_uuid_ << std::endl;
    MqttPubBase::publish(getReleaseRequestKey(asset_id), message);
    
    // Mark that we've sent a release for this asset
    assets_with_pending_requests_.erase(asset_id);
}

void Occupy::releaseNonSelectedAssets()
{
    std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
              << "' releasing " << assets_with_pending_requests_.size() 
              << " non-selected assets (selected=" << selected_asset_id_ << ")" << std::endl;

    // Make a copy since sendUnregisterCommand modifies the set
    std::set<std::string> assets_to_release_copy = assets_with_pending_requests_;
    
    for (const auto &asset_id : assets_to_release_copy)
    {
        if (asset_id != selected_asset_id_)
        {
            sendUnregisterCommand(asset_id);
        }
    }
}

void Occupy::callback(const std::string &topic_key, const json &msg, mqtt::properties props)
{
    std::lock_guard<std::mutex> lock(mutex_);

    if (status() != BT::NodeStatus::RUNNING)
    {
        return;
    }

    std::string received_uuid = msg.at("Uuid").get<std::string>();
    std::string state = msg.at("State").get<std::string>();

    // Check if this response is for our UUID
    if (received_uuid != occupy_uuid_)
    {
        // Not our response
        return;
    }

    // Find which asset this response belongs to by matching the topic key
    std::string responding_asset;
    for (const auto &asset_id : asset_ids_)
    {
        if (topic_key == getOccupyResponseKey(asset_id) || 
            topic_key == getReleaseResponseKey(asset_id))
        {
            responding_asset = asset_id;
            break;
        }
    }

    if (responding_asset.empty())
    {
        std::cerr << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                  << "' received response on unknown topic_key: " << topic_key << std::endl;
        return;
    }

    // Handle occupy responses (during STARTING phase)
    if (topic_key == getOccupyResponseKey(responding_asset))
    {
        std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                  << "' <- OCCUPY RESPONSE from " << responding_asset 
                  << ": " << state << " (UUID=" << received_uuid << ")" 
                  << " phase=" << static_cast<int>(current_phase_) << std::endl;

        if (current_phase_ == PackML::State::STARTING)
        {
            pending_assets_.erase(responding_asset);

            if (state == "SUCCESS")
            {
                if (selected_asset_id_.empty())
                {
                    // First successful response - this is our selected asset
                    selected_asset_id_ = responding_asset;

                    // Set the selected asset as output
                    setOutput("SelectedAsset", selected_asset_id_);
                    setOutput("Uuid", occupy_uuid_);

                    std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                              << "' SELECTED asset: " << selected_asset_id_ 
                              << " (UUID=" << occupy_uuid_ << ")" << std::endl;

                    // Release ALL other assets that we sent requests to (not just pending ones)
                    // This ensures we don't leave stale requests in asset queues
                    releaseNonSelectedAssets();
                    pending_assets_.clear();

                    // Transition to EXECUTE - we have our asset
                    current_phase_ = PackML::State::EXECUTE;
                }
                else
                {
                    // Already have a selected asset, need to release this one immediately
                    std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                              << "' asset " << responding_asset << " also succeeded but "
                              << selected_asset_id_ << " was already selected - releasing" << std::endl;
                    sendUnregisterCommand(responding_asset);
                }
            }
            else if (state == "FAILURE")
            {
                std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                          << "' asset " << responding_asset << " FAILED occupation request" << std::endl;

                // If all assets have failed, transition to STOPPED
                if (pending_assets_.empty() && selected_asset_id_.empty())
                {
                    std::cerr << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                              << "' ALL assets failed occupation - node failing" << std::endl;
                    current_phase_ = PackML::State::STOPPED;
                }
            }
        }
    }
    // Handle release responses
    else if (topic_key == getReleaseResponseKey(responding_asset))
    {
        std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                  << "' <- RELEASE RESPONSE from " << responding_asset 
                  << ": " << state << " (UUID=" << received_uuid << ")" << std::endl;

        assets_to_release_.erase(responding_asset);

        if (responding_asset == selected_asset_id_)
        {
            // This is the release of our main selected asset
            if (state == "SUCCESS")
            {
                std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                          << "' successfully released selected asset: " << responding_asset << std::endl;
                          
                if (current_phase_ == PackML::State::COMPLETING)
                {
                    current_phase_ = PackML::State::COMPLETE;
                }
                else if (current_phase_ == PackML::State::STOPPING)
                {
                    current_phase_ = PackML::State::STOPPED;
                }
            }
            else if (state == "FAILURE")
            {
                std::cerr << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                          << "' FAILED to release selected asset: " << responding_asset << std::endl;
                current_phase_ = PackML::State::STOPPED;
            }
        }
        // For non-selected assets, we just log
        else
        {
            std::cout << "[" << getOccupyLogTimestamp() << "] [Occupy] Node '" << this->name() 
                      << "' released non-selected asset: " << responding_asset
                      << " with state: " << state << std::endl;
        }
    }

    emitWakeUpSignal();
}

BT::PortsList Occupy::providedPorts()
{
    return {
        BT::InputPort<std::vector<std::string>>(
            "Assets",
            "List of asset IDs to attempt occupation on"),
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::OUTPUT,
            "SelectedAsset",
            "{SelectedAsset}",
            "The Asset that has accepted our request"),
        BT::details::PortWithDefault<std::string>(
            BT::PortDirection::INOUT,
            "Uuid",
            "{Uuid}",
            "UUID of the selected asset's occupation request")};
}
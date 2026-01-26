#include "bt/decorators/occupy.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
#include <utils.h>
#include <algorithm>

// Helper functions to generate unique topic keys per asset
std::string Occupy::getOccupyRequestKey(const std::string& asset_id) const
{
    return "occupyRequest_" + asset_id;
}

std::string Occupy::getReleaseRequestKey(const std::string& asset_id) const
{
    return "releaseRequest_" + asset_id;
}

std::string Occupy::getOccupyResponseKey(const std::string& asset_id) const
{
    return "occupyResponse_" + asset_id;
}

std::string Occupy::getReleaseResponseKey(const std::string& asset_id) const
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
        for (const auto& asset_id : asset_ids_)
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
        std::cerr << "Node '" << this->name() << "' FAILED - could not initialize. "
                  << "Assets count=" << (assets.has_value() ? std::to_string(assets.value().size()) : "<not set>") << std::endl;
        return BT::NodeStatus::FAILURE;
    }

    if (status() == BT::NodeStatus::IDLE)
    {
        current_phase_ = PackML::State::STARTING;
        selected_asset_id_.clear();
        pending_assets_.clear();
        assets_to_release_.clear();
        asset_uuids_.clear();
        sendRegisterCommandToAll();
        return BT::NodeStatus::RUNNING;
    }

    if (current_phase_ == PackML::State::EXECUTE)
    {
        BT::NodeStatus child_state = child_node_->executeTick();
        if (child_state == BT::NodeStatus::FAILURE)
        {
            current_phase_ = PackML::State::STOPPING;
            sendUnregisterCommand(selected_asset_id_);
            return BT::NodeStatus::RUNNING;
        }
        else if (child_state == BT::NodeStatus::SUCCESS)
        {
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
    
    // Release the selected asset if we have one
    if (!selected_asset_id_.empty())
    {
        sendUnregisterCommand(selected_asset_id_);
    }
    
    // Also release any assets that were pending
    for (const auto& asset_id : pending_assets_)
    {
        if (MqttPubBase::topics_.find(getReleaseRequestKey(asset_id)) != MqttPubBase::topics_.end())
        {
            sendUnregisterCommand(asset_id);
        }
    }
    
    DecoratorNode::halt();
}

void Occupy::sendRegisterCommandToAll()
{
    // Try to get UUID from input, or generate new ones per asset
    BT::Expected<std::string> base_uuid = getInput<std::string>("Uuid");
    
    for (const auto& asset_id : asset_ids_)
    {
        // Check if we have valid topics for this asset
        if (MqttPubBase::topics_.find(getOccupyRequestKey(asset_id)) == MqttPubBase::topics_.end())
        {
            std::cerr << "No occupy topic configured for asset: " << asset_id << std::endl;
            continue;
        }
        
        sendRegisterCommand(asset_id);
    }
}

void Occupy::sendRegisterCommand(const std::string& asset_id)
{
    json message;
    
    // Generate a unique UUID for each asset request
    std::string uuid = mqtt_utils::generate_uuid();
    asset_uuids_[asset_id] = uuid;
    pending_assets_.insert(asset_id);
    
    message["Uuid"] = uuid;
    
    std::cout << "Sending occupy request to asset: " << asset_id << " with UUID: " << uuid << std::endl;
    MqttPubBase::publish(getOccupyRequestKey(asset_id), message);
}

void Occupy::sendUnregisterCommand(const std::string& asset_id)
{
    if (asset_uuids_.find(asset_id) == asset_uuids_.end())
    {
        std::cerr << "No UUID found for asset: " << asset_id << " - cannot send release" << std::endl;
        return;
    }
    
    json message;
    message["Uuid"] = asset_uuids_[asset_id];
    
    std::cout << "Sending release request to asset: " << asset_id << std::endl;
    MqttPubBase::publish(getReleaseRequestKey(asset_id), message);
}

void Occupy::releaseNonSelectedAssets()
{
    std::cout << "Releasing " << assets_to_release_.size() << " non-selected assets" << std::endl;
    
    for (const auto& asset_id : assets_to_release_)
    {
        sendUnregisterCommand(asset_id);
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

    // Find which asset this response belongs to
    std::string responding_asset;
    for (const auto& [asset_id, uuid] : asset_uuids_)
    {
        if (uuid == received_uuid)
        {
            responding_asset = asset_id;
            break;
        }
    }

    if (responding_asset.empty())
    {
        // UUID doesn't match any of our requests
        return;
    }

    // Handle occupy responses (during STARTING phase)
    if (topic_key == getOccupyResponseKey(responding_asset))
    {
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
                    setOutput("Uuid", asset_uuids_[selected_asset_id_]);
                    
                    std::cout << "Asset " << selected_asset_id_ << " selected for occupation" << std::endl;

                    // Mark remaining pending assets for release when they respond
                    // Also add any assets that haven't responded yet
                    for (const auto& asset_id : pending_assets_)
                    {
                        assets_to_release_.insert(asset_id);
                    }
                    
                    // Transition to EXECUTE - we have our asset
                    current_phase_ = PackML::State::EXECUTE;
                }
                else
                {
                    // Already have a selected asset, need to release this one
                    std::cout << "Asset " << responding_asset << " also succeeded but " 
                              << selected_asset_id_ << " was already selected - releasing" << std::endl;
                    sendUnregisterCommand(responding_asset);
                }
            }
            else if (state == "FAILURE")
            {
                std::cout << "Asset " << responding_asset << " failed occupation request" << std::endl;
                
                // If all assets have failed, transition to STOPPED
                if (pending_assets_.empty() && selected_asset_id_.empty())
                {
                    std::cerr << "All assets failed occupation - node failing" << std::endl;
                    current_phase_ = PackML::State::STOPPED;
                }
            }
        }
    }
    // Handle release responses
    else if (topic_key == getReleaseResponseKey(responding_asset))
    {
        assets_to_release_.erase(responding_asset);
        
        if (responding_asset == selected_asset_id_)
        {
            // This is the release of our main selected asset
            if (state == "SUCCESS")
            {
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
                std::cerr << "Failed to release selected asset: " << responding_asset << std::endl;
                current_phase_ = PackML::State::STOPPED;
            }
        }
        // For non-selected assets, we just log and continue
        else
        {
            std::cout << "Released non-selected asset: " << responding_asset 
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
            "UUID of the selected asset's occupation request")
    };
}
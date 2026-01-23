#pragma once

#include "bt/mqtt_decorator.h"
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include "mqtt/mqtt_pub_base.h"
#include <fmt/chrono.h>
#include <chrono>
#include <utils.h>

/**
 * @brief Occupy decorator that requests occupation from multiple assets and selects the first successful one.
 * 
 * This node sends occupation requests to all provided assets simultaneously and waits for responses.
 * When the first asset responds with SUCCESS, it:
 * 1. Sets that asset as the selected/occupied asset (output)
 * 2. Releases all other pending occupation requests
 * 3. Executes the child node with the selected asset
 * 4. Upon completion, releases the occupied asset
 * 
 * This enables flexible resource assignment where assets handle their own queueing internally.
 */
class Occupy : public MqttDecorator
{
private:
    std::mutex mutex_;
    PackML::State current_phase_ = PackML::State::IDLE;

    // Multi-asset tracking
    std::vector<std::string> asset_ids_;                          // All candidate assets from input
    std::string selected_asset_id_;                                // The asset that was successfully occupied
    std::unordered_map<std::string, std::string> asset_uuids_;     // asset_id -> UUID for each request
    std::unordered_set<std::string> pending_assets_;               // Assets waiting for occupy response
    std::unordered_set<std::string> assets_to_release_;            // Assets that need release (occupied but not selected)

    // Helper to generate topic keys per asset
    std::string getOccupyRequestKey(const std::string& asset_id) const;
    std::string getReleaseRequestKey(const std::string& asset_id) const;
    std::string getOccupyResponseKey(const std::string& asset_id) const;
    std::string getReleaseResponseKey(const std::string& asset_id) const;

public:
    Occupy(
        const std::string &name,
        const BT::NodeConfig &config,
        MqttClient &mqtt_client,
        AASClient &aas_client)
        : MqttDecorator(name, config, mqtt_client, aas_client)
    {
    }

    // Mqtt AAS Stuff
    void initializeTopicsFromAAS() override;
    void sendRegisterCommandToAll();
    void sendRegisterCommand(const std::string& asset_id);
    void sendUnregisterCommand(const std::string& asset_id);
    void releaseNonSelectedAssets();
    void callback(const std::string &topic_key, const json &msg, mqtt::properties props) override;

    // BT Stuff
    BT::NodeStatus tick() override;
    void halt() override;

    static BT::PortsList providedPorts();
};
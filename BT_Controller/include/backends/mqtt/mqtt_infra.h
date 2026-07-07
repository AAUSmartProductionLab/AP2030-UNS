#pragma once

#include <chrono>
#include <memory>
#include <string>
#include <vector>
#include <functional>

#include "backends/mqtt/mqtt_client.h"

class NodeMessageDistributor;
class SkillInterfaceCache;
class AASClient;
class MqttAidProtocolParser;

namespace BT
{
    class Tree;
}

/// Owns the MQTT runtime infrastructure shared by all MQTT backends:
///   - IMqttClient             (MQTT transport — created internally)
///   - NodeMessageDistributor  (routes incoming messages to MqttSubBase instances)
///   - SkillInterfaceCache      (caches resolved skill interfaces)
///
/// Also manages the MQTT client's incoming-message handler.
/// Created once by BackendRegistry::configure().
class MqttInfra
{
public:
    /// `server_uri` and `client_id` are the Paho connection parameters.
    MqttInfra(const std::string &server_uri,
              const std::string &client_id,
              AASClient &aas_client);
    ~MqttInfra();

    /// Wire the MQTT client's message handler to route through the NMD.
    void initialize();

    /// Remove the message handler.
    void shutdown();

    // ── Accessors ─────────────────────────────────────────────────
    NodeMessageDistributor *getNmd() { return nmd_.get(); }
    SkillInterfaceCache *getInterfaceCache() { return iface_cache_.get(); }
    IMqttClient *getMqttClient() { return mqtt_client_.get(); }
    AASClient &getAasClient() { return aas_client_; }

    // ── Operations the controller needs ───────────────────────────
    /// Unsubscribe from a list of topic patterns (used during teardown).
    void unsubscribeTopics(const std::vector<std::string> &topics);

    /// Temporarily stop routing incoming messages (e.g. during BT loading).
    void suspendRouting();

    /// Resume routing after a suspendRouting() call.
    void resumeRouting();

    /// Full execution prep: suspend routing, subscribe to active-node
    /// topics (triggers retained-message delivery), resume routing.
    /// Called once by BackendRegistry::prepareForExecution().
    void prepareForExecution(const BT::Tree &tree,
                             std::chrono::milliseconds timeout = std::chrono::seconds(5));

private:
    void setHandlerActive(bool active);

    AASClient &aas_client_;
    std::unique_ptr<IMqttClient> mqtt_client_;
    std::unique_ptr<NodeMessageDistributor> nmd_;
    std::unique_ptr<SkillInterfaceCache> iface_cache_;
    std::unique_ptr<MqttAidProtocolParser> mqtt_aid_parser_;

    /// Saved handler — captured on suspend, restored on resume.
    IMqttClient::MessageCallback saved_handler_;
};

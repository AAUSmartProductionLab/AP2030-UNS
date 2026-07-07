#pragma once

#include <optional>
#include <string>
#include <vector>

/// Abstract interface for querying predicate truth values from a
/// knowledge graph. Implementations may talk to Fuseki (SPARQL),
/// GraphDB, an in-process RDF store, etc.
///
/// Predicate facts in the KG are expected to follow this shape
/// (materialized by Phase B predicate reasoner):
///
///   ?fact a apex:PredicateInstance ;
///         apex:predicateName "Operational" ;
///         apex:arguments "shuttle1" ;
///         apex:truthValue true .
class KgClient
{
public:
    virtual ~KgClient() = default;

    /// Ask whether a predicate holds for the given arguments.
    ///
    /// @param predicate  The predicate name (e.g. "Operational", "Occupied").
    /// @param args       Ordered argument values (e.g. {"shuttle1"}).
    /// @return true if the KG contains a matching true predicate fact,
    ///         false if the KG contains a matching false fact or no fact,
    ///         std::nullopt on query failure (network error, parse error).
    virtual std::optional<bool> askPredicate(
        const std::string &predicate,
        const std::vector<std::string> &args) const = 0;

    /// Raw SPARQL ASK query. Returns true/false/nullopt.
    /// Exposed for testing and for predicates with non-standard shapes.
    virtual std::optional<bool> ask(const std::string &sparql_query) const = 0;

    /// Check whether the client is configured and ready.
    virtual bool isConfigured() const = 0;

    // ── Write methods (SPARQL UPDATE) ──────────────────────────

    /// Insert a predicate fact with truthValue true.
    /// @return true on success, false on failure.
    virtual bool insertFact(const std::string &predicate,
                            const std::vector<std::string> &args) = 0;

    /// Delete a predicate fact (remove it from the KG).
    /// @return true on success, false on failure.
    virtual bool deleteFact(const std::string &predicate,
                            const std::vector<std::string> &args) = 0;

    /// Send a raw SPARQL UPDATE string to the update endpoint.
    /// @return true on success, false on failure.
    virtual bool update(const std::string &sparql_update) = 0;
};

/// KgClient implementation backed by an Apache Jena Fuseki SPARQL
/// endpoint. Sends SPARQL ASK queries via HTTP POST, parses the JSON
/// boolean result.
///
/// The controller pulls predicate state from the KG on demand — no MQTT
/// push from KG. Each call is a synchronous HTTP round-trip (~5-50ms).
class FusekiQueryClient : public KgClient
{
public:
    /// @param fuseki_query_url  Full URL of the Fuseki SPARQL query endpoint
    ///                          (e.g. "http://kg-fuseki:3030/kg/sparql").
    /// @param abox_graph        The named graph URI for ABox (instance) data
    ///                          (e.g. "urn:kg:abox").
    /// @param timeout_seconds   HTTP request timeout in seconds.
    FusekiQueryClient(const std::string &fuseki_query_url,
                      const std::string &fuseki_update_url,
                      const std::string &abox_graph = "urn:kg:abox",
                      long timeout_seconds = 5);

    ~FusekiQueryClient() override;

    std::optional<bool> askPredicate(
        const std::string &predicate,
        const std::vector<std::string> &args) const override;

    std::optional<bool> ask(const std::string &sparql_query) const override;

    bool isConfigured() const override;

    bool insertFact(const std::string &predicate,
                    const std::vector<std::string> &args) override;

    bool deleteFact(const std::string &predicate,
                    const std::vector<std::string> &args) override;

    bool update(const std::string &sparql_update) override;

private:
    std::string fuseki_query_url_;
    std::string fuseki_update_url_;
    std::string abox_graph_;
    long timeout_seconds_;

    bool sendUpdate(const std::string &sparql_update) const;
};

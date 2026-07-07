#include "backends/kg/kg_query_client.h"

#include <curl/curl.h>

#include <iostream>
#include <sstream>

namespace
{
    size_t writeCallback(void *contents, size_t size, size_t nmemb, void *userp)
    {
        static_cast<std::string *>(userp)->append(static_cast<char *>(contents), size * nmemb);
        return size * nmemb;
    }

    std::string joinArgs(const std::vector<std::string> &args)
    {
        std::ostringstream oss;
        for (size_t i = 0; i < args.size(); ++i)
        {
            if (i > 0)
            {
                oss << ",";
            }
            oss << args[i];
        }
        return oss.str();
    }
} // namespace

FusekiQueryClient::FusekiQueryClient(const std::string &fuseki_query_url,
                                     const std::string &fuseki_update_url,
                                     const std::string &abox_graph,
                                     long timeout_seconds)
    : fuseki_query_url_(fuseki_query_url),
      fuseki_update_url_(fuseki_update_url),
      abox_graph_(abox_graph),
      timeout_seconds_(timeout_seconds)
{
    curl_global_init(CURL_GLOBAL_DEFAULT);
}

FusekiQueryClient::~FusekiQueryClient()
{
    curl_global_cleanup();
}

bool FusekiQueryClient::isConfigured() const
{
    return !fuseki_query_url_.empty();
}

std::optional<bool> FusekiQueryClient::askPredicate(
    const std::string &predicate,
    const std::vector<std::string> &args) const
{
    const std::string args_str = joinArgs(args);

    // Build SPARQL ASK query.  The predicate may be a short PDDL name
    // (e.g. "free") or a full ontology URI (e.g.
    // "https://w3id.org/2026/apex/Free").  Both are matched as string
    // literals against apex:predicateName in the KG.
    std::ostringstream q;
    q << "PREFIX apex: <https://w3id.org/2026/apex/>\n"
      << "ASK WHERE {\n"
      << "  GRAPH <" << abox_graph_ << "> {\n"
      << "    ?fact a apex:PredicateInstance ;\n"
      << "          apex:predicateName \"" << predicate << "\" ;\n"
      << "          apex:arguments \"" << args_str << "\" ;\n"
      << "          apex:truthValue true .\n"
      << "  }\n"
      << "}";

    return ask(q.str());
}

std::optional<bool> FusekiQueryClient::ask(const std::string &sparql_query) const
{
    if (!isConfigured())
    {
        return std::nullopt;
    }

    CURL *curl = curl_easy_init();
    if (!curl)
    {
        return std::nullopt;
    }

    std::string response;
    curl_easy_setopt(curl, CURLOPT_URL, fuseki_query_url_.c_str());
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, sparql_query.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE,
                     static_cast<long>(sparql_query.size()));
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout_seconds_);

    struct curl_slist *headers = nullptr;
    headers = curl_slist_append(headers,
                                "Accept: application/sparql-results+json");
    headers = curl_slist_append(headers,
                                "Content-Type: application/sparql-query");
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || http_code != 200)
    {
        std::cerr << "FusekiQueryClient: SPARQL query failed (HTTP " << http_code
                  << ", CURL " << res << ")" << std::endl;
        return std::nullopt;
    }

    // Fuseki returns {"head": {}, "boolean": true/false} for ASK queries.
    // Simple string search avoids pulling in nlohmann::json just for this.
    if (response.find("\"boolean\"") == std::string::npos)
    {
        std::cerr << "FusekiQueryClient: unexpected SPARQL ASK response: "
                  << response.substr(0, 200) << std::endl;
        return std::nullopt;
    }
    return response.find("\"boolean\": true") != std::string::npos;
}

// ── Write methods ───────────────────────────────────────────────────

bool FusekiQueryClient::insertFact(const std::string &predicate,
                                   const std::vector<std::string> &args)
{
    const std::string args_str = joinArgs(args);

    std::ostringstream q;
    q << "PREFIX apex: <https://w3id.org/2026/apex/>\n"
      << "INSERT DATA {\n"
      << "  GRAPH <" << abox_graph_ << "> {\n"
      << "    [ a apex:PredicateInstance ;\n"
      << "      apex:predicateName \"" << predicate << "\" ;\n"
      << "      apex:arguments \"" << args_str << "\" ;\n"
      << "      apex:truthValue true ] .\n"
      << "  }\n"
      << "}";

    return sendUpdate(q.str());
}

bool FusekiQueryClient::deleteFact(const std::string &predicate,
                                   const std::vector<std::string> &args)
{
    const std::string args_str = joinArgs(args);

    std::ostringstream q;
    q << "PREFIX apex: <https://w3id.org/2026/apex/>\n"
      << "DELETE DATA {\n"
      << "  GRAPH <" << abox_graph_ << "> {\n"
      << "    [ a apex:PredicateInstance ;\n"
      << "      apex:predicateName \"" << predicate << "\" ;\n"
      << "      apex:arguments \"" << args_str << "\" ;\n"
      << "      apex:truthValue true ] .\n"
      << "  }\n"
      << "}";

    return sendUpdate(q.str());
}

bool FusekiQueryClient::update(const std::string &sparql_update)
{
    return sendUpdate(sparql_update);
}

bool FusekiQueryClient::sendUpdate(const std::string &sparql_update) const
{
    if (fuseki_update_url_.empty() || !isConfigured())
    {
        std::cerr << "FusekiQueryClient: update endpoint not configured" << std::endl;
        return false;
    }

    CURL *curl = curl_easy_init();
    if (!curl)
        return false;

    std::string response;
    curl_easy_setopt(curl, CURLOPT_URL, fuseki_update_url_.c_str());
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, sparql_update.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE,
                     static_cast<long>(sparql_update.size()));
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout_seconds_);

    struct curl_slist *headers = nullptr;
    headers = curl_slist_append(headers,
                                "Content-Type: application/sparql-update");
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || (http_code < 200 || http_code >= 300))
    {
        std::cerr << "FusekiQueryClient: SPARQL update failed (HTTP " << http_code
                  << ", CURL " << res << ")" << std::endl;
        return false;
    }

    return true;
}

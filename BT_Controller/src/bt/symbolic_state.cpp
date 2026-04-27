#include "bt/symbolic_state.h"

#include "bt/execution_refs.h"

#include <cctype>

SymbolicState &SymbolicState::instance()
{
    static SymbolicState s;
    return s;
}

namespace
{
    // Lower-case ASCII fold so writes (planner-emitted effect atoms and
    // the ``_planner_initial_state`` seed, which carry mixed-case
    // identifiers like ``StationAt``/``imaLoadingSystem``/``loadingLocation``)
    // and reads (FluentCheck symbolic node names, which the planner
    // emits as lowercase ``stationat(imaloadingsystem,loadinglocation)``)
    // produce the same canonical key. Without this normalization,
    // every symbolic effect was silently invisible to the FluentChecks
    // and the BT spun on the same action forever.
    inline void appendLower(std::string &out, const std::string &s)
    {
        out.reserve(out.size() + s.size());
        for (char c : s)
        {
            out.push_back(static_cast<char>(
                std::tolower(static_cast<unsigned char>(c))));
        }
    }
} // namespace

std::string SymbolicState::canonicalKey(const std::string &predicate,
                                        const std::vector<std::string> &args)
{
    std::string key;
    key.reserve(predicate.size() + 2 + args.size() * 8);
    appendLower(key, predicate);
    key.push_back('(');
    for (size_t i = 0; i < args.size(); ++i)
    {
        if (i > 0)
        {
            key.push_back(',');
        }
        appendLower(key, args[i]);
    }
    key.push_back(')');
    return key;
}

void SymbolicState::seed(const std::vector<bt_exec_refs::GroundedAtom> &atoms)
{
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto &atom : atoms)
    {
        store_[canonicalKey(atom.predicate, atom.args)] = atom.value;
    }
}

void SymbolicState::clear()
{
    std::lock_guard<std::mutex> lock(mutex_);
    store_.clear();
}

std::optional<nlohmann::json> SymbolicState::get(const std::string &predicate,
                                                 const std::vector<std::string> &args) const
{
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = store_.find(canonicalKey(predicate, args));
    if (it == store_.end())
    {
        return std::nullopt;
    }
    return it->second;
}

bool SymbolicState::getBool(const std::string &predicate,
                            const std::vector<std::string> &args) const
{
    auto v = get(predicate, args);
    if (!v.has_value() || !v->is_boolean())
    {
        return false;
    }
    return v->get<bool>();
}

void SymbolicState::set(const std::string &predicate,
                        const std::vector<std::string> &args,
                        nlohmann::json value)
{
    std::lock_guard<std::mutex> lock(mutex_);
    store_[canonicalKey(predicate, args)] = std::move(value);
}

void SymbolicState::erase(const std::string &predicate,
                          const std::vector<std::string> &args)
{
    std::lock_guard<std::mutex> lock(mutex_);
    store_.erase(canonicalKey(predicate, args));
}

nlohmann::json SymbolicState::snapshot() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json out = nlohmann::json::object();
    for (const auto &[k, v] : store_)
    {
        out[k] = v;
    }
    return out;
}

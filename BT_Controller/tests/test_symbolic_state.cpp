// Unit tests for the in-process SymbolicState store introduced in PR4.

#include <gtest/gtest.h>

#include <thread>
#include <vector>

#include <nlohmann/json.hpp>

#include "bt/execution_refs.h"
#include "bt/symbolic_state.h"

namespace
{
    bt_exec_refs::GroundedAtom mk(std::string predicate,
                                  std::vector<std::string> args,
                                  nlohmann::json value = true)
    {
        bt_exec_refs::GroundedAtom a;
        a.predicate = std::move(predicate);
        a.args = std::move(args);
        a.value = std::move(value);
        return a;
    }
}

TEST(SymbolicState, MissingKeyReturnsNullopt)
{
    SymbolicState s;
    EXPECT_FALSE(s.get("step_done", {"order_product", "step_1"}).has_value());
    EXPECT_FALSE(s.getBool("step_done", {"order_product", "step_1"}));
}

TEST(SymbolicState, SeedThenGet)
{
    SymbolicState s;
    s.seed({
        mk("step_ready", {"order_product", "step_1_loading"}, true),
        mk("step_done", {"order_product", "step_1_loading"}, false),
    });
    EXPECT_TRUE(s.getBool("step_ready", {"order_product", "step_1_loading"}));
    EXPECT_FALSE(s.getBool("step_done", {"order_product", "step_1_loading"}));
    auto v = s.get("step_done", {"order_product", "step_1_loading"});
    ASSERT_TRUE(v.has_value());
    EXPECT_TRUE(v->is_boolean());
    EXPECT_FALSE(v->get<bool>());
}

TEST(SymbolicState, SetOverwrites)
{
    SymbolicState s;
    s.set("step_ready", {"p", "s"}, false);
    EXPECT_FALSE(s.getBool("step_ready", {"p", "s"}));
    s.set("step_ready", {"p", "s"}, true);
    EXPECT_TRUE(s.getBool("step_ready", {"p", "s"}));
}

TEST(SymbolicState, EraseRemovesKey)
{
    SymbolicState s;
    s.set("step_ready", {"p", "s"}, true);
    s.erase("step_ready", {"p", "s"});
    EXPECT_FALSE(s.get("step_ready", {"p", "s"}).has_value());
    // Erase of missing key is a no-op (no throw).
    s.erase("step_done", {"x"});
}

TEST(SymbolicState, CanonicalKeyDeterminism)
{
    EXPECT_EQ(SymbolicState::canonicalKey("step_done", {"a", "b"}),
              "step_done(a,b)");
    EXPECT_EQ(SymbolicState::canonicalKey("free", {}),
              "free()");
    EXPECT_EQ(SymbolicState::canonicalKey("p", {"x"}),
              "p(x)");
    // Same args in different SymbolicState instances yield the same key.
    auto k1 = SymbolicState::canonicalKey("step_ready", {"order_product", "step_1"});
    auto k2 = SymbolicState::canonicalKey("step_ready", {"order_product", "step_1"});
    EXPECT_EQ(k1, k2);
}

TEST(SymbolicState, JsonValueRoundTrip)
{
    SymbolicState s;
    nlohmann::json complex = {{"count", 3}, {"label", "ready"}};
    s.set("inventory", {"vialA"}, complex);
    auto v = s.get("inventory", {"vialA"});
    ASSERT_TRUE(v.has_value());
    EXPECT_EQ(*v, complex);
    // Non-bool values resolve to false on getBool().
    EXPECT_FALSE(s.getBool("inventory", {"vialA"}));
}

TEST(SymbolicState, ClearEmpties)
{
    SymbolicState s;
    s.set("a", {"x"}, true);
    s.set("b", {"y"}, true);
    s.clear();
    EXPECT_FALSE(s.get("a", {"x"}).has_value());
    EXPECT_FALSE(s.get("b", {"y"}).has_value());
    EXPECT_TRUE(s.snapshot().empty());
}

TEST(SymbolicState, SnapshotContainsCanonicalKeys)
{
    SymbolicState s;
    s.set("step_done", {"order_product", "step_1"}, true);
    auto snap = s.snapshot();
    ASSERT_TRUE(snap.contains("step_done(order_product,step_1)"));
    EXPECT_EQ(snap["step_done(order_product,step_1)"], true);
}

TEST(SymbolicState, SeedDeduplicatesByCanonicalKey)
{
    SymbolicState s;
    s.seed({
        mk("step_ready", {"p", "s"}, false),
        mk("step_ready", {"p", "s"}, true), // later wins
    });
    EXPECT_TRUE(s.getBool("step_ready", {"p", "s"}));
}

TEST(SymbolicState, ConcurrentSetGetIsSafe)
{
    SymbolicState s;
    constexpr int N = 200;
    std::thread writer([&]()
    {
        for (int i = 0; i < N; ++i)
        {
            s.set("counter", {"x"}, i);
        }
    });
    std::thread reader([&]()
    {
        for (int i = 0; i < N; ++i)
        {
            (void)s.get("counter", {"x"});
        }
    });
    writer.join();
    reader.join();
    auto v = s.get("counter", {"x"});
    ASSERT_TRUE(v.has_value());
    EXPECT_TRUE(v->is_number_integer());
}

# AAS as External Blackboard: Design & Implementation

## Overview

This document describes the integration of AAS (Asset Administration Shell) as an external 
blackboard in BehaviorTree.CPP. The implementation is done via a fork at:

**Repository:** https://github.com/tristan-schwoerer/AASBT.CPP

The fork extends BehaviorTree.CPP with native support for `$aas{path}` references, allowing
behavior tree nodes to transparently access AAS properties.

---

## Implementation Status

✅ **Completed:**
- `AASProvider` interface in `aas_provider.h`
- `CachingAASProvider` wrapper with TTL-based caching
- Blackboard extension: `setAASProvider()`, `getAASProvider()`, `resolveAASReference()`
- `getInputStamped()` extended to handle `$aas{path}` port values
- `ExprAASReference` AST node for scripting
- Grammar rules for parsing `$aas{path}` in expressions

---

## Syntax

```xml
<!-- AAS property reference syntax -->
<MoveToPosition 
    Asset="{Xbot}"
    x="$aas{aauFillingLineAAS/HierarchicalStructures/Dispensing/Location/x}"
    y="$aas{aauFillingLineAAS/HierarchicalStructures/Dispensing/Location/y}"
    yaw="$aas{aauFillingLineAAS/HierarchicalStructures/Dispensing/Location/theta}"
/>

<!-- Dynamic station reference using local blackboard value -->
<MoveToPosition 
    Asset="{Xbot}"
    x="$aas{{Station}/HierarchicalStructures/Location/x}"
    y="$aas{{Station}/HierarchicalStructures/Location/y}"
    yaw="$aas{{Station}/HierarchicalStructures/Location/theta}"
/>
```

**Path Format**: `AAS_ID_Short/SubmodelIdShort/SMC.../PropertyIdShort`

### Syntax Option 2: Protocol-Style Prefix
```xml
<MoveToPosition 
    x="aas://aauFillingLineAAS/HierarchicalStructures/Dispensing/Location/x"
/>
```

### Syntax Option 3: JSON-Path Style
```xml
<MoveToPosition 
    x="$aas{$.shells['aauFillingLineAAS'].submodels['HierarchicalStructures'].Dispensing.Location.x}"
/>
```

**Recommendation**: Option 1 is clearest and aligns with AAS ReferenceElement conventions.

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BehaviorTree Runtime                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────────────┐  │
│  │  XML Parser     │───▶│ Extended Port    │───▶│  getInput<T>()        │  │
│  │  (Extended)     │    │ Value Parser     │    │  (Extended)           │  │
│  └─────────────────┘    └──────────────────┘    └───────────────────────┘  │
│                                │                         │                  │
│                                ▼                         ▼                  │
│                        ┌──────────────────┐    ┌───────────────────────┐   │
│                        │ Detect Reference │    │  AAS Value Resolver   │   │
│                        │    Type          │    │                       │   │
│                        │ - {local}        │    │  - Parse AAS path     │   │
│                        │ - $aas{path}     │    │  - Cache lookup       │   │
│                        │ - literal        │    │  - Fetch from server  │   │
│                        └──────────────────┘    └───────────────────────┘   │
│                                                          │                  │
└──────────────────────────────────────────────────────────│──────────────────┘
                                                           │
                                                           ▼
                                              ┌───────────────────────┐
                                              │    AASBlackboard      │
                                              │  (Caching Proxy)      │
                                              │                       │
                                              │  - get(path) → Any    │
                                              │  - set(path, value)   │
                                              │  - cache management   │
                                              │  - async prefetch     │
                                              └───────────────────────┘
                                                           │
                                                           ▼
                                              ┌───────────────────────┐
                                              │     AAS Server        │
                                              │   (HTTP/REST API)     │
                                              └───────────────────────┘
```

---

## Implementation Plan

### Phase 1: AAS Blackboard Wrapper

Create an `AASBlackboard` class that provides a blackboard-like interface to the AAS:

```cpp
// include/aas/aas_blackboard.h
#pragma once

#include <behaviortree_cpp/blackboard.h>
#include "aas/aas_client.h"
#include <optional>
#include <unordered_map>
#include <mutex>
#include <chrono>

namespace BT {

/**
 * @brief AASBlackboard provides a blackboard-like interface to AAS properties.
 * 
 * It supports:
 *  - Reading properties via path: "AAS_ID/Submodel/SMC/Property"
 *  - Caching with TTL (time-to-live) to reduce network calls
 *  - Nested blackboard variable substitution in paths
 */
class AASBlackboard {
public:
    struct CacheEntry {
        Any value;
        std::chrono::steady_clock::time_point fetch_time;
    };

    AASBlackboard(std::shared_ptr<AASClient> aas_client, 
                  std::chrono::seconds cache_ttl = std::chrono::seconds(60));
    
    /**
     * @brief Get a value from AAS given a path.
     * @param path Format: "AAS_IdShort/SubmodelIdShort/SMC.../PropertyIdShort"
     * @param local_bb Optional local blackboard for variable substitution in path
     * @return The value as Any, or empty if not found
     */
    Expected<Any> get(const std::string& path, 
                      const Blackboard::Ptr& local_bb = nullptr);
    
    /**
     * @brief Set a value in AAS (if writable).
     * @param path The AAS property path
     * @param value The value to set
     */
    Result set(const std::string& path, const Any& value);
    
    /**
     * @brief Invalidate cache for a specific path or all entries.
     */
    void invalidateCache(const std::string& path = "");
    
    /**
     * @brief Prefetch multiple paths asynchronously (for optimization).
     */
    void prefetch(const std::vector<std::string>& paths);

private:
    std::shared_ptr<AASClient> aas_client_;
    std::chrono::seconds cache_ttl_;
    
    std::unordered_map<std::string, CacheEntry> cache_;
    mutable std::mutex cache_mutex_;
    
    // Parse path into components
    struct AASPath {
        std::string aas_id;
        std::string submodel_id;
        std::vector<std::string> property_path;
    };
    
    std::optional<AASPath> parsePath(const std::string& path);
    
    // Substitute {BlackboardVar} in path using local blackboard
    std::string substitutePath(const std::string& path, 
                               const Blackboard::Ptr& local_bb);
};

} // namespace BT
```

### Phase 2: Extended Value Parser

Extend the port value parsing to detect AAS references:

```cpp
// include/bt/aas_port_value.h
#pragma once

#include <behaviortree_cpp/basic_types.h>
#include <string>
#include <variant>

namespace BT {

enum class PortValueType {
    LITERAL,           // Plain value: "42" or "hello"
    BLACKBOARD,        // Local blackboard: "{variable}"
    AAS_REFERENCE,     // AAS property: "$aas{path/to/property}"
    SCRIPT             // Expression: "2 + {x} * $aas{.../y}"
};

struct AASReference {
    std::string path;  // The AAS path, may contain {variables}
};

/**
 * @brief Detect the type of a port value string.
 */
PortValueType detectPortValueType(StringView str);

/**
 * @brief Check if string is an AAS reference.
 * @param str The input string
 * @param stripped_path Output: the path without $aas{} wrapper
 * @return true if it's an AAS reference
 */
bool isAASReference(StringView str, StringView* stripped_path = nullptr);

/**
 * @brief Parse an AAS reference from a string.
 */
std::optional<AASReference> parseAASReference(StringView str);

} // namespace BT
```

Implementation:
```cpp
// src/bt/aas_port_value.cpp
#include "bt/aas_port_value.h"

namespace BT {

static constexpr StringView AAS_PREFIX = "$aas{";
static constexpr char AAS_SUFFIX = '}';

bool isAASReference(StringView str, StringView* stripped_path)
{
    // Trim whitespace
    size_t start = 0, end = str.size();
    while (start < end && str[start] == ' ') start++;
    while (end > start && str[end-1] == ' ') end--;
    
    auto trimmed = str.substr(start, end - start);
    
    if (trimmed.size() < AAS_PREFIX.size() + 2) {
        return false;
    }
    
    if (trimmed.substr(0, AAS_PREFIX.size()) == AAS_PREFIX && 
        trimmed.back() == AAS_SUFFIX) 
    {
        if (stripped_path) {
            *stripped_path = trimmed.substr(
                AAS_PREFIX.size(), 
                trimmed.size() - AAS_PREFIX.size() - 1
            );
        }
        return true;
    }
    return false;
}

PortValueType detectPortValueType(StringView str)
{
    if (isAASReference(str)) {
        return PortValueType::AAS_REFERENCE;
    }
    if (TreeNode::isBlackboardPointer(str)) {
        return PortValueType::BLACKBOARD;
    }
    // Check for mixed expressions containing $aas or {}
    if (str.find("$aas{") != StringView::npos || 
        str.find('{') != StringView::npos) 
    {
        return PortValueType::SCRIPT;
    }
    return PortValueType::LITERAL;
}

std::optional<AASReference> parseAASReference(StringView str)
{
    StringView path;
    if (isAASReference(str, &path)) {
        return AASReference{std::string(path)};
    }
    return std::nullopt;
}

} // namespace BT
```

### Phase 3: Extended Tree Node getInput

We need to extend `getInput<T>` to handle AAS references. There are two approaches:

#### Approach A: Fork BehaviorTree.CPP (More Invasive)

Modify `TreeNode::getInputStamped` to check for AAS references:

```cpp
// In tree_node.h, extend getInputStamped
template <typename T>
inline Expected<Timestamp> TreeNode::getInputStamped(const std::string& key,
                                                     T& destination) const
{
    // ... existing code to get port_value_str ...
    
    // NEW: Check for AAS reference
    StringView aas_path;
    if (isAASReference(port_value_str, &aas_path))
    {
        // Substitute any {blackboard} variables in the path
        std::string resolved_path = substituteBlackboardVars(
            std::string(aas_path), config().blackboard);
        
        // Fetch from AAS blackboard
        if (auto aas_bb = config().aas_blackboard)
        {
            auto result = aas_bb->get(resolved_path, config().blackboard);
            if (result)
            {
                destination = result.value().cast<T>();
                return Timestamp{};
            }
            return nonstd::make_unexpected(
                StrCat("Failed to fetch AAS property: ", resolved_path));
        }
        return nonstd::make_unexpected("AAS Blackboard not configured");
    }
    
    // ... existing blackboard/literal handling ...
}
```

#### Approach B: Wrapper Helper (Less Invasive - Recommended Initially)

Create helper functions that nodes can use without modifying BT.CPP:

```cpp
// include/bt/aas_input_helper.h
#pragma once

#include <behaviortree_cpp/tree_node.h>
#include "aas/aas_blackboard.h"

namespace BT {

/**
 * @brief Extended getInput that supports AAS references.
 * 
 * Usage in node:
 *   float x;
 *   if (auto res = getInputAAS<float>("x", x, aas_blackboard_); !res) {
 *       return BT::NodeStatus::FAILURE;
 *   }
 */
template <typename T>
Result getInputAAS(const TreeNode* node,
                   const std::string& key,
                   T& destination,
                   AASBlackboard::Ptr aas_bb)
{
    // First try normal getInput
    std::string port_value;
    auto remap_it = node->config().input_ports.find(key);
    if (remap_it != node->config().input_ports.end()) {
        port_value = remap_it->second;
    } else {
        // Fall back to default from manifest
        // ... handle default value ...
    }
    
    // Check if it's an AAS reference
    StringView aas_path;
    if (isAASReference(port_value, &aas_path)) {
        if (!aas_bb) {
            return nonstd::make_unexpected("AAS Blackboard not configured");
        }
        
        // Resolve any {blackboard} variables in path
        std::string resolved = substituteBlackboardVarsInPath(
            std::string(aas_path), node->config().blackboard);
        
        auto result = aas_bb->get(resolved, node->config().blackboard);
        if (!result) {
            return nonstd::make_unexpected(result.error());
        }
        
        try {
            destination = result.value().template cast<T>();
            return {};
        } catch (const std::exception& e) {
            return nonstd::make_unexpected(
                StrCat("Type conversion failed for AAS value: ", e.what()));
        }
    }
    
    // Not AAS reference, use standard getInput
    return node->getInput(key, destination);
}

/**
 * @brief Substitutes {variable} references in an AAS path with blackboard values.
 */
std::string substituteBlackboardVarsInPath(
    const std::string& path,
    const Blackboard::Ptr& blackboard);

} // namespace BT
```

### Phase 4: Script Parser Extension (For Arithmetic)

To support arithmetic expressions with AAS values, extend the scripting system:

```cpp
// New AST node type for AAS variable access
struct ExprAASName : ExprBase
{
    std::string path;
    
    explicit ExprAASName(std::string p) : path(std::move(p)) {}
    
    Any evaluate(Environment& env) const override
    {
        // env needs access to AASBlackboard
        if (auto aas_bb = env.aas_blackboard) {
            auto result = aas_bb->get(path, env.vars);
            if (result) {
                return result.value();
            }
            throw RuntimeError(StrCat("Failed to fetch AAS property: ", path));
        }
        throw RuntimeError("AAS Blackboard not available in scripting environment");
    }
};
```

Extend the grammar to recognize `$aas{...}`:

```cpp
// In operators.hpp, add to Grammar namespace
struct AASReference : lexy::token_production
{
    static constexpr auto rule = 
        LEXY_LIT("$aas{") >> 
        dsl::identifier(dsl::ascii::alpha, 
                        dsl::ascii::alnum / dsl::lit_c<'/'> / dsl::lit_c<'_'>) >>
        dsl::lit_c<'}'>;
    
    static constexpr auto value = 
        lexy::as_string<std::string> |
        lexy::callback<Ast::expr_ptr>([](std::string&& path) {
            return std::make_shared<Ast::ExprAASName>(std::move(path));
        });
};
```

---

## Usage Examples

### Example 1: Simple Property Reference
```xml
<MoveToPosition 
    name="MoveToDenseCell"
    Asset="{Xbot}"
    x="$aas{FillingLine/HierarchicalStructures/DenseCell/Location/x}"
    y="$aas{FillingLine/HierarchicalStructures/DenseCell/Location/y}"
    yaw="$aas{FillingLine/HierarchicalStructures/DenseCell/Location/theta}"
/>
```

### Example 2: Dynamic Station from Blackboard
```xml
<!-- Station is set earlier in the tree to an AAS ID like "imaDispensingSystemAAS" -->
<Script code="CurrentStation := 'imaDispensingSystemAAS'" />

<MoveToPosition 
    name="MoveToCurrentStation"
    Asset="{Xbot}"
    x="$aas{FillingLine/HierarchicalStructures/{CurrentStation}/Location/x}"
    y="$aas{FillingLine/HierarchicalStructures/{CurrentStation}/Location/y}"
    yaw="$aas{FillingLine/HierarchicalStructures/{CurrentStation}/Location/theta}"
/>
```

### Example 3: Arithmetic with AAS Values
```xml
<!-- Calculate offset position: base + offset -->
<Script code="
    target_x := $aas{FillingLine/.../x} + {offset_x};
    target_y := $aas{FillingLine/.../y} + {offset_y}
" />

<!-- Or directly in port (if script-enabled ports) -->
<MoveToPosition 
    x="$aas{.../x} + 0.1"
    y="$aas{.../y} - 0.05"
    yaw="$aas{.../theta}"
/>
```

### Example 4: Conditional Based on AAS Value
```xml
<Precondition if="$aas{Station/Capabilities/isAvailable} == true" else="FAILURE">
    <MoveToPosition ... />
</Precondition>
```

---

## MoveToPosition Node Refactored

With the new system, the `MoveToPosition` node becomes much simpler:

```cpp
// move_to_position.h (simplified)
class MoveToPosition : public MqttActionNode
{
public:
    static BT::PortsList providedPorts()
    {
        return {
            BT::InputPort<std::string>("Asset", "{Xbot}", "Robot asset ID"),
            BT::InputPort<double>("x", "Target X position (literal or AAS ref)"),
            BT::InputPort<double>("y", "Target Y position (literal or AAS ref)"),  
            BT::InputPort<double>("yaw", "Target yaw angle (literal or AAS ref)"),
            BT::InputPort<std::string>("Uuid", "{ProductID}", "Command UUID"),
        };
    }
    
    nlohmann::json createMessage() override
    {
        double x, y, yaw;
        std::string uuid;
        
        // These will automatically resolve $aas{} references
        if (auto res = getInputAAS<double>(this, "x", x, aas_blackboard_); !res) {
            std::cerr << "Failed to get x: " << res.error() << std::endl;
            return {};
        }
        if (auto res = getInputAAS<double>(this, "y", y, aas_blackboard_); !res) {
            std::cerr << "Failed to get y: " << res.error() << std::endl;
            return {};
        }
        if (auto res = getInputAAS<double>(this, "yaw", yaw, aas_blackboard_); !res) {
            std::cerr << "Failed to get yaw: " << res.error() << std::endl;
            return {};
        }
        getInput("Uuid", uuid);
        
        nlohmann::json message;
        message["Position"] = {x, y, yaw};
        message["Uuid"] = uuid;
        return message;
    }
};
```

---

## Implementation Phases

### Phase 1: Basic AAS Blackboard (Week 1-2)
- [ ] Implement `AASBlackboard` class
- [ ] Implement `isAASReference()` and path parsing
- [ ] Add `getInputAAS<T>()` helper function
- [ ] Unit tests for path parsing and value retrieval

### Phase 2: Node Integration (Week 2-3)
- [ ] Refactor `MoveToPosition` to use new system
- [ ] Update `MqttActionNode` base class to provide `aas_blackboard_`
- [ ] Create example nodes demonstrating the pattern
- [ ] Integration tests

### Phase 3: Script Parser Extension (Week 3-4)
- [ ] Fork BehaviorTree.CPP (optional, for deep integration)
- [ ] Add `ExprAASName` to AST
- [ ] Extend grammar for `$aas{...}` in expressions
- [ ] Support arithmetic with AAS values
- [ ] Tests for expressions

### Phase 4: Caching & Optimization (Week 4-5)
- [ ] Implement cache with TTL
- [ ] Add prefetch capability
- [ ] Profile and optimize network calls
- [ ] Add cache invalidation triggers

### Phase 5: Write Support (Optional, Week 5-6)
- [ ] Implement `set()` for writable AAS properties
- [ ] Add output port support with `$aas{}` targets
- [ ] Transaction/rollback support

---

## Considerations

### Caching Strategy
- **TTL-based**: Properties are cached for a configurable time (default 60s)
- **Event-based**: Subscribe to AAS change notifications (if available)
- **Manual**: Explicit cache invalidation via tree actions

### Error Handling
- Network failures should be graceful (use cached value if available)
- Property-not-found should return clear error message with full path
- Type conversion errors should be descriptive

### Performance
- Prefetch commonly-used properties during tree initialization
- Batch requests where possible
- Consider async fetching for non-blocking behavior

### Fork vs. Extension
- **Without fork**: Use helper functions, some syntax limitations
- **With fork**: Full integration into `getInput<T>()` and scripting, cleaner syntax

**Recommendation**: Start with helpers (Approach B), fork later if deeper integration needed.

---

## Alternative Approaches Considered

### 1. Pre-populate Blackboard
Fetch all needed AAS values before tree execution and put them in the local blackboard.
- **Pro**: No BT library changes needed
- **Con**: Stale data, can't update during execution, must know all needed values upfront

### 2. Custom Port Types
Create a custom `AASPort<T>` type that wraps the reference.
- **Pro**: Type-safe, explicit
- **Con**: Requires changes to how ports are defined, breaks standard patterns

### 3. Decorator Node for AAS Fetch
Use a decorator that fetches AAS values into blackboard before child executes.
- **Pro**: Explicit, no library changes
- **Con**: Verbose XML, extra nodes everywhere

**Chosen Approach**: Extended syntax (`$aas{}`) is most ergonomic and aligns with blackboard pattern.

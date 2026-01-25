# BehaviorTree.CPP Fork: AAS Scripting Extension

This document describes the changes needed to fork BehaviorTree.CPP to add native
support for `$aas{...}` references in the scripting language and expressions.

## Overview

The goal is to extend the scripting parser to:
1. Recognize `$aas{path/to/property}` as a valid expression element
2. Resolve AAS values at runtime during expression evaluation
3. Allow arithmetic operations mixing AAS values with other values

Example expressions that should work:
```
target_x := $aas{Line/Structure/Station/x} + {offset_x}
adjusted_yaw := $aas{Line/Structure/Station/theta} * 0.5
valid := $aas{Station/Capabilities/available} == true
```

## Files to Modify

### 1. Environment Extension (`scripting/script_parser.hpp`)

Add AAS blackboard to the scripting environment:

```cpp
// scripting/script_parser.hpp
namespace BT::Ast
{

class AASBlackboard;  // Forward declaration

struct Environment
{
  BT::Blackboard::Ptr vars;
  EnumsTablePtr enums;
  
  // NEW: AAS blackboard for resolving $aas{} references
  std::shared_ptr<AASBlackboard> aas_blackboard;
};

}  // namespace Ast
```

### 2. New AST Node (`scripting/operators.hpp`)

Add a new expression node type for AAS references:

```cpp
// In BT::Ast namespace

/**
 * @brief AST node for AAS property references: $aas{path}
 * 
 * The path may contain {blackboard_var} substitutions that are resolved
 * at evaluation time.
 */
struct ExprAASReference : ExprBase
{
    std::string raw_path;  // May contain {var} placeholders
    
    explicit ExprAASReference(std::string path) : raw_path(std::move(path)) {}
    
    Any evaluate(Environment& env) const override
    {
        if (!env.aas_blackboard)
        {
            throw RuntimeError("AAS Blackboard not available in scripting environment");
        }
        
        // Substitute any {blackboard_var} in the path
        std::string resolved_path = substitutePath(raw_path, env.vars);
        
        auto result = env.aas_blackboard->get(resolved_path, env.vars);
        if (!result)
        {
            throw RuntimeError(StrCat("Failed to fetch AAS property [", 
                                      resolved_path, "]: ", result.error()));
        }
        return result.value();
    }
    
private:
    static std::string substitutePath(const std::string& path, 
                                      const Blackboard::Ptr& bb)
    {
        // Same logic as AASBlackboard::substitutePath
        if (!bb) return path;
        
        std::string result = path;
        std::regex var_pattern(R"(\{([^}]+)\})");
        std::smatch match;
        
        while (std::regex_search(result, match, var_pattern))
        {
            std::string var_name = match[1].str();
            auto any_ref = bb->getAnyLocked(var_name);
            if (any_ref)
            {
                std::string value = any_ref.get()->cast<std::string>();
                result = match.prefix().str() + value + match.suffix().str();
            }
            else
            {
                // Variable not found, leave placeholder (will cause AAS lookup to fail)
                break;
            }
        }
        return result;
    }
};
```

### 3. Grammar Extension (`scripting/any_types.hpp`)

Add a grammar rule for parsing `$aas{...}`:

```cpp
// In BT::Grammar namespace

/**
 * @brief Grammar for AAS reference: $aas{path/with/slashes}
 * 
 * Path characters allowed: alphanumeric, underscore, slash, curly braces (for {var})
 */
struct AASPath : lexy::token_production
{
    // Characters allowed in AAS path
    struct path_char
    {
        static constexpr auto rule = 
            dsl::ascii::alnum / 
            dsl::lit_c<'_'> / 
            dsl::lit_c<'/'> / 
            dsl::lit_c<'{'> /
            dsl::lit_c<'}'>;
    };
    
    static constexpr auto rule = [] {
        auto path_content = dsl::while_one(path_char::rule);
        return path_content;
    }();
    
    static constexpr auto value = lexy::as_string<std::string>;
};

struct AASReference : lexy::token_production
{
    static constexpr auto rule = 
        LEXY_LIT("$aas{") >> dsl::p<AASPath> >> dsl::lit_c<'}'>;
    
    static constexpr auto value = 
        lexy::callback<Ast::expr_ptr>([](std::string&& path) {
            return std::make_shared<Ast::ExprAASReference>(std::move(path));
        });
};
```

### 4. Expression Grammar Update (`scripting/operators.hpp`)

Add AAS reference to the expression atom rule:

```cpp
// In Expression struct, update the atom rule:

struct Expression : lexy::expression_production
{
    // ... existing code ...
    
    static constexpr auto atom = [] {
        auto paren_expr = dsl::parenthesized(dsl::p<nested_expr>);
        auto boolean = dsl::p<BooleanLiteral>;
        auto var = dsl::p<Name>;
        auto string = dsl::p<StringLiteral>;
        
        // NEW: AAS reference
        auto aas_ref = dsl::p<AASReference>;
        
        auto literal =
            dsl::p<Real> | dsl::p<Integer> | dsl::peek(dsl::lit_c<'\''> / dsl::lit_c<'"'>) >>
            string;
        
        // Add aas_ref to the alternatives
        return paren_expr | aas_ref | boolean | literal | var;
    }();
    
    // ... rest unchanged ...
};
```

### 5. Factory Configuration (`bt_factory.h`)

Add method to set AAS blackboard for scripting:

```cpp
class BehaviorTreeFactory
{
public:
    // ... existing code ...
    
    /**
     * @brief Set the AAS Blackboard for script evaluation.
     * 
     * When set, scripts can use $aas{path} syntax to reference AAS properties.
     */
    void setAASBlackboard(std::shared_ptr<AASBlackboard> aas_bb);
    
private:
    std::shared_ptr<AASBlackboard> aas_blackboard_;
};
```

### 6. Script Execution Update

Ensure the environment is populated with AAS blackboard:

```cpp
// In tree execution, when building the scripting environment:

Ast::Environment buildScriptEnvironment(const Blackboard::Ptr& bb,
                                        const ScriptingEnumsRegistry& enums,
                                        std::shared_ptr<AASBlackboard> aas_bb)
{
    Ast::Environment env;
    env.vars = bb;
    env.enums = std::make_shared<EnumsTable>(enums);
    env.aas_blackboard = aas_bb;  // NEW
    return env;
}
```

## Usage Examples

### Example 1: Simple Assignment from AAS
```xml
<Script code="station_x := $aas{FillingLine/Structure/Dispensing/x}" />
```

### Example 2: Arithmetic with AAS
```xml
<Script code="
    base_x := $aas{FillingLine/Structure/{CurrentStation}/Location/x};
    target_x := base_x + {offset_x}
" />
```

### Example 3: Conditions with AAS
```xml
<Precondition if="$aas{Station/Status/available} == true" else="FAILURE">
    <DoSomething />
</Precondition>
```

### Example 4: Complex Expression
```xml
<Script code="
    distance := sqrt(
        ($aas{Station/x} - {robot_x}) * ($aas{Station/x} - {robot_x}) +
        ($aas{Station/y} - {robot_y}) * ($aas{Station/y} - {robot_y})
    )
" />
```

## Build Integration

The fork would be maintained as a submodule with additional source files:

```
BT_Controller/
├── third_party/
│   └── BehaviorTree.CPP/          # Fork with modifications
│       ├── include/behaviortree_cpp/
│       │   ├── scripting/
│       │   │   ├── script_parser.hpp    # Modified: Environment with AAS
│       │   │   ├── operators.hpp        # Modified: ExprAASReference + grammar
│       │   │   └── any_types.hpp        # Modified: AASPath grammar
│       │   └── bt_factory.h             # Modified: setAASBlackboard
│       └── src/
│           └── bt_factory.cpp           # Modified: AAS BB handling
```

## Alternative: No-Fork Plugin Approach

If forking is undesirable, an alternative is to:

1. Use pre/post script hooks
2. Implement a custom "FetchAAS" action node that populates blackboard
3. Use decorator pattern to fetch AAS values before node execution

Example without fork:
```xml
<!-- Pre-fetch pattern -->
<Sequence>
    <FetchAAS 
        path="FillingLine/Structure/{Station}/Location/x" 
        output="{station_x}" />
    <FetchAAS 
        path="FillingLine/Structure/{Station}/Location/y" 
        output="{station_y}" />
    <MoveToPosition x="{station_x}" y="{station_y}" />
</Sequence>
```

This is more verbose but doesn't require modifying BT.CPP.

## Recommendation

Start with the **helper function approach** (already implemented in `aas_input_helper.h`)
for immediate use. Consider forking BT.CPP only if:

1. You need AAS values in `Script` nodes and preconditions
2. You want cleaner XML without explicit fetch nodes
3. You're willing to maintain a fork

The helper approach covers 90% of use cases (action node inputs) without any
library modifications.

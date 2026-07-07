# AAS-Centric Architecture Plan — v3 (June 2026)

**TL;DR** — Protocol backends implement standardized `IActionBackend`/`IConditionBackend` interfaces. BT nodes contain zero protocol code. KG auto-derives predicates, controller queries via SPARQL pull. SymbolicState migrates to KG.

## Status

| Phase | Status |
|-------|--------|
| A — BT_Controller refactor | ✅ Complete |
| B — Predicate Reasoner (kg-bridge) | ⬜ Not started |
| C — Ontology: Protocol Bindings | ⬜ Not started |
| D — Planner Integration + KG migration | ⬜ Not started |
| E — DataBridge + Migration | ⬜ Not started |

---

## Architecture

```
BT_Controller/
├── include/
│   ├── backends/                           ← Protocol infrastructure
│   │   ├── action_backend.h                ← IActionBackend + ActionContext
│   │   ├── condition_backend.h             ← IConditionBackend
│   │   ├── backend_registry.h/.cpp         ← Unified lazy registry
│   │   ├── backend_factory.h/.cpp          ← InterfaceMode enum
│   │   ├── aas/                            ← AAS protocol (all of it)
│   │   │   ├── aas_bridge.h                ← IAASBridge interface
│   │   │   ├── aas_client.h/.cpp           ← BaSyx REST client
│   │   │   ├── basyx_rest_bridge.h/.cpp    ← IAASBridge → BaSyx impl
│   │   │   ├── binding_resolver.h/.cpp     ← Parameter resolution
│   │   │   ├── transformation_resolver.h/.cpp
│   │   │   ├── aas_interface_cache.h/.cpp
│   │   │   ├── aas_snapshot.h/.cpp
│   │   │   ├── action_backend.h/.cpp       ← AasActionBackend
│   │   │   └── condition_backend.h/.cpp    ← AasConditionBackend
│   │   ├── mqtt/                           ← MQTT protocol (all of it)
│   │   │   ├── mqtt_client.h/.cpp          ← IMqttClient + PahoMqttClient
│   │   │   ├── mqtt_sub_base.h/.cpp
│   │   │   ├── mqtt_pub_base.h/.cpp
│   │   │   ├── node_message_distributor.h/.cpp
│   │   │   ├── action_backend.h/.cpp       ← MqttActionBackend
│   │   │   └── condition_backend.h/.cpp    ← MqttConditionBackend
│   │   ├── kg/                             ← Knowledge Graph
│   │   │   ├── kg_query_client.h/.cpp      ← IKGQueryClient + FusekiQueryClient
│   │   │   └── condition_backend.h/.cpp    ← KgConditionBackend
│   │   └── symbolic/                       ← In-process state (→ KG Phase D)
│   │       └── condition_backend.h/.cpp    ← SymbolicConditionBackend
│   │
│   └── bt/                                 ← Behavior tree nodes
│       ├── actions/execute_action_node.*   ← Pure backend-driven
│       ├── conditions/fluent_check_node.*  ← Pure backend-driven
│       └── register_all_nodes.h            ← No backend wiring
```

**External dependencies:**

```
BT_Controller ──→ BaSyx AAS (REST)       via IAASBridge
              ──→ MQTT Broker (Paho)      via IMqttClient
              ──→ Fuseki KG (SPARQL)      via IKGQueryClient
              ──→ Registration_Service    for invocationDelegation
```

---

## Phase A — BT_Controller Refactor ✅

Backends implement standardized interfaces. BT nodes delegate entirely. Protocol code consolidated under `backends/`.

**Key decisions:**
- `IActionBackend` — `onStart(ctx)`, `onRunning()`, `onHalted()`, `responseData()`
- `IConditionBackend` — `evaluate(predicate, args)` → `std::optional<bool>`
- `BackendRegistry` — single source, lazy creation, shared instances
- `InterfaceMode` — `Standard` (AAS) / `Native` (AID submodel), set via `BT_INTERFACE_MODE` env var
- `FluentCheck` priority chain: symbolic → KG → protocol (AAS or MQTT)
- No static singletons in BT nodes — all backends from registry

---

## Phase B — Predicate Reasoner + Projection (kg-bridge)

**Depends on:** Phase A ✅

1. Submodel-type filter in `projection.py` — only project Variables, Parameters, HierarchicalStructures, Nameplate. Skip AIPlanning, Skills, Capabilities, AID.
2. `PredicateReasoner` class — Kafka consumer, runs SPARQL materialization rules on AAS change events.
3. SPARQL rules in `sparql/predicates/`:
   - `operational.rq` — PackMLState → boolean
   - `occupied.rq` — ProcessQueue → boolean
   - `in-range.rq` — euclidean distance → boolean
   - `resource-at.rq` — location label match → boolean
   - `product-at.rq` — location label match → boolean
4. Dependency index — maps AAS semanticIds → affected rules.
5. Facts INSERTed/DELETEd directly in Fuseki. **No MQTT publishing from KG.**
6. Align predicate RDF shape with `KgConditionBackend::askPredicate()` SPARQL query.

**Files:**
| Action | File |
|--------|------|
| New | `kg-bridge/runtime/predicate_reasoner.py` |
| New | `kg-bridge/sparql/predicates/{operational,occupied,in-range,resource-at,product-at}.rq` |
| Mod | `kg-bridge/conversion/projection.py` |
| Mod | `kg-bridge/main.py` |

---

## Phase C — Ontology: Protocol Bindings (kg-bridge + APEX)

**Depends on:** Phase A ✅, Phase B

1. `apex-protocol-binding.ttl` — SkillParameter, ValueSource, Transformation, ProtocolFieldBinding.
2. `apex:VariableDecomposition` for MQTT↔AAS field mappings.
3. Binding template instances (ABOX) for current skills (MoveToPosition, Occupy, etc.).
4. SHACL shapes for validation.
5. `BindingResolver` reads ontology templates instead of JSONata expressions.
6. Transparent switch for `AasActionBackend` — already uses `BindingResolver`.

**Files:**
| Action | File |
|--------|------|
| New | `kg-bridge/Ontology/APEX/apex-protocol-binding.ttl` |
| New | `kg-bridge/Ontology/APEX/extensions/apex-protocol-binding-instances.ttl` |
| Mod | `BT_Controller/src/backends/aas/binding_resolver.cpp` |

---

## Phase D — Planner Integration + SymbolicState → KG

**Depends on:** Phase A ✅, Phase B, Phase C

1. Add `insertFact()` / `deleteFact()` to `IKGQueryClient` + `FusekiQueryClient`.
2. `ExecuteAction::applySymbolicEffects()` dual-writes to KG + SymbolicState.
3. `FluentCheck` removes `tickSymbolic()` — all predicates through backend chain.
4. Remove `SymbolicConditionBackend`.
5. Remove `SymbolicState`.
6. Plots `execution_refs.py` emits binding template refs instead of JSONata transformations.
7. BT XML `action_ref` carries binding template reference + grounded args.

**Files:**
| Action | File |
|--------|------|
| Mod | `BT_Controller/include/backends/kg/kg_query_client.h` |
| Mod | `BT_Controller/src/backends/kg/kg_query_client.cpp` |
| Mod | `BT_Controller/src/bt/actions/execute_action_node.cpp` |
| Mod | `BT_Controller/src/bt/conditions/fluent_check_node.cpp` |
| Del | `BT_Controller/include/backends/symbolic/` |
| Del | `BT_Controller/src/backends/symbolic/` |
| Del | `BT_Controller/include/bt/symbolic_state.h` |
| Del | `BT_Controller/src/bt/symbolic_state.cpp` |
| Mod | `Plots/step4_policy_to_bt/execution_refs.py` |

---

## Phase E — DataBridge + Migration

**Depends on:** Phase A ✅, Phase C

1. Throttle DataBridge MQTT→AAS to configurable rate (default 10Hz).
2. Variable decomposition mappings from ontology → DataBridge config.
3. JSONata deprecation — existing configs work, new skills use ontology bindings.
4. Remove `Transformation` property from Registration_Service AIPlanning builder for new configs.

**Files:**
| Action | File |
|--------|------|
| Mod | `Registration_Service/src/aas_generation/ai_planning_builder.py` |
| Mod | DataBridge configs |

---

## Verification

1. **Unit**: `BackendRegistry::getActionBackend()` returns correct backend for given mode
2. **Unit**: `BackendRegistry::getConditionBackend()` returns backends by key
3. **Unit**: `ExecuteAction::onStart()` delegates to AAS and MQTT backends
4. **Unit**: `FluentCheck::tick()` returns SUCCESS/FAILURE from each backend in priority order
5. **Integration**: AAS Variable change → kg-bridge rule fires → KG updated → controller SPARQL → FluentCheck returns status
6. **Integration**: Plots reads KG initial state → plans → BT executes → AAS Operation invoked
7. **Regression**: Existing BT XMLs with JSONata transformations work via MQTT backend fallback
8. **Mode switch**: `BT_INTERFACE_MODE=Standard` → AAS path; `Native` → MQTT from AID submodel

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| v1 | — | Initial: MQTT PredicateCache, push from KG |
| v2 | Jun 26 | SPARQL pull (KGQueryClient), no MQTT from KG |
| v3 | Jun 30 | Protocol-first backends, IActionBackend/IConditionBackend, BackendRegistry, FluentCheck refactored, SymbolicState→KG migration path |

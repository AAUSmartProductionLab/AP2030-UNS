## Plan: Transformation-Driven Executable BT Pipeline (v3)

Build an end-to-end execution contract where planner-generated BT nodes carry AAS paths and parameter bindings, BT runtime nodes fetch transformation logic at construction time, prefer direct interface communication, and fall back to direct AAS operation invocation when interface metadata is missing. Symbolic planning state (step ordering, plan-internal flags) lives in an in-process `SymbolicState` store inside `BT_Controller`; the AAS remains a digital twin of physical assets and serves only sensor-backed predicates via Transformations.

PR1 is complete and the planner-side XML contract is frozen. PR2 and PR3 are complete. Active scope for this revision: PR4 in detail; PR5–PR7 in outline.

**Steps**

PR1 - DONE (frozen, do not modify)
1. ExecuteAction and FluentCheck XML emission with `action_ref`/`action_args` and `predicate_ref`/`predicate_args`.
2. Quoted semicolon-delimited args (e.g. `"{Param_a};{Param_b}"`) to satisfy BT.CPP generic-port constraints.
3. Payload and parameter-link aliases declared as MainTree SubTree input_port defaults in TreeNodesModel; no setup-tree SetBlackboard.
4. `transformation_aas_path` captured per action and per fluent in parsing, propagated through merge -> up_builder -> `planner_metadata.action_refs` / `predicate_refs` / `object_refs` (with `_ci` lowercase variants).
5. Tests `test_bt_synthesis_hoisting.py` and `test_pipeline_facade.py` lock the contract in.

PR2 - DONE (Runtime contract alignment and transformation fetch)
6. Phase 2.A Dependencies + AAS client extensions: `rayokota/jsonata-cpp` v0.1.2 vendored under `BT_Controller/third_party/jsonata-cpp/` and linked PUBLIC into `bt_controller_common`. `AASClient` gained `fetchSubmodelElementByPath` and `invokeOperation`. `TransformationResolver` caches `(aas_id, transformation_aas_path) -> JSONata expression`.
7. Phase 2.B Shared parsing: `BT_Controller/include/bt/execution_refs.h` + `src/bt/execution_refs.cpp` provide `ActionRef`, `PredicateRef`, `parseActionRef`, `parsePredicateRef`, `parseArgsList` (10 unit tests, behind `BT_CONTROLLER_BUILD_TESTS=ON`).
8. Phase 2.C Runtime nodes: `ExecuteAction` (derives `MqttActionNode`) and `FluentCheck` (derives `MqttSyncConditionNode`) registered alongside legacy nodes; legacy registrations untouched. Both detect cached interface, then live `fetchInterface`, then AAS-direct fallback gated by env flag.
9. Phase 2.D Diagnostics: parse / fetch / JSONata-compile failures emit a single line and return `FAILURE` rather than throw. JSONata expressions cached on the node instance after first successful compile.

PR3 - DONE (Direct execution + predicate evaluation engine + path normalization)
10. `ExecuteAction::createMessage()` evaluates the cached JSONata transformation against `{ args: [...], object_refs: { name: { aas_id, aas_path } }, now: <iso8601> }`; merges with `{"Uuid": <uuid>}`. Scalar results wrapped as `{"value": scalar}`.
11. Response handling reuses `MqttActionNode` lifecycle; reverse JSONata transformation deferred (revisit in PR5 if needed).
12. `FluentCheck::tick()` evaluates the JSONata transformation against latest received message (or polled property on AAS-direct fallback). Result must be boolean or `{"value": <bool>}`. Symbolic-only predicates (empty `transformation_aas_path`) emit a one-shot warning and return `FAILURE`; PR4 replaces this short-circuit with a `SymbolicState` lookup.
13. `AASClient::resolveSkillReference(asset_id, action_aas_path)` walks the AIPlanning Action SMC, locates its `SkillReference` ReferenceElement, returns `("Skills", "<skill>/<skill>")`. `ExecuteAction::onStart` resolves before `invokeOperation`; falls back to `Skills/<remainder>` verbatim.
14. Env flag `BT_CONTROLLER_AAS_DIRECT=auto|force|disable` controls fallback path during debugging.
15. `bt_log` facade (`include/bt/bt_log.h` + `src/bt/bt_log.cpp`) with `BT_LOG_DEBUG` / `BT_LOG_INFO` / `BT_LOG_WARN` / `BT_LOG_ERROR` macros gated by `BT_CONTROLLER_LOG_LEVEL` (default `info`); `ExecuteAction` and `FluentCheck` route their previous `std::cerr` lines through it.
16. `splitSubmodelPath(slash_path) -> (submodel_id_short, remainder)` canonicalizes the planner's `AI-Planning/...` segment to the actual idShort `AIPlanning` and recognizes `Skills`, `Capabilities`, `Variables`, `AssetInterfacesDescription`, `ProcessInformation`, `RequiredCapabilities`, `HierarchicalStructures`. Used by `TransformationResolver` (with fallback candidate list) and `FluentCheck` AAS-direct fallback. 6 new tests in `test_execution_refs.cpp` (16/16 pass).

PR4 - Split world model: SymbolicState in runtime, sensor predicates in AAS (ACTIVE)

Two predicate populations are separated cleanly:
- **Sensor-backed** (`ProductAt`, `Free`, `Operational`, ...): evaluated via Transformations against live MQTT data on the asset's AAS. Read-only at runtime; PR3 already covers this path.
- **Symbolic / control** (`step_done`, `step_ready`, plan-internal flags): live in a per-BT-tree in-memory `SymbolicState` store inside `BT_Controller`. Seeded from `planner_metadata.initial_state`, mutated by `ExecuteAction` effects on SUCCESS, looked up by `FluentCheck` when no transformation is present.

The AAS is **not** used as a planning world model. No `value_aas_path`, no PATCH, no Process-AAS Variables submodel for grounded planning atoms, no Registration_Service changes. The AAS retains its role as digital twin of assets and capabilities. A future PR may revisit migration to a queryable knowledge store (e.g. RDF over `ppr-ontology/`) once runtime replanning, cross-asset queries, or persistence become real requirements; not in scope here.

Evaluation rule (`FluentCheck::tick()`):
- If `transformation_aas_path` non-empty -> AAS + JSONata path (unchanged from PR3).
- Else -> `SymbolicState.get(predicate, args)`. Missing key -> `false` for boolean predicates / `FAILURE` for non-boolean lookups.

Effect application rule (`ExecuteAction`, on operation SUCCESS):
- For each grounded effect atom on `action_ref_->effects`:
  - Predicate has `transformation_aas_path` -> ignore (trust the next sensor tick).
  - Else -> `SymbolicState.set(predicate, args, value)` or `erase` per PDDL effect literal.

Phase 4.A - Planner metadata surface
17. Tag predicates as symbolic vs sensor-backed in `Planner/aas_to_pddl_conversion/parsing.py` based on presence of `transformation_aas_path`.
18. Extend `planner_metadata` schema with:
    - `initial_state: [{predicate, args:[...], value}]` for symbolic predicates only.
    - Per `ActionRef`: `effects: [{predicate, args:[...], value}]` for symbolic predicates only.
19. Serialize the new fields from `Planner/bt_synthesis/execution_refs.py` and `Planner/bt_synthesis/xml_writer.py`. Verify against `Planner/aas_to_pddl_conversion/bop_ordering.py` output - `step_ready`/`step_done` fall naturally into the symbolic bucket (no `transformation_aas_path`).
20. `Planner/process_aas_generation_publishing/process_aas_generator.py` is **not** modified for grounded atoms.

Phase 4.B - SymbolicState store in BT_Controller
21. New `BT_Controller/include/bt/symbolic_state.h` + `src/bt/symbolic_state.cpp`:
    - `void seed(const std::vector<GroundedAtom>&)`.
    - `std::optional<nlohmann::json> get(std::string predicate, std::vector<std::string> args) const`.
    - `void set(std::string predicate, std::vector<std::string> args, nlohmann::json value)`.
    - `void erase(std::string predicate, std::vector<std::string> args)`.
    - Canonical key: `predicate(arg1,arg2,...)` with deterministic argument order.
22. Owner / lifetime: instantiated alongside the BT factory in `BT_Controller/src/main.cpp` (or wherever the tree is built); shared pointer injected into `ExecuteAction` and `FluentCheck` mirroring how `AASClient` is shared today.

Phase 4.C - Execution-refs additions
23. Extend `ExecutionRefs` (`BT_Controller/include/bt/execution_refs.h` + `src/bt/execution_refs.cpp`):
    - New `struct GroundedAtom { std::string predicate; std::vector<std::string> args; nlohmann::json value; };`.
    - `ActionRef` gains `std::vector<GroundedAtom> effects;`.
    - Add tolerant parsers for `effects` (per-action) and a top-level `initial_state` list. Absence is allowed (back-compat with PR3 trees).

Phase 4.D - FluentCheck + ExecuteAction wiring
24. `BT_Controller/include/bt/conditions/fluent_check_node.{h,cpp}`: drop the PR3 symbolic-only short-circuit; route empty-`transformation_aas_path` ticks through `SymbolicState.get`. One-shot warning is removed.
25. `BT_Controller/include/bt/actions/execute_action_node.{h,cpp}`: add `applySymbolicEffects()` invoked on operation SUCCESS; iterates `action_ref_->effects` and applies via `SymbolicState.set`/`erase`. Effects whose predicate is sensor-backed are skipped defensively (planner already excludes them).

Phase 4.E - Tests
26. New `BT_Controller/tests/test_symbolic_state.cpp`: `seed`/`get`/`set`/`erase`, canonical-key determinism, missing-key semantics, JSON value round-trip.
27. Extend `BT_Controller/tests/test_execution_refs.cpp`: parse `initial_state`, parse `ActionRef.effects`, back-compat with metadata lacking these fields.
28. Integration smoke (manual / scripted): dispensing tree with purely symbolic `step_*` progresses through every step; verify via debug logs that `SymbolicState` transitions match the plan.

PR5 - Effect interpretation policy + state update rules (outline)
29. Classify effects in planner metadata as `sensor-backed`, `symbolic-only`, or `hybrid` (currently inferred from presence of `transformation_aas_path`; PR5 makes the classification explicit).
30. Symbolic-only effects: applied to `SymbolicState` immediately on action SUCCESS (already PR4).
31. Sensor-backed effects: validated by a downstream `FluentCheck` or by an active subscription before the BT advances. Default policy: trust next sensor tick (PR4 behaviour).
32. Hybrid effects: optimistically write to `SymbolicState` shadow, then confirm against sensor reading within a configurable timeout window; emit divergence diagnostic on mismatch.

PR6 - Plan-state synchronization + plan update loop (outline)
33. Divergence detection: `BT_Controller` compares expected symbolic transitions to observed `SymbolicState` and sensor evidence.
34. Publish plan-state updates and divergence events on a planner-facing MQTT topic (topic name TBD with planner team before implementation).
35. Replan trigger policy: hard failure on unresolvable divergence; soft continuation on transient sensor mismatch within timeout.
36. Optional: persist `SymbolicState` snapshot on tree shutdown so a restart can resume mid-plan (out of scope unless explicitly needed).

PR7 - End-to-end validation + rollout hardening (outline)
37. Validate duplicate-suffixed action names invoke the correct AAS targets per grounded instance.
38. Validate predicates across both sensor-backed (`Operational`) and symbolic-only (`step_done`) cases.
39. Validate quoted semicolon args + main-tree defaulted link ports end-to-end in both policy and deterministic-plan paths.
40. Run integration with and without Asset Interface Description to confirm direct + fallback paths both work.
41. Extend `Planner/experiments/run_bt_hoisting_equivalence.py` to additionally exercise the C++ runtime path so the strong-cyclic preservation guarantee is checked against real execution, not just the Python simulator.

**Relevant files**

PR4 (active scope):

Planner (write):
- [Planner/aas_to_pddl_conversion/parsing.py](Planner/aas_to_pddl_conversion/parsing.py) - tag symbolic vs sensor-backed predicates.
- [Planner/bt_synthesis/execution_refs.py](Planner/bt_synthesis/execution_refs.py) - serialize `initial_state` + per-action `effects`.
- [Planner/bt_synthesis/xml_writer.py](Planner/bt_synthesis/xml_writer.py) - `planner_metadata` XML schema bump.

Planner (audit only - no changes expected):
- [Planner/aas_to_pddl_conversion/bop_ordering.py](Planner/aas_to_pddl_conversion/bop_ordering.py) - `step_*` generation as-is.
- [Planner/process_aas_generation_publishing/process_aas_generator.py](Planner/process_aas_generation_publishing/process_aas_generator.py) - no changes (no AIPlanning/Init Property injection).

Runtime (write):
- new: `BT_Controller/include/bt/symbolic_state.h`, `BT_Controller/src/bt/symbolic_state.cpp`.
- [BT_Controller/include/bt/execution_refs.h](BT_Controller/include/bt/execution_refs.h), [BT_Controller/src/bt/execution_refs.cpp](BT_Controller/src/bt/execution_refs.cpp).
- [BT_Controller/include/bt/conditions/fluent_check_node.h](BT_Controller/include/bt/conditions/fluent_check_node.h), [BT_Controller/src/bt/conditions/fluent_check_node.cpp](BT_Controller/src/bt/conditions/fluent_check_node.cpp).
- [BT_Controller/include/bt/actions/execute_action_node.h](BT_Controller/include/bt/actions/execute_action_node.h), [BT_Controller/src/bt/actions/execute_action_node.cpp](BT_Controller/src/bt/actions/execute_action_node.cpp).
- [BT_Controller/src/main.cpp](BT_Controller/src/main.cpp) (or BT factory entry point) - construct `SymbolicState` and inject.
- [BT_Controller/CMakeLists.txt](BT_Controller/CMakeLists.txt) - add `src/bt/symbolic_state.cpp` to `bt_controller_common`.

Tests (write):
- new: `BT_Controller/tests/test_symbolic_state.cpp`.
- [BT_Controller/tests/test_execution_refs.cpp](BT_Controller/tests/test_execution_refs.cpp) - extend.

PR2 + PR3 (frozen, reference only):
- [BT_Controller/include/aas/aas_client.h](BT_Controller/include/aas/aas_client.h), [BT_Controller/src/aas/aas_client.cpp](BT_Controller/src/aas/aas_client.cpp).
- [BT_Controller/include/aas/transformation_resolver.h](BT_Controller/include/aas/transformation_resolver.h), [BT_Controller/src/aas/transformation_resolver.cpp](BT_Controller/src/aas/transformation_resolver.cpp).
- [BT_Controller/include/bt/bt_log.h](BT_Controller/include/bt/bt_log.h), [BT_Controller/src/bt/bt_log.cpp](BT_Controller/src/bt/bt_log.cpp).
- [BT_Controller/include/bt/register_all_nodes.h](BT_Controller/include/bt/register_all_nodes.h).
- [BT_Controller/Project.btproj](BT_Controller/Project.btproj).

PR1 (frozen, reference only):
- [Planner/aas_to_pddl_conversion/parsing.py](Planner/aas_to_pddl_conversion/parsing.py), [Planner/aas_to_pddl_conversion/merge.py](Planner/aas_to_pddl_conversion/merge.py), [Planner/aas_to_pddl_conversion/up_builder.py](Planner/aas_to_pddl_conversion/up_builder.py), [Planner/aas_to_pddl_conversion/models.py](Planner/aas_to_pddl_conversion/models.py), [Planner/aas_to_pddl_conversion/pipeline.py](Planner/aas_to_pddl_conversion/pipeline.py).
- [Planner/bt_synthesis/nodes.py](Planner/bt_synthesis/nodes.py), [Planner/bt_synthesis/builder.py](Planner/bt_synthesis/builder.py), [Planner/bt_synthesis/plan_converters.py](Planner/bt_synthesis/plan_converters.py), [Planner/bt_synthesis/execution_refs.py](Planner/bt_synthesis/execution_refs.py), [Planner/bt_synthesis/xml_writer.py](Planner/bt_synthesis/xml_writer.py).

**Verification**
1. PR1 tests (passing): planner-generated BT XML carries complete AAS path / binding metadata, quoted semicolon args, main-tree defaulted link-port declarations.
2. PR2 unit tests (10/10 passing): `parseArgsList`, `parseActionRef`, `parsePredicateRef` round-trips and HTML-entity decoding.
3. PR3 unit tests (16/16 passing): adds 6 `splitSubmodelPath` cases (`AI-Planning` -> `AIPlanning`, camelCase pass-through, known submodel pass-through, empty input, no-slash, unknown prefix).
4. PR4 unit: new `test_symbolic_state.cpp` covers seed/get/set/erase, canonical key determinism, missing-key semantics, JSON value round-trip.
5. PR4 unit: extended `test_execution_refs.cpp` parses `initial_state` and `ActionRef.effects`; back-compat verified against PR3 trees lacking the new fields.
6. PR4 integration smoke: dispensing tree with purely symbolic `step_*` progresses through all steps; debug logs show `SymbolicState` transitions matching the plan.
7. PR4 build: `cmake --build BT_Controller/build -j` succeeds; `LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu ./BT_Controller/build/tests/test_symbolic_state` passes; `test_execution_refs` still passes (now > 16 cases).
8. PR5 tests: explicit `sensor-backed` / `symbolic-only` / `hybrid` classification respected; hybrid path respects timeout.
9. PR6 tests: divergence detection publishes update events and triggers expected replan policy.
10. PR7 end-to-end: duplicated action names with suffixes invoke correct AAS assets; sensor-backed and symbolic predicates both behave correctly; strong-cyclic preservation re-checked against the C++ runtime.

**Decisions**
- Include scope: transformation functions are fetched by runtime nodes during construction using AAS paths from BT XML.
- Include scope: planner XML contract is strict for runtime nodes - no legacy fluent/action_name ports; use `predicate_ref`/`predicate_args` and `action_ref`/`action_args`.
- Include scope: multi-argument values are encoded as quoted semicolon-delimited generic strings.
- Include scope: link refs are provided through main-tree SubTree input-port defaults, not setup-time SetBlackboard nodes.
- Include scope: transformation expressions are in JSONata format, evaluated in C++ via `rayokota/jsonata-cpp` v0.1.2.
- Include scope: direct MQTT communication is preferred when an Asset Interface Description exists.
- Include scope: fallback path is direct AAS operation invocation (`…/submodel-elements/<path>/invoke`) when interface metadata is unavailable.
- Include scope: AAS represents physical/digital-twin reality; sensor-backed predicates only.
- Include scope: symbolic planning state lives in an in-process `SymbolicState` store in `BT_Controller`; flat key/value map keyed by canonical ground-atom strings; no AAS PATCH or writeback; `SymbolicState` is in-memory only and a controller restart implies replan.
- Include scope: PDDL effect literals are applied verbatim to `SymbolicState` on action SUCCESS; no per-action JSONata setter expressions; subject-ownership is moot because there is no AAS storage for symbolic atoms.
- Include scope: `ExecuteAction` and `FluentCheck` coexist with legacy nodes; legacy registrations remain in `register_all_nodes.h`.
- Include scope: parameterized SubTree template `{argN}` ports are handled natively by BT.CPP port chaining.
- Include scope: active development scope is PR4; PR5–PR7 remain in outline form.
- Exclude scope: redesign of legacy handcrafted BT files not produced by planner pipeline.
- Exclude scope: response-side reverse JSONata transformation in PR3 (revisit in PR5 if needed).
- Exclude scope (PR4): AAS PATCH / writeback infrastructure; Process AAS `Variables` submodel for grounded planning atoms; Product Instance AAS YAML provisioning; Registration_Service AIPlanning/Init extensions; `SymbolicState` persistence across restarts; MQTT mirror of `SymbolicState`; numeric / non-bool fluent pipeline (storage tolerates arbitrary JSON but planner stays bool-only until needed).
- Exclude scope (PR4): runtime knowledge graph / RDF store. Migration path remains open as a future PR if/when runtime replanning, cross-asset queries, provenance, or persistence become first-class requirements - `ppr-ontology/` and `unified-planning/` are pre-positioned for this.

**Further Considerations**
1. JSONata dialect aligns with the reference implementation through `rayokota/jsonata-cpp`; keep transformations within its supported feature set and pin the library version.
2. Dev container may lack internet access for `FetchContent`; v0.1.2 release zip is vendored under `BT_Controller/third_party/jsonata-cpp/`.
3. AAS operation-invoke endpoint path may differ between BaSyx versions; PR3 confirmed against the deployed server. MQTT remains the primary path.
4. BT.CPP normally decodes XML entities in attribute values; `parseActionRef` / `parsePredicateRef` tolerate both raw and HTML-entity-encoded JSON.
5. Confirm planner-facing topic / API for plan update notifications before PR6 implementation.
6. `SymbolicState` is per-tree and per-process; if a future use case requires multiple controllers sharing planning state, the flat-map abstraction must be promoted to a queryable shared store - prefer that as the trigger for the knowledge-graph migration above rather than hand-rolling distribution on the flat map.
7. The PR2/PR3 `ExecutionRefs` parser must remain tolerant of trees emitted before PR4 added `initial_state` / `effects`; existing dispensing/loading XMLs in `Planner/output/ai_planning_runs/` serve as back-compat fixtures.
## Plan: Transformation-Driven Executable BT Pipeline (v2)

Build an end-to-end execution contract where planner-generated BT nodes contain AAS paths and parameter bindings, while BT runtime nodes fetch transformation logic at construction time, prefer direct interface communication when available, and fall back to direct AAS operation access when interface metadata is missing. Add a Process AAS world-model submodel to persist symbolic fluents and keep plan state updateable.

PR1 is complete and the planner-side XML contract is frozen. The interim BT-synthesis rework (templates, hoisting, Monte-Carlo strong-cyclic verification via `Planner/experiments/run_bt_hoisting_equivalence.py`) did not change the PR1 contract, so PR2+ proceed against it unchanged. Active scope for this revision: PR2 + PR3 in detail; PR4–PR7 in outline.

**Steps**

PR1 - DONE (frozen, do not modify)
1. ExecuteAction and FluentCheck XML emission with action_ref/action_args and predicate_ref/predicate_args.
2. Quoted semicolon-delimited args (for example `"{Param_a};{Param_b}"`) to satisfy BT.CPP generic-port constraints.
3. Payload and parameter-link aliases declared as MainTree SubTree input_port defaults in TreeNodesModel; no setup-tree SetBlackboard.
4. transformation_aas_path captured per action and per fluent in parsing, propagated through merge -> up_builder -> planner_metadata.action_refs / predicate_refs / object_refs (with `_ci` lowercase variants).
5. Tests `test_bt_synthesis_hoisting.py` and `test_pipeline_facade.py` lock the contract in.

PR2 - Runtime contract alignment and transformation fetch (DONE)
6. Phase 2.A Dependencies and AAS client extensions: DONE
   - Added `rayokota/jsonata-cpp` v0.1.2 via CMake `FetchContent` (with local-zip override under `BT_Controller/third_party/jsonata-cpp/`). Linked `jsonata::jsonata` PUBLIC into `bt_controller_common`.
   - Extended `AASClient` with `fetchSubmodelElementByPath(asset_id, submodel_id_short, slash_path)` (walks the in-memory submodel tree by `idShort` segments; reuses `fetchSubmodelData`) and `invokeOperation(asset_id, submodel_id_short, operation_aas_path, input_json)` (POST to `/submodels/<base64url>/submodel-elements/<dot.path>/invoke` with a minimal BaSyx InvocationRequest envelope; resets `CURLOPT_POST` after each call). New private `makePostRequest` helper.
   - Added `TransformationResolver` (`include/aas/transformation_resolver.h`, `src/aas/transformation_resolver.cpp`) caching `(aas_id, transformation_aas_path) -> std::string JSONata expression`. Candidate submodels tried in order: `AIPlanning`, `Skills`, `Capabilities`, `Variables`. Failures are not cached.
7. Phase 2.B Shared parsing utility: DONE
   - New `BT_Controller/include/bt/execution_refs.h` and `src/bt/execution_refs.cpp` providing `ActionRef` and `PredicateRef` structs, `parseActionRef` / `parsePredicateRef` (tolerant of HTML-entity escaping in XML attributes via `decodeHtmlEntities`), and `parseArgsList` that strips one optional wrapping `"…"` layer and splits on `;`. Empty input yields empty vector. Tokens are returned as-is because BT.CPP port chaining has already substituted `{Param_*}` blackboard values. DONE.
   - 10 unit tests in `BT_Controller/tests/test_execution_refs.cpp` (built behind CMake option `BT_CONTROLLER_BUILD_TESTS=ON`). DONE.
8. Phase 2.C Runtime nodes (coexist with legacy nodes; legacy registrations untouched): DONE
   - `ExecuteAction` (in `include/bt/actions/execute_action_node.h` and `src/bt/actions/execute_action_node.cpp`) derives from `MqttActionNode`. providedPorts: `action_ref`, `action_args`, `Uuid`. `initializeTopicsFromAAS()` parses the ref, derives the interaction name from the last segment of `action_aas_path`, fetches the JSONata transformation via `TransformationResolver`, then attempts cached interface → live `aas_client_.fetchInterface` → marks `aas_direct_fallback_=true` if neither succeeds (gated by env flag).
   - `FluentCheck` (in `include/bt/conditions/fluent_check_node.h` and `src/bt/conditions/fluent_check_node.cpp`) derives from `MqttSyncConditionNode`. providedPorts: `predicate_ref`, `predicate_args`. Subscribes to fluent data interface; if no interface, polls `AASClient::fetchSubmodelElementByPath` per tick on the AAS-direct path.
   - Both registered in `register_all_nodes.h` via `MqttActionNode::registerNodeType<ExecuteAction>` / `MqttSyncConditionNode::registerNodeType<FluentCheck>`. All legacy registrations intact.
9. Phase 2.D Diagnostics and safety: DONE (PR3 will tighten log levels)
   - Parse / fetch / JSONata-compile failures emit one `std::cerr` line with node name, AAS id, AAS path, and a 200-char-truncated payload snippet, then return `FAILURE` rather than throwing.
   - JSONata expressions are compiled once per node on first successful fetch and cached on the node instance.

PR3 - Direct execution and predicate evaluation engine (ACTIVE)
Most of items 10-14 below already landed during PR2 implementation; PR3 focuses on the corrections required by the actual planner XML contract observed at `Planner/output/ai_planning_runs/20260424T101143Z/behavior_tree.xml`:
   - `action_aas_path` and `fluent_aas_path` are emitted with a leading `AI-Planning/...` segment whose `idShort` in the actual submodel is `AIPlanning` (no hyphen).
   - `transformation_aas_path` is empty for actions and for symbolic-only predicates (`Predicate_Object`).
   - `action_aas_path` points into the AIPlanning Action SMC, not into the invokable Skill operation. The Skills operation must be reached via the AIPlanning Action's `SkillReference`.

10. `ExecuteAction::createMessage()` evaluates the cached JSONata transformation against context `{ args: [...resolved arg strings...], object_refs: { name: { aas_id, aas_path } }, now: <iso8601> }`; merges result with `{"Uuid": <uuid>}`. If the transformation returns a scalar, wrap as `{"value": scalar}`. DONE in PR2.
11. Response handling reuses the existing `MqttActionNode` lifecycle without reverse transformation in PR3 (revisit in PR5 if needed). DONE.
12. `FluentCheck::tick()` evaluates the JSONata transformation against the latest received message (or the polled property value on the fallback path). Contract: result must be a boolean or `{"value": <bool>}`. Anything else returns `FAILURE` plus a structured diagnostic. DONE in PR2. **Symbolic-only predicates with empty `transformation_aas_path`** (e.g. `Predicate_Object` for StepDone/StepReady) are deferred to PR4 - they must be served from the Process AAS Variables submodel, not from a per-resource sensor. PR3 logs them as `FAILURE` with a clear "no transformation, awaiting PR4 world-model" message rather than spamming on every tick.
13. AAS-direct invocation path: `AASClient::invokeOperation` is in place. PR3 adds `AASClient::resolveSkillReference(aas_id, action_aas_path)` that walks the AIPlanning Action SMC, locates its `SkillReference` (a ReferenceElement), and returns `(skills_submodel_id_short, operation_aas_path)`. `ExecuteAction::onStart` then invokes the resolved Skills operation instead of guessing.
14. Add an env flag `BT_CONTROLLER_AAS_DIRECT=auto|force|disable` for forcing one path during debugging. DONE in PR2.
15. Binding-snapshot logging: PR3 introduces a tiny `bt_log` facade with `BT_LOG_DEBUG` / `BT_LOG_ERROR` macros gated by env `BT_CONTROLLER_LOG_LEVEL=debug|info|error` (default `info`). `ExecuteAction` and `FluentCheck` route their existing `std::cerr` lines through the facade so production runs are not noisy.
16. **AAS-Planning path normalization** (new in PR3): both `TransformationResolver` and `FluentCheck` AAS-direct fallback strip a leading `AI-Planning/` or `AIPlanning/` segment from the slash path, query the `AIPlanning` submodel, and use the remainder as the in-submodel path. Other known prefixes (`Skills/`, `Capabilities/`, `Variables/`) are normalized similarly so that the planner-emitted contract is honored verbatim.

PR4 - Process AAS world model for symbolic fluents (outline)
16. Extend `Planner/process_aas_generation_publishing/process_aas_generator.py` to emit a `Variables` submodel scoped to the process instance (mirrors existing Variables submodels in this repository). Each symbolic fluent (StepReady, StepDone, etc.) becomes a Property element with initial value.
17. Add `AASClient::readVariable` and `AASClient::writeVariable` thin wrappers over `fetchSubmodelElementByPath` and the corresponding PATCH/PUT endpoint. Wire a process-world-model context into `BehaviorTreeController.cpp` so all nodes can access it through a shared handle.

PR5 - Effect interpretation policy and state update rules (outline)
18. Classify effects in planner metadata as `sensor-backed`, `symbolic-only`, or `hybrid`.
19. Runtime applies symbolic-only effects to the Variables submodel immediately upon action success.
20. Sensor-backed effects are validated by a downstream FluentCheck or by an active subscription before the BT advances.
21. Hybrid effects: write symbolic update first, then confirm observed state within a configurable timeout window.

PR6 - Plan-state synchronization and plan update loop (outline)
22. Add divergence detection in BT_Controller comparing expected symbolic transitions to observed Variables-submodel state.
23. Publish plan-state updates and divergence events on a planner-facing MQTT topic (topic name TBD with planner team before implementation).
24. Replan trigger policy: hard failure on unresolvable divergence; soft continuation on transient sensor mismatch within timeout.

PR7 - End-to-end validation and rollout hardening (outline)
25. Validate duplicate-suffixed action names invoke the correct AAS targets per grounded instance.
26. Validate predicates across both sensor-backed and symbolic-only cases (Operational vs StepDone).
27. Validate quoted semicolon args and main-tree defaulted link ports end-to-end in both policy and deterministic-plan paths.
28. Run integration with and without Asset Interface Description to confirm both direct and fallback paths work.
29. Extend `Planner/experiments/run_bt_hoisting_equivalence.py` to additionally exercise the C++ runtime path so the strong-cyclic preservation guarantee is checked against real execution, not just the Python simulator.

**Relevant files**

PR2 + PR3 (active scope):
- [BT_Controller/CMakeLists.txt](BT_Controller/CMakeLists.txt) - FetchContent for jsonata-cpp; add new .cpp files to `bt_controller_common`.
- [BT_Controller/include/aas/aas_client.h](BT_Controller/include/aas/aas_client.h) and [BT_Controller/src/aas/aas_client.cpp](BT_Controller/src/aas/aas_client.cpp) - add `fetchSubmodelElementByPath` and `invokeOperation`.
- [BT_Controller/include/aas/transformation_resolver.h](BT_Controller/include/aas/transformation_resolver.h) - new cached transformation fetch wrapper.
- [BT_Controller/include/bt/execution_refs.h](BT_Controller/include/bt/execution_refs.h) and `src/bt/execution_refs.cpp` - new `ActionRef`/`PredicateRef` structs and parsing utilities.
- [BT_Controller/include/bt/actions/execute_action_node.h](BT_Controller/include/bt/actions/execute_action_node.h) and `src/bt/actions/execute_action_node.cpp` - new generic ExecuteAction node.
- [BT_Controller/include/bt/conditions/fluent_check_node.h](BT_Controller/include/bt/conditions/fluent_check_node.h) and `src/bt/conditions/fluent_check_node.cpp` - new generic FluentCheck node.
- [BT_Controller/include/bt/register_all_nodes.h](BT_Controller/include/bt/register_all_nodes.h) - register new types; keep all legacy registrations.
- [BT_Controller/src/bt/mqtt_action_node.cpp](BT_Controller/src/bt/mqtt_action_node.cpp) and [BT_Controller/src/bt/mqtt_sync_condition_node.cpp](BT_Controller/src/bt/mqtt_sync_condition_node.cpp) - reuse base lifecycle; no changes expected.
- [BT_Controller/Project.btproj](BT_Controller/Project.btproj) - keep Groot node-model declarations aligned with `action_ref`/`action_args` and `predicate_ref`/`predicate_args`.

PR4+ (outline scope):
- [Planner/process_aas_generation_publishing/process_aas_generator.py](Planner/process_aas_generation_publishing/process_aas_generator.py) - add Variables submodel generation.
- [BT_Controller/src/BehaviorTreeController.cpp](BT_Controller/src/BehaviorTreeController.cpp) - initialize shared process world-model context for all nodes.

PR1 (frozen, reference only):
- [Planner/aas_to_pddl_conversion/parsing.py](Planner/aas_to_pddl_conversion/parsing.py), [merge.py](Planner/aas_to_pddl_conversion/merge.py), [up_builder.py](Planner/aas_to_pddl_conversion/up_builder.py), [models.py](Planner/aas_to_pddl_conversion/models.py), [pipeline.py](Planner/aas_to_pddl_conversion/pipeline.py).
- [Planner/bt_synthesis/nodes.py](Planner/bt_synthesis/nodes.py), [builder.py](Planner/bt_synthesis/builder.py), [plan_converters.py](Planner/bt_synthesis/plan_converters.py), [execution_refs.py](Planner/bt_synthesis/execution_refs.py), [xml_writer.py](Planner/bt_synthesis/xml_writer.py).

**Verification**
1. PR1 tests (already passing): planner-generated BT XML contains complete AAS path and binding metadata, quoted semicolon args strings, and main-tree defaulted link-port declarations.
2. PR2 unit: `parseArgsList` round-trips quoted `"{a};{b}"` -> `["{a}","{b}"]`; plain `a;b` -> `["a","b"]`; empty/whitespace handled.
3. PR2 unit: `parseActionRef` decodes both raw JSON and HTML-entity-encoded JSON as found in generated XML (sample: `Planner/output/ai_planning_runs/20260423T081106Z/behavior_tree.xml`).
4. PR2 integration: load a generated BT XML in a bare `BT::BehaviorTreeFactory` with both new node types registered; confirm parsing succeeds and `TreeNodesModel` SubTree defaults populate the blackboard with `{Param_*}`, `{FluentLink_*}`, `{ActionLink_*}`.
5. PR2 integration: a mock `AASClient` returns a canned transformation; confirm `ExecuteAction` constructs the expected message JSON and `FluentCheck` evaluates to `SUCCESS` on matching data.
6. PR2 regression: legacy handcrafted BTs (loading.xml, dispensing.xml) still execute unchanged.
7. PR3 integration: `ExecuteAction` drives a Dispensing action end-to-end via simulated stations - MQTT command published, response consumed, BT returns `SUCCESS`.
8. PR3 integration: temporarily disable an asset's Interface Description and confirm the node falls back to `invokeOperation` and still returns `SUCCESS`.
9. PR3 integration: a sensor-backed `FluentCheck` (e.g. `Occupied`) returns correct SUCCESS/FAILURE as the underlying MQTT data changes.
10. PR3 error injection: malformed transformation JSONata, missing AAS operation, malformed response JSON each produce a single clear ERROR log and BT `FAILURE` without crashing the controller.
11. PR4 tests: process world-model submodel is generated and runtime can read or update symbolic fluents.
12. PR5 tests: symbolic-only effects update world model without requiring sensor data; sensor-backed effects use runtime observation; hybrid path respects timeout.
13. PR6 tests: divergence detection publishes update events and triggers expected replan policy.
14. PR7 end-to-end: duplicated action names with suffixes still invoke correct AAS assets, preserve traceable provenance, and remain compatible with the frozen PR1 XML contract; strong-cyclic preservation re-checked against the C++ runtime.

**Decisions**
- Include scope: transformation functions are fetched by runtime nodes during construction using AAS paths from BT XML.
- Include scope: planner XML contract is strict for runtime nodes - no legacy fluent/action_name ports; use predicate_ref/predicate_args and action_ref/action_args.
- Include scope: multi-argument values are encoded as quoted semicolon-delimited generic strings.
- Include scope: link refs are provided through main-tree SubTree input-port defaults, not setup-time SetBlackboard nodes.
- Include scope: transformation expressions are in JSONata format, evaluated in C++ via `rayokota/jsonata-cpp` v0.1.2 integrated via CMake `FetchContent`.
- Include scope: direct MQTT communication is preferred when an Asset Interface Description exists.
- Include scope: fallback path is direct AAS operation invocation (`…/submodel-elements/<path>/invoke`) when interface metadata is unavailable.
- Include scope: process-scoped world model is stored in the Process AAS using a Variables submodel (PR4).
- Include scope: full predicate support includes both sensor-backed and symbolic-only fluents.
- Include scope: required AAS endpoints for invoke and read or write access are available.
- Include scope: ExecuteAction and FluentCheck coexist with legacy nodes (GenericActionNode, Data_Condition, MoveToPosition, etc.); legacy registrations remain in `register_all_nodes.h`.
- Include scope: parameterized SubTree template `{argN}` ports are handled natively by BT.CPP port chaining; no planner-side flattening pass is needed.
- Include scope: active development scope is PR2 + PR3; PR4–PR7 remain in outline form until PR2/PR3 land.
- Exclude scope: redesign of legacy handcrafted BT files not produced by planner pipeline.
- Exclude scope: response-side reverse JSONata transformation in PR3 (revisit in PR5 if needed).

**Further Considerations**
1. JSONata dialect aligns with the reference implementation through `rayokota/jsonata-cpp`; keep transformations within its supported feature set and pin the library version in `FetchContent`.
2. The dev container may lack internet access for `FetchContent`; if so, vendor the v0.1.2 release zip under `BT_Controller/third_party/jsonata-cpp/` and switch `FetchContent_Declare` to a local `URL`.
3. AAS operation-invoke endpoint path may differ between BaSyx versions; confirm the deployed server supports `…/invoke` before relying on PR3 AAS-direct path. MQTT remains the primary path.
4. BT.CPP normally decodes XML entities in attribute values; confirm by inspecting the raw blackboard value at runtime before finalizing `parseActionRef` / `parsePredicateRef`.
5. Confirm planner-facing topic or API for plan update notifications before PR6 implementation.
6. Cross-check the BT-synthesis rework artifacts (templates, hoisting, optimizer) to ensure their generated SubTree definitions are also exercised by the PR2 integration loader; the verifier in `Planner/experiments/run_bt_hoisting_equivalence.py` is the source of truth for strong-cyclic preservation.
## Plan: Transformation-Driven Executable BT Pipeline

Build an end-to-end execution contract where planner-generated BT nodes contain AAS paths and parameter bindings, while BT runtime nodes fetch transformation logic at construction time, prefer direct interface communication when available, and fall back to direct AAS operation access when interface metadata is missing. Add a Process AAS world-model submodel to persist symbolic fluents and keep plan state updateable.

**Steps**
1. PR1 - Planner metadata contract and XML payloads (completed, contract frozen).
2. Define and emit ActionRef and PredicateRef payloads in planner metadata with stable identity fields and provenance disambiguation for suffixed names.
3. Emit runtime-resolvable XML only for planner nodes: ExecuteAction uses action_ref and action_args, FluentCheck uses predicate_ref and predicate_args.
4. Remove legacy fluent and action_name XML inputs and keep name only as label/trace field.
5. Represent multi-argument ports as quoted semicolon-delimited generic strings, for example "{Param_a};{Param_b}", to satisfy BT.CPP generic-port constraints.
6. Replace setup-tree SetBlackboard writes with main-tree SubTree input_port defaults in TreeNodesModel so link refs are defined as defaults.
7. Keep PR1 tests validating action and predicate refs, parameter-link references, quoted semicolon args, and absence of SetBlackboard setup subtree.
8. PR2 - BT runtime contract alignment and transformation fetch at node construction.
9. Update runtime node registrations and NodeModel ports to the PR1 contract: action_ref/action_args and predicate_ref/predicate_args.
10. Add shared parsing utility for args ports that strips optional wrapping quotes and splits semicolon-delimited lists into typed argument arrays.
11. Resolve each argument token to its linked AAS ref via the main-tree defaulted input-port values before transformation binding.
12. Add a runtime TransformationResolver service that uses AAS submodel reads similarly to existing interface lookup logic.
13. During node initialization, detect whether an Asset Interface Description exists for the interaction and configure direct MQTT path when present.
14. If no interface exists, configure AAS-direct fallback path for action invocation or predicate data retrieval.
15. PR3 - Direct execution and predicate evaluation engine.
16. Implement ExecuteAction runtime behavior: bind resolved parameter refs, apply transformation, publish command through MQTT when direct interface exists, otherwise invoke through AAS operation endpoint.
17. Implement FluentCheck runtime behavior: bind resolved parameter refs, fetch required runtime values, evaluate transformation expression output, return BT success or failure.
18. Add strict diagnostics on parsing, ref-resolution, fetch, or transformation evaluation failures including node name, AAS path, and binding snapshot.
19. PR4 - Process AAS world model for symbolic fluents.
20. Extend Process AAS generation to include a Variables-like submodel for planning world state, scoped to each process instance.
21. Persist symbolic fluents such as StepReady, StepDone, and other non-sensor predicates in this process-level submodel.
22. Add runtime world-model client in BT_Controller to read and write symbolic fluents via AAS APIs.
23. PR5 - Effect interpretation policy and state update rules.
24. Classify effects into three categories in planner metadata: sensor-backed, symbolic-only, and hybrid.
25. Runtime applies symbolic effects immediately to process world model after action result and validates sensor-backed effects via FluentCheck or data subscriptions.
26. For hybrid effects, apply symbolic update first and confirm observed state within timeout window.
27. PR6 - Plan-state synchronization and plan update loop.
28. Add runtime divergence detection between expected symbolic state transitions and observed world-model state.
29. Publish plan-state updates and divergence events through planner-facing channel so current plan can be updated or replanned.
30. Add controlled replan trigger strategy: hard failure on unresolvable divergence, soft continuation on transient sensor mismatch.
31. PR7 - End-to-end validation and rollout hardening.
32. Validate duplicate action-name cases where suffixes exist and confirm exact AAS target execution for each grounded action instance.
33. Validate predicates across both sensor-backed and symbolic-only cases, including Operational versus StepDone behavior.
34. Validate that quoted semicolon args and main-tree defaulted link ports work end-to-end in both policy and deterministic-plan paths.
35. Run integration tests with and without Asset Interface Description to confirm direct and fallback paths both work.

**Relevant files**
- [Planner/aas_to_pddl_conversion/parsing.py](Planner/aas_to_pddl_conversion/parsing.py) - extend parsed action and fluent records with transformation source path metadata.
- [Planner/aas_to_pddl_conversion/merge.py](Planner/aas_to_pddl_conversion/merge.py) - preserve provenance and path mapping through deduplication and namespacing.
- [Planner/aas_to_pddl_conversion/up_builder.py](Planner/aas_to_pddl_conversion/up_builder.py) - bind UP action names to provenance records used in runtime metadata export.
- [Planner/aas_to_pddl_conversion/models.py](Planner/aas_to_pddl_conversion/models.py) - add ActionRef and PredicateRef metadata contracts.
- [Planner/aas_to_pddl_conversion/pipeline.py](Planner/aas_to_pddl_conversion/pipeline.py) - include action and predicate execution metadata in artifacts and solve metadata.
- [Planner/bt_synthesis/nodes.py](Planner/bt_synthesis/nodes.py) - extend node data model to carry structured execution references.
- [Planner/bt_synthesis/builder.py](Planner/bt_synthesis/builder.py) - attach provenance references for policy-mode action and condition nodes.
- [Planner/bt_synthesis/plan_converters.py](Planner/bt_synthesis/plan_converters.py) - attach provenance references for deterministic-plan action and condition nodes.
- [Planner/bt_synthesis/execution_refs.py](Planner/bt_synthesis/execution_refs.py) - resolve grounded action or predicate parameters to object link references.
- [Planner/bt_synthesis/xml_writer.py](Planner/bt_synthesis/xml_writer.py) - serialize ActionRef and PredicateRef, quoted semicolon args, and main-tree defaulted input-port links.
- [Planner/process_aas_generation_publishing/process_aas_generator.py](Planner/process_aas_generation_publishing/process_aas_generator.py) - add process world-model submodel generation.
- [BT_Controller/include/aas/aas_client.h](BT_Controller/include/aas/aas_client.h) - add transformation fetch and AAS operation invocation support methods.
- [BT_Controller/src/aas/aas_client.cpp](BT_Controller/src/aas/aas_client.cpp) - implement transformation path reads, fallback execution calls, and world-model read or write calls.
- [BT_Controller/src/BehaviorTreeController.cpp](BT_Controller/src/BehaviorTreeController.cpp) - initialize shared process world-model context and expose it to nodes.
- [BT_Controller/include/bt/register_all_nodes.h](BT_Controller/include/bt/register_all_nodes.h) - register ExecuteAction and FluentCheck runtime node types for planner XML.
- [BT_Controller/Project.btproj](BT_Controller/Project.btproj) - keep Groot node-model declarations aligned with action_ref/action_args and predicate_ref/predicate_args.
- [BT_Controller/src/bt/mqtt_action_node.cpp](BT_Controller/src/bt/mqtt_action_node.cpp) - reusable MQTT action lifecycle integration for new generic execution node.
- [BT_Controller/src/bt/mqtt_sync_condition_node.cpp](BT_Controller/src/bt/mqtt_sync_condition_node.cpp) - reusable sync condition lifecycle integration for new generic predicate node.
- [BT_Controller/src/bt/actions](BT_Controller/src/bt/actions) - add generic planner-driven ExecuteAction runtime node implementation.
- [BT_Controller/src/bt/conditions](BT_Controller/src/bt/conditions) - add generic planner-driven FluentCheck runtime node implementation.

**Verification**
1. PR1 tests: planner-generated BT XML contains complete AAS path and binding metadata, quoted semicolon args strings, and main-tree defaulted link-port declarations.
2. PR2 tests: runtime correctly parses quoted semicolon args strings, resolves link refs from main-tree defaulted ports, and fetches transformation definitions using AAS paths.
3. PR3 tests: ExecuteAction and FluentCheck execute with transformation-bound parameters and produce expected success or failure status.
4. PR4 tests: process world-model submodel is generated and runtime can read or update symbolic fluents.
5. PR5 tests: symbolic-only effects update world model without requiring sensor data, while sensor-backed effects use runtime observation.
6. PR6 tests: divergence detection publishes update events and triggers expected replan policy.
7. End-to-end tests: duplicated action names with suffixes still invoke correct AAS assets, preserve traceable provenance, and remain compatible with the frozen PR1 XML contract.

**Decisions**
- Include scope: transformation functions are fetched by runtime nodes during construction using AAS paths from BT XML.
- Include scope: planner XML contract is strict for runtime nodes: no legacy fluent/action_name ports, use predicate_ref/predicate_args and action_ref/action_args.
- Include scope: multi-argument values are encoded as quoted semicolon-delimited generic strings.
- Include scope: link refs are provided through main-tree SubTree input-port defaults, not setup-time SetBlackboard nodes.
- Include scope: transformation expressions are in JSONata format.
- Include scope: direct communication is preferred when Asset Interface Description exists.
- Include scope: fallback path is direct AAS operation invocation when interface metadata is unavailable.
- Include scope: process-scoped world model is stored in Process AAS using a Variables-like submodel.
- Include scope: full predicate support includes both sensor-backed and symbolic-only fluents.
- Include scope: required AAS endpoints for invoke and read or write access are available.
- Exclude scope: redesign of legacy handcrafted BT files not produced by planner pipeline.

**Further Considerations**
1. JSONata dialect is confirmed for transformations; runtime evaluator and validation behavior should align to this dialect.
2. AAS invoke and read or write endpoints are confirmed available; endpoint-specific implementation details can be refined during PR2 to PR4.
3. Confirm planner-facing topic or API for plan update notifications before PR6 implementation.
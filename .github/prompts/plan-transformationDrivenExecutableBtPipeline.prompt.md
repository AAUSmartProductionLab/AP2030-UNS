## Plan: Transformation-Driven Executable BT Pipeline (v4)

End-to-end goal: take a planner-generated BT (deterministic plan or FOND
policy) and execute it against the AAS-described production resources
(real or simulated) without manual intervention. PR1–PR4 built the
contract and the runtime primitives. PR5 onward closes the remaining
gaps so a freshly-generated tree actually ticks to SUCCESS on the
deployed stack.

PR1 — DONE (v3 §1–5). Planner XML contract frozen: `action_ref`/`action_args`,
`predicate_ref`/`predicate_args`, quoted semicolon args, MainTree SubTree
input_port defaults, `transformation_aas_path` propagated through
`planner_metadata.{action,predicate,object}_refs`.

PR2 — DONE (v3 §6–9). `jsonata-cpp` v0.1.2 vendored, `AASClient`
extended (`fetchSubmodelElementByPath`, `invokeOperation`),
`TransformationResolver` cache, shared `bt_exec_refs::{ActionRef,
PredicateRef, parseActionRef, parsePredicateRef, parseArgsList}`,
`ExecuteAction`/`FluentCheck` registered alongside legacy nodes,
single-line diagnostics on parse/fetch/compile failure.

PR3 — DONE (v3 §10–16). `ExecuteAction::createMessage()` evaluates
JSONata against `{args, object_refs, now}` + UUID merge.
`AASClient::resolveSkillReference()` walks AIPlanning Action SMC →
`SkillReference`. `BT_CONTROLLER_AAS_DIRECT=auto|force|disable`.
`bt_log` facade with `BT_CONTROLLER_LOG_LEVEL`.
`splitSubmodelPath()` canonicalises `AI-Planning` → `AIPlanning` and
recognises Skills/Capabilities/Variables/AID/ProcessInformation/etc.

PR4 — DONE (v3 §17–28, see `/memories/repo/pr4_symbolic_state.md`).
Process-wide `SymbolicState` singleton (per-tree clear+seed inside
`BehaviorTreeController` after `createTreeFromText`). `ActionRef.effects`
+ `parseGroundedAtomList`. Symbolic `FluentCheck` parses
`predicate(args)` from BT node `name()`. `ExecuteAction::applySymbolicEffects()`
on SUCCESS, with `effects_applied_` latch covering both AAS-direct and
MQTT paths. Planner emits `_planner_initial_state` on the MainTree
SubTree input_port. Coverage: 35 C++ tests + 15 Python tests.

---

## Active scope: PR5 — End-to-end execution against AAS resources

Goal: a freshly emitted BT (deterministic plan today, FOND policy as
soon as the executor exercises both branches) ticks to SUCCESS against
either `simulated_stations/` or the lab stack, with no per-tree
hand-edits. Each phase unblocks one concrete failure mode observed in
PR3/PR4 dry runs or anticipated from the v3 outline.

### Phase 5.A — Audit and reproduce a clean run
29. Boot the deployment with `simulated_stations` and at least one
    Process AAS, generate a BT via `production_planner` (deterministic
    path first), let `BT_Controller` pick it up via `fetchPolicyBTUrl`,
    and capture a baseline log of every `ExecuteAction` /
    `FluentCheck` tick at `BT_CONTROLLER_LOG_LEVEL=debug`.
30. Triage failures into three buckets: (i) JSONata context shape
    mismatches, (ii) predicate evaluation issues, (iii) lifecycle /
    response-routing issues. Each bucket maps to one of phases
    5.B–5.D below; a fourth bucket (planner-side missing data) feeds
    back to the planner team rather than this PR.
31. Snapshot the captured BT XML + a representative AAS export under
    `BT_Controller/tests/fixtures/end_to_end/` so later phases can
    replay without the full stack.

### Phase 5.B — JSONata context completeness for ExecuteAction
32. Verify `createMessage()` exposes everything a transformation can
    legitimately ask for: `args` (already), `object_refs` (already
    fetched from `planner_metadata`), `now` (already), and **add**
    `process_aas_id` plus `action_aas_path` so transformations can
    self-identify when emitting MQTT envelopes.
33. Confirm `object_refs` entries are reachable as
    `object_refs.<name>.aas_id` / `.aas_path` (not nested deeper).
    If not, normalise the planner-side dict shape in
    `Planner/bt_synthesis/execution_refs.py::_resolve_object_ref` and
    the runtime parser symmetrically.
34. Add a focused unit test covering:
    `ExecuteAction::createMessage()` against a representative
    transformation taken verbatim from `AASDescriptions/Resource/`
    (dispense, move, occupy). Mock `TransformationResolver` returns
    the JSONata expression; assert on the produced JSON envelope.

### Phase 5.C — FluentCheck robustness for first-tick and multi-arg
35. First-tick semantics: when no MQTT message has yet arrived for a
    sensor-backed predicate, `FluentCheck` currently returns
    `FAILURE`. That is correct for "is occupied" style checks but
    breaks for negated guards. Add a configurable initial mode per
    predicate (`pessimistic_false` / `optimistic_true`) wired via the
    transformation's `defaultValue` SMC element if present (already
    common in `AASDescriptions/`). Default remains `pessimistic_false`.
36. Multi-arg predicates: `FluentCheck::tick()` already passes
    `args` from the BT node name to the JSONata context, but the
    AAS-direct fallback path needs to swap `aas_id`/`aas_path` per
    argument when the predicate is parameterised over multiple
    objects. Audit `splitSubmodelPath` consumers; if the fallback
    path can't disambiguate, route through `object_refs[arg]` lookup
    just as `ExecuteAction` does.
37. Add fixture-driven tests in `test_fluent_check_node.cpp` (new):
    occupied-on-station, free-on-station, product-at, plus one
    symbolic case (`step_done(p,s)`) to lock the dual path in.

### Phase 5.D — Action lifecycle, response routing, and SkillReference coverage
38. End-to-end MQTT request/response: confirm the `Uuid` minted in
    `createMessage()` round-trips through the response topic so
    `MqttActionNode` matches the right correlation. Today's path
    relies on the topic match alone; add explicit Uuid matching when
    the response carries one (already common in
    `MQTTSchemas/commandResponse.schema.json`).
39. Reverse transformation (deferred from PR3): some skills emit
    structured responses where the planner-relevant outcome is a
    nested field. Add an optional `response_transformation` JSONata
    expression resolved alongside the request transformation; when
    present, run it on the response payload before
    `MqttActionNode::onResponse()` decides SUCCESS/FAILURE. Default
    behaviour (raw `{"success": true|false}` envelope) unchanged.
40. `AASClient::resolveSkillReference` works for `Skills/<name>/<name>`
    today; widen the walk to also handle `HierarchicalStructures`
    references and emit a single warning (not an error) on
    miss-then-fall-back-to-verbatim.
41. AAS-direct fallback: confirm `invokeOperation` against the live
    BaSyx server returns synchronously and produces the same
    SUCCESS/FAILURE shape as the MQTT path. Add an integration-style
    test gated by env (`BT_CONTROLLER_E2E=1`) that issues one real
    invoke against `simulated_stations/`.

### Phase 5.E — Initial state seeding completeness
42. Today's planner emits `step_ready(p, first_step)=true` but does
    not emit `step_ready(p, other_steps)=false` or `step_done(...)
    =false` because PDDL closed-world handles that implicitly. The
    BT runtime treats missing keys as `false` (`SymbolicState`
    `getBool`), so this is currently fine — but defensive: add a
    one-shot startup log enumerating which symbolic predicates were
    seeded vs assumed-false to make divergence obvious during
    triage.
43. If a future planner change starts emitting goal/precondition
    predicates the runtime hasn't seen seeded, the warning above is
    the trigger to revisit.

### Phase 5.F — Operational readiness gates
44. The plan currently assumes assets are `Operational`. In practice
    `BT_Controller` should hold the tree at the root until at least
    one `Operational` reading per used asset is observed, otherwise
    the first `ExecuteAction` will publish a command nobody is
    listening for. Add a small startup phase in
    `BehaviorTreeController` that waits (with timeout) for the
    initial round-trip of each interface used by the loaded BT; on
    timeout, log + fail fast rather than tick blindly.
45. Use the existing `aas_client_->fetchInterface` discovery to
    enumerate which assets the loaded BT depends on (cross-reference
    `action_refs[*].source_aas_id` and `predicate_refs[*].source_aas_id`).

### Phase 5.G — Tests, fixtures, and CI hooks
46. Add `BT_Controller/tests/test_execute_action_node.cpp` (new) and
    `tests/test_fluent_check_node.cpp` (new) running fully in-process
    against a mock `AASClient` + recorded MQTT messages. Both should
    work without any deployment running.
47. Reuse the `tests/fixtures/end_to_end/` snapshot from §31 as the
    canonical regression bundle.
48. Add a `BT_CONTROLLER_E2E=1` opt-in CMake target
    (`add_test(... CONFIGURATIONS E2E)`) that drives the full stack
    via `docker compose up -d simulated_stations production_planner`
    and asserts the dispensing tree completes within a deadline.

---

## PR6 — Effect interpretation policy (concrete, no longer outline)

49. Make the implicit PR4 classification explicit: extend
    `ActionRef.effects[*]` with `kind: "symbolic" | "sensor" | "hybrid"`
    populated by the planner from `_is_symbolic_fluent` plus a new
    "hybrid" tag for predicates whose AAS transformation reflects a
    write rather than a read (currently none, so default
    `hybrid=false`).
50. Runtime applies symbolic effects immediately (PR4). Sensor
    effects: post-action, schedule a one-shot `FluentCheck` against
    the affected predicate inside a configurable
    `BT_CONTROLLER_EFFECT_VERIFY_TIMEOUT_MS` window (default 5000);
    on timeout, emit divergence warning but do not fail the action
    (the tree's reactive structure will catch it on next tick).
51. Hybrid effects: optimistically write to `SymbolicState`, then
    confirm against the next sensor reading inside the same window;
    on mismatch, emit divergence warning AND erase the symbolic
    write so SymbolicState matches reality.

## PR7 — Plan-state synchronisation, replan loop (deferred)

52. Publish a `BTController/<process_id>/state` MQTT topic with
    `{tree_status, current_action, symbolic_state_snapshot,
    divergence_count}` at 1 Hz; consumers can re-trigger planning
    if needed. Topic schema lands in `MQTTSchemas/btState.schema.json`.
53. Divergence trigger: when the same predicate divergence repeats N
    times within a window, emit a `replan_request` event on
    `BTController/<process_id>/replan`. Planner subscription is the
    Planner team's contract, not implemented here.
54. Persistence and cross-controller sharing of `SymbolicState`
    remain explicitly out of scope until a real multi-controller
    deployment exists.

## PR8 — Validation and rollout hardening

55. Cross-product matrix: deterministic plan × FOND policy, with /
    without AID, sensor-backed / symbolic / mixed predicates,
    duplicated suffixed actions. Encode each cell as one fixture
    under `BT_Controller/tests/fixtures/`.
56. Long-soak: run the dispensing tree for 100 product cycles
    against `simulated_stations`, assert zero leaked subscriptions
    and bounded `SymbolicState` size.
57. Extend `Planner/experiments/run_bt_hoisting_equivalence.py` to
    optionally replay the produced BT through `BT_Controller` so the
    Monte-Carlo strong-cyclic preservation result is checked against
    the C++ runtime, not just the Python simulator.

---

## Relevant files

PR5 (active):
- [BT_Controller/src/BehaviorTreeController.cpp](BT_Controller/src/BehaviorTreeController.cpp) — startup gates (§44), debug logging (§29).
- [BT_Controller/include/bt/actions/execute_action_node.h](BT_Controller/include/bt/actions/execute_action_node.h), [BT_Controller/src/bt/actions/execute_action_node.cpp](BT_Controller/src/bt/actions/execute_action_node.cpp) — JSONata context (§32), Uuid round-trip (§38), response transformation (§39).
- [BT_Controller/include/bt/conditions/fluent_check_node.h](BT_Controller/include/bt/conditions/fluent_check_node.h), [BT_Controller/src/bt/conditions/fluent_check_node.cpp](BT_Controller/src/bt/conditions/fluent_check_node.cpp) — first-tick mode (§35), multi-arg fallback (§36).
- [BT_Controller/include/aas/aas_client.h](BT_Controller/include/aas/aas_client.h), [BT_Controller/src/aas/aas_client.cpp](BT_Controller/src/aas/aas_client.cpp) — `resolveSkillReference` widening (§40), `invokeOperation` E2E (§41).
- [Planner/bt_synthesis/execution_refs.py](Planner/bt_synthesis/execution_refs.py) — `object_refs` shape audit (§33).

PR5 (new test files):
- new: `BT_Controller/tests/test_execute_action_node.cpp`.
- new: `BT_Controller/tests/test_fluent_check_node.cpp`.
- new: `BT_Controller/tests/fixtures/end_to_end/` (snapshot bundle).

PR6 (planned):
- [Planner/aas_to_pddl_conversion/up_builder.py](Planner/aas_to_pddl_conversion/up_builder.py) — `kind` tagging on serialised effects (§49).
- [BT_Controller/src/bt/actions/execute_action_node.cpp](BT_Controller/src/bt/actions/execute_action_node.cpp) — sensor/hybrid verification window (§50–51).

PR7 (planned):
- new: `MQTTSchemas/btState.schema.json`.
- [BT_Controller/src/BehaviorTreeController.cpp](BT_Controller/src/BehaviorTreeController.cpp) — periodic state publish (§52).

PR8 (planned):
- [Planner/experiments/run_bt_hoisting_equivalence.py](Planner/experiments/run_bt_hoisting_equivalence.py) — runtime replay (§57).

PR1–PR4 (frozen, reference only):
- [BT_Controller/include/bt/symbolic_state.h](BT_Controller/include/bt/symbolic_state.h), [BT_Controller/src/bt/symbolic_state.cpp](BT_Controller/src/bt/symbolic_state.cpp).
- [BT_Controller/include/bt/execution_refs.h](BT_Controller/include/bt/execution_refs.h), [BT_Controller/src/bt/execution_refs.cpp](BT_Controller/src/bt/execution_refs.cpp).
- [BT_Controller/include/aas/transformation_resolver.h](BT_Controller/include/aas/transformation_resolver.h), [BT_Controller/src/aas/transformation_resolver.cpp](BT_Controller/src/aas/transformation_resolver.cpp).
- [BT_Controller/include/bt/bt_log.h](BT_Controller/include/bt/bt_log.h), [BT_Controller/src/bt/bt_log.cpp](BT_Controller/src/bt/bt_log.cpp).
- [Planner/aas_to_pddl_conversion/models.py](Planner/aas_to_pddl_conversion/models.py), [Planner/aas_to_pddl_conversion/up_builder.py](Planner/aas_to_pddl_conversion/up_builder.py), [Planner/bt_synthesis/xml_writer.py](Planner/bt_synthesis/xml_writer.py), [Planner/bt_synthesis/plan_converters.py](Planner/bt_synthesis/plan_converters.py).

---

## Verification

1. PR1–PR4: existing 35 C++ tests + ~58 Python tests stay green
   (two pre-existing FSAP-related Python failures in
   `test_bt_synthesis_hoisting.py` are baseline, unrelated).
2. PR5.A: `BT_Controller` boots, fetches a generated BT, ticks
   through every action node without crashing; debug log
   trace recorded as fixture.
3. PR5.B: `test_execute_action_node.cpp` passes — JSONata context
   shape locked to `{args, object_refs, now, process_aas_id,
   action_aas_path}`; representative dispense/move/occupy
   transformations produce the expected MQTT envelopes.
4. PR5.C: `test_fluent_check_node.cpp` passes — first-tick semantics
   honour `defaultValue` when present, multi-arg predicates resolve
   per-arg `aas_id`/`aas_path` on the AAS-direct path.
5. PR5.D: integration test (`BT_CONTROLLER_E2E=1`) drives one real
   `invokeOperation` against `simulated_stations` and observes the
   expected response envelope.
6. PR5.E: startup log enumerates symbolic predicates seeded vs
   assumed-false; manual inspection on the dispensing fixture matches
   the planner's `_planner_initial_state`.
7. PR5.F: removing one simulated asset before the BT starts results
   in a fail-fast log within `BT_CONTROLLER_STARTUP_TIMEOUT_MS`
   (default 5000), not a silent hang.
8. PR5.G: `cmake --build` + ctest covers the new fixtures
   without a running stack; `BT_CONTROLLER_E2E=1` opt-in target
   covers the live path.
9. PR6: divergence between planner-expected and observed sensor
   state within the verify window emits exactly one warning per
   action and does not fail the tree.
10. PR7: `BTController/<process_id>/state` topic carries the
    contracted JSON; replan trigger fires after N consecutive
    divergences (N configurable via env).
11. PR8: matrix runs green; long-soak completes 100 cycles with
    bounded resource use.

---

## Decisions

- Active scope is PR5; PR6–PR8 stay in concrete-but-deferred form
  until PR5 reveals which assumptions actually break.
- The AAS remains the digital twin of physical assets; symbolic
  planning state lives only in `SymbolicState` (PR4 decision
  preserved).
- Sensor effects are *not* eagerly applied to anything; we trust
  the next tick. PR6's verification window only emits diagnostics,
  it does not gate action SUCCESS.
- No AAS PATCH / writeback is added in PR5–PR8. The migration
  path to a knowledge-graph store (`ppr-ontology/`,
  `unified-planning/`) remains open as a future PR if and when
  cross-asset queries, persistence, or distributed control
  become real requirements.
- MQTT remains the primary command path; AAS-direct
  `invokeOperation` is a debugging fallback gated by
  `BT_CONTROLLER_AAS_DIRECT`.
- BT XML contract from PR1 is still frozen — PR5+ adds runtime
  options (`response_transformation`, predicate `defaultValue`)
  via existing AAS metadata, not via new XML attributes.

---

## Further considerations

1. The Planner emits both deterministic plans and FOND policies; PR5
   focuses on deterministic first because it is one straight-line
   path. Once that runs reliably, exercising both branches of a
   FOND policy under controlled non-determinism becomes a PR8
   matrix cell.
2. JSONata expressions live in `AASDescriptions/`; treat them as the
   integration boundary. If a transformation needs context the
   runtime doesn't expose, the right fix is §32 (extend the context)
   not per-node hacks.
3. The Operational-readiness gate (§44) interacts with the existing
   PackML state machine in `packml_runtime/`; coordinate so the
   gate does not double-wait when a station is mid-state-transition.
4. Reverse transformation (§39) intentionally avoids becoming a new
   "response schema language". JSONata + boolean coercion is the
   contract; anything richer is a planner-side change.
5. Replan plumbing (PR7) blocks on a planner-team agreement on the
   topic schema — confirm before coding.
6. `SymbolicState` remains process-local. Multi-controller sharing
   is the explicit trigger for the knowledge-graph migration; do
   not hand-roll distribution on the flat map.
7. `Planner/output/ai_planning_runs/` snapshots act as PR3+
   back-compat fixtures; phases 5.B–5.G should not break parsing
   of older runs.

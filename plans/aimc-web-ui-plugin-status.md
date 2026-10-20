# AIMC Web UI plugin — build status (2026-10-19)

State of the uncommitted AIMC plugin work in `basyx-aas-web-ui/aas-web-ui`
(`src/UserPlugins/AimcMappingConfiguration.vue`, `src/UserPlugins/aimc/**`,
new `aimc/composables/resolveAimc.ts`). Found while bringing up the main stack;
nothing in the submodule was changed.

## Symptom

`docker compose up --build` fails building `aas-web-ui` (`Dockerfile.ci`), whose
build stage runs `lint:check → vitest → type-check → vite build`. It stops at
`lint:check`, so the whole `up` aborts. The stack currently runs the last good
image, `aas-gui-ap2030:local` (built ~2026-10-05), which does **not** contain
this plugin work. Workaround used: build the other services explicitly and
`docker compose up -d --no-build`.

## 1. Lint: 29 errors, 28 auto-fixable

```
AimcMappingConfiguration.vue   80:15  vue/padding-line-between-tags
aimc/components/AimcMappingGraph.vue
   35:11, 244:11, 248:11       vue/padding-line-between-tags
  630:66                       unicorn/consistent-existence-index-check (>= 0 → !== -1)
aimc/composables/parseAimc.test.ts
  216:5                        @stylistic/padded-blocks
  221:30                       curly
aimc/composables/resolveAimc.ts
    1:72                       perfectionist/sort-named-imports
   19:7, 107:7, 111:60         unicorn/no-nested-ternary
   24..90 (13×)                curly (if without braces)
   52:22, 96:23, 113:43        unicorn/consistent-existence-index-check
  164:17                       unicorn/prefer-split-limit
  165:10                       unicorn/prefer-includes-over-repeated-comparisons
```

`pnpm exec eslint src/UserPlugins --fix` fixes all but one, which then remains
at `resolveAimc.ts:191:10` (`unicorn/prefer-includes-over-repeated-comparisons`:
replace `x === a || x === b` with `[a, b].includes(x)`).

## 2. Type-check and build-stage tests pass

Run on a copy of the working tree after `--fix`: `pnpm run type-check` exits 0;
`vitest run src/UserPlugins` passes 2 tests and skips 5. The skips are by design:
the fixture-driven suites need an AP2030-UNS checkout (`AIMC_FIXTURE_ROOT`),
which the Docker build does not have — so the image build never exercises them.

## 3. Fixture suites are broken against the current repo

With `AIMC_FIXTURE_ROOT` set to an AP2030-UNS checkout the test file fails to
load (`ENOENT`), because three of its fixtures came from the discontinued
Python management node, which no longer exists:

| parseAimc.test.ts | fixture | status |
|---|---|---|
| line 24 (presence check) | `aas-model/tests/data_aimc.json` | exists |
| line 181 | `aas-camel-dmp/management-node/tests/data/syntegon_stoppering_aimc.json` | missing |
| line 204 | `aas-camel-dmp/management-node/tests/data/events/sm_created.json` | missing |
| line 224 | `aas-camel-dmp/management-node/tests/data/syntegon_stoppering_aid.json` | missing |

Also, line 181 loads its fixture at suite-collection time outside the
`skipWithoutFixtures()` guard, so a missing file fails the whole file instead
of skipping the suite.

Candidate replacements are the DMP contract fixtures, generated from aas-model
(`aas-model/scripts/dmp_contract_fixtures.py`) and kept current:
`aas-camel-dmp/dmp.component/src/test/resources/runtime-model-contracts/stoppering/{aimc,aid}.json`
(plain submodel JSON, no Submodel-Repository event envelope — `loadFixture`
unwrapping must cope with both). There is no equivalent of `sm_created.json`
(a BaSyx event envelope); that test needs its own small inline fixture.

## 4. Model changes the plugin should expect

Made in aas-model on 2026-10-18/19 and now in the running repository:

- No protocol is a default: interfaces are `interface_mqtt`, `interface_opcua`, …
  and AIMC references name their interface. The dispensing station is
  OPC UA only (`InterfaceTemplateForOPCUA["interface_opcua"]`), so the plugin
  must not assume `interface_mqtt` when resolving Sources/Sinks.
- OPC UA PackML state mapping `OPCUA`: two sources (`State`, `ProcessQueue`),
  two sinks (`PackMLState`, `OccupationState`).
- `ObserveWeight` sets a per-source `PollingInterval` (0.1 s) on its Source.
- `OccupationState` is written as JSON array text (`"[]"`, `"[\"uuid\"]"`).

## Resolution (2026-10-19)

All four items addressed in `basyx-aas-web-ui/aas-web-ui/src/UserPlugins` (still
uncommitted). `lint:check`, full `vitest run` (1667 tests), `type-check` and
`vite build` — the `Dockerfile.ci` chain — pass locally.

- **Lint**: clean.
- **Fixtures**: `parseAimc.test.ts` now runs on the DMP contract fixtures
  (`stoppering`, `station-imaDispensing`, `projection-extensions`) incl. their
  dependency submodels; suites skip cleanly without a checkout.
- **Model alignment**: DMP extension semantic ids moved to the project
  namespace; `ExecutionSemantics.TriggerSourceIds` parsed and shown per source;
  response elements on a non-operation route are flagged (the DMP rejects them).
- **Resolver bugs found by the new fixtures**: affordance = child of the
  `td#…Affordance` group container (was resolving `actions/actions`); CCI
  Operation detected by `modelType` (semanticId ends `/Operation/2/0`); form
  `href` read from the flat `forms` collection (`hypermedia#hasTarget`).
- **Vertical centering**: layout moved to `aimc/composables/layoutAimcGraph.ts`;
  every column is centered on its lane midline using Vue Flow's measured node
  heights (second placement pass), groups kept contiguous.

## DMP status and endpoint overview (2026-10-19)

- Route index shows each route's DMP state (running / blocked / stale /
  failed / not deployed, with the category explained), polled every 15 s.
  Source: the DMP's `GET /management/status`, proxied by the UI's nginx at
  `<base>/api/dmp/status` (GET only) when `DMP_STATUS_URL` is set — set in
  `compose/docker-compose.basyx.yml`. Routes are matched by
  `sha256(aimcId)` + `sha256(idShort || "mapping_<i>")`, verified against the
  live DMP. The DMP exposes only a category, not the compile message.
- New "Endpoints" tab: every referenced affordance / AAS element with the
  routes reading and writing it.
- Graph height follows the route (280–760 px).

## Graph routing, DMP liveness, save refresh (2026-10-19)

- Supports AIMC 2.x only (2.0/2.1 IDTA templates without extensions verified
  in tests); no longer registers for AIMC 1.0.
- DMP chip on index and route header: offline / starting / degraded /
  live (proxy 502 → offline, verified).
- Every node side spaces its connection points evenly (1/(k+1)…); edges sit
  above group frames; operation replies always use the reply lane
  (passthrough node); request + reply share one centered lane.
- Saving a transformation re-reads the AIMC from the repository (it used to
  re-parse the stale page-load copy and show the old script).

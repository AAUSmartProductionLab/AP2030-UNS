# Extracting a shared `aas-model` package (Option C) — Plan

> Goal: make the **registration service (generator)** and the **management node
> (parser)** share the *same* pydantic model classes, so any model/generator
> change is forced to stay consistent with the parser — eliminating the current
> drift between the registration-service `submodel_templates/` and the management
> node's hand-written `parsers/`.
>
> Date: 2026-08-25 · Scope: cross-repo refactor of `AP2030-UNS`.

---

## 1. Context findings (why the plan is shaped this way)

Deep review confirmed the following, which materially shape the plan:

1. **Two distinct layers** exist in the registration service:
   - `src/templates/submodel_templates/` — the **model layer**: pydantic
     classes `mqtt_aid.py`, `rest_aid.py`, `aimc.py`, `variables.py`,
     `parameters.py`, `control_component_instance.py`. These subclass the
     generated IDTA templates (`aas_pydantic.submodel_templates.*`) and add
     project-specific extensions.
   - `src/templates/resource_template/` — the **resource-assembly layer**:
     `ResourceTypeAAS` composed from the models plus JSON-schema-driven
     datapoint generation (`json_schema_aid.py`), id injection
     (`id_injector.py`), write-delegation wiring. Registration-service-specific.

   Only the model layer (plus its constants) moves to the shared package.

2. **The model layer has a small, clean dependency set**: `aas_pydantic`
   (generated IDTA templates), `..constants` (project semantic IDs), one
   intra-`submodel_templates` import, and `pydantic`. No resource-layer coupling.

3. **`aas_pydantic` provides a full reverse path**
   (`convert_submodel_to_model_instance`) turning a basyx `Submodel` back into
   the pydantic model — the mechanism the management node uses to "parse with
   the same classes".

4. **The management node fetches each submodel by id** (`aas_client.py`) — a
   single BaSyx REST submodel — so the reverse path is `submodel JSON → basyx
   Submodel → convert_submodel_to_model_instance → shared pydantic model`.

5. **The management node's parser is deliberately lenient**; the resolver/
   descriptor remain the derived-state layer (delivery, valuePath, ref_path).

6. **Git/submodule structure**: `Registration_Service` and `aas-camel-dmp` are
   separate git submodules of `AP2030-UNS`. The shared package is a new **own
   git repo / submodule**.

---

## 2. Target architecture (final — aas_model is the entire data model package)

```
ap2030-uns (monorepo) / aas-model (git repo + submodule of AP2030-UNS)
├── src/aas_model/
│   ├── pyproject.toml           (self-contained: pydantic, basyx, requests)
│   ├── constants.py             (semantic IDs + infra constants)
│   ├── aas_pydantic/            (VENDORED base framework + generated IDTA templates)
│   ├── submodel_templates/      (custom models: aimc, mqtt_aid, rest_aid, variables, ...)
│   ├── resource_template/       (instantiation templates: asset, nameplate, ...)
│   ├── builder.py               (build_from_dict / build_resource_type_aas / ...)
│   ├── id_injector.py           (id injection)
│   ├── json_schema_aid.py       (JSON Schema → datapoint)
│   ├── schema_parser.py         (JSON Schema $ref/allOf parser)
│   ├── _serde.py                (AAS-JSON → shared-model parse bridge)
│   └── MQTTSchemas/             (mqtt_message_schemas submodule, vendored)
└── src/aas_pydantic/            (VENDORED — top-level `aas_pydantic` importable)
```

Consumers:
- Registration_Service: authors/instantiates via `aas_model` (no local templates).
- aas-camel-dmp/management-node: parses via `aas_model._serde` (+ validation gate).

---

## 3. Steps

### Phase 0 — prove the reverse path ✅ DONE (gate passed)
Reverse-converted the real BaSyx REST `syntegon_stoppering_aimc.json` /
`_aid.json` into `Aimc` / `MqttAssetInterfacesDescription` via
`convert_submodel_to_model_instance`. AIMC (5 mappings, Transformation blob) and
AID (MQTT interface + actions `Halt/Occupy/Release/Stoppering` + props) both
round-trip. Extension classes resolve correctly. Gate passed — full plan viable.

### Phase 1 — create `aas-model` package ✅ DONE
- New repo `aas-model` (`git init`), `src/aas_model/` with `pyproject.toml`
  (`aas_pydantic`, `pydantic`, `basyx-python-sdk`).
- Moved `constants.py` + `submodel_templates/*`; rewrote relative imports to
  `aas_model.*`.
- Added `_serde.py` (parse API) and `tests/test_serde.py` (round-trip, 3 pass).
- Committed (2 commits).

### Phase 2 — rewire `Registration_Service` onto `aas-model` ✅ DONE (35 tests green)
- `src/templates/submodel_templates/*` converted to **re-export shims** of
  `aas_model.submodel_templates.*`; `__init__.py` re-exports the shared classes.
- `tests/conftest.py` exposes the sibling `aas-model/src`.
- Documented the dep in `requirements.txt` (git URL pending remote).
- Full registration-service suite: **35 passed**.

### Phase 3 — management node parses via the shared models ✅ DONE (71 tests green)
- Added `aas_model` to `pyproject.toml`; `tests/conftest.py` exposes it.
- New `parsers/validate.py`: reverse-parses each incoming BaSyx AID/AIMC submodel
  through the shared models — **Strict** by default (`DMP_MGMT_STRICT_MODELS`,
  raise on mismatch → generator change breaks the parser = lockstep), with a
  lenient fallback (log + continue, never drop).
- `parse_aid` / `parse_aimc` call the gate first, then the lenient translation.
- Resolver/descriptor unchanged (they consume the lightweight dataclasses the
  tests build directly).
- New `tests/test_shared_model_gate.py` (4 tests). Full suite: **71 passed**.

### Phase 4 — consistency/CI ✅ (done + expanded scope)
- `aas-model/tests/test_schema_lockstep.py`: golden snapshot of
  `model_json_schema()`; any model change breaks CI. **Done**.
- **Submodule registered:** `aas-model` is a git submodule of `AP2030-UNS`
  (`AP2030-UNS/aas-model`), pushed to
  `https://github.com/tristan-schwoerer/aas-model.git`.

### Phase 5 — aas_model = the entire data-model package ✅ (done, ADR-016 expanded)
Per user direction, `aas_model` now owns the **whole** data model:
- Vendored `aas_pydantic` (base framework + generated IDTA templates) at
  `src/aas_pydantic` — `from aas_pydantic import ...` still resolves, now via
  the aas-model repo.
- Moved `resource_template/`, `builder.py`, `id_injector.py`, `json_schema_aid.py`,
  `schema_parser.py` into `aas_model`.
- Vendored `MQTTSchemas` (`mqtt_message_schemas`) into `aas-model/MQTTSchemas`;
  fixed `SchemaParser._default_schema_dir` to find it (the local JSON schemas
  carry fields the remote github.io ones lack, e.g. `commandResponse.Outcome`).
- **Registration_Service**: removed `src/templates/`, `src/schema_parser.py`,
  `third_party/aas_pydantic`, and the `MQTTSchemas` submodule; all authoring now
  goes through `aas_model` (config_parser, registration_service, scripts, tests
  re-pointed). Depends on `aas-model` only for the data model.
- Public `aas_model` API: models + `build_from_dict`/`build_resource_type_aas`/
  `generate_station_template`/`merge_instance_config`/`inject_ids` + `_serde`.

## 4a. What moved vs stays (final state)

| Artifact | Destination |
|---|---|
| `aas_pydantic` (full package) | `aas-model/src/aas_pydantic` (vendored) |
| custom `submodel_templates/` | `aas_model/submodel_templates/` |
| `resource_template/` | `aas_model/resource_template/` |
| `builder.py`, `id_injector.py`, `json_schema_aid.py`, `schema_parser.py` | `aas_model/` |
| `constants.py` | `aas_model/constants.py` |
| `MQTTSchemas` (mqtt_message_schemas) | `aas-model/MQTTSchemas` (submodule) |
| `src/templates/`, `src/schema_parser.py`, `third_party/aas_pydantic`, `MQTTSchemas` (Registration_Service) | removed |
| `management_node/parsers/` + `validate.py` | **re-authored**: thin parse → shared pydantic models (dataclasses removed) |
| **`submodel-templates/` submodule + `scripts/idta_generate.py`** | **added to aas-model** — the regeneration tooling so the vendored IDTA pydantic classes stay current with the IDTA templates (`scripts/README.md` documents the named-field/container style caveat) |
| **`aas_model/testing.py`** | **added** — compact pydantic AID/AIMC builders for tests/tools |

### Phase 6 — parser dataclasses replaced by pydantic models ✅ (done)
- `parsers/aid.py` / `parsers/aimc.py` are now **thin wrappers** returning the
  shared pydantic models (`parse_aid -> MqttAssetInterfacesDescription`,
  `parse_aimc -> Aimc`). All parser dataclasses (`AidModel`/`AidInterface`/
  `AidDataPoint`/`AidForm`/`MqttForm`/`AimcModel`/`AimcSource`/...) removed.
- `resolver.py` navigates the pydantic models directly (AIMC `.Sources.value`,
  `.SinkId.value`, reference `.key[].value`; AID `EndpointMetadata.base`,
  `InteractionMetadata.{properties,actions}.property_name`, generic
  `InterfaceTemplateFor*` dicts). `Resolved*` dataclasses stay (derived state:
  protocol, delivery, value_path) — not a model re-implementation. `reference_values()`
  helper exposes reference path keys to the descriptor.
- `aas_model/testing.py` added: compact builders (mqtt_interface, rest_interface,
  opcua_interface, http_interface, modbus_interface, aimc_mapping, ...) so tests
  construct shared pydantic models tersely.
- Management-node tests converted to builders/parse; 70 pass. The OpCUA
  `op`-based & `InteractionMetadata.events` paths are no longer representable in
  the generated AID (its `forms` lacks `op` and `events` has no `property_name`),
  so those cases are covered by `observable`/`subprotocol` instead.



---

## 4. What moved vs stays

| Artifact | Destination |
|---|---|
| `src/templates/submodel_templates/*` (models) | `aas_model/submodel_templates/` (moved) |
| `src/templates/constants.py` | `aas_model/constants.py` (moved) |
| `aas_pydantic` | stays vendored; dependency of `aas_model` |
| `resource_template/`, `json_schema_aid.py`, `id_injector.py`, `builder.py` | stay in Registration_Service (shim → shared models) |
| `management_node/parsers/` | shared-model validation gate added; lenient translation kept |
| `management_node/resolver.py`, `descriptor.py` | unchanged (derived-state layer) |

---

## 5. Decisions taken

1. **Runtime strict path — YES** (shared-model validation gate in the
   management node), with `DMP_MGMT_STRICT_MODELS=0` lenient escape.
2. **Distribution — git submodule pattern**, matching `aas_pydantic`.
   *(Submodule registration pending remote creation — user step.)*
3. **MQTT-only scope — honored**; all model files moved as-is, no new
   protocol coverage added by this refactor.
4. **Callers re-pointed** via re-export shims + conftest path wiring.

---

## 6. Remaining (needs the user/remote)

1. **Create/publish the `aas-model` remote repo**, then register it as a
   submodule in both consumers (exact commands in the next step), or point the
   Docker/pyproject deps at the published package.
2. **Finalize Docker wiring** to install `aas_model` in both images.
3. **Wire aas-model into CI** for `Registration_Service` and `aas-camel-dmp`
   (the golden-schema test + shared-model gate become the enforcement).

---

## 7. Success criteria (status)

| Criterion | Status |
|---|---|
| `aas_model` package exists, git repo | ✅ |
| consumed by both repos | ✅ (local path; submodule pending remote) |
| generator change → parser CI break | ✅ (schema lockstep + shared-model gate) |
| registration-service AAS JSON unchanged | ✅ (35 tests incl. generation pass) |
| management-node pytest green | ✅ (71) |
| aas-model pytest green | ✅ (4) |

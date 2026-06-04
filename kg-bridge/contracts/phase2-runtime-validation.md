# Phase 2 Runtime Validation and Structural Reasoning

This document captures the Phase 2 runtime decisions implemented for the KG + planner integration.

## Goals

- Enforce fail-fast SHACL validation before planning when the gate is active.
- Keep structural enrichment deterministic and controllable.
- Allow retiring superseded structural materialization rules when structural reasoning mode is enabled.

## Planner SHACL Gate

The planner now supports a pre-planning SHACL gate:

- Module: `Planner/step0_validation/shacl_gate.py`
- Invocation point: `Planner/production_planner_service.py` (Step 0, before context collection)

Behavior:

- Fetches structural ABox data from `PLANNER_SHACL_ABOX_GRAPH` via SPARQL CONSTRUCT.
- Excludes `apex:smElementValue` payload mirroring data from validation scope.
- Fetches TBox from `PLANNER_SHACL_TBOX_GRAPH` and shapes from `PLANNER_SHACL_SHAPES_GRAPH`.
- Runs `pyshacl` with configurable inference (`PLANNER_SHACL_INFERENCE`, default `rdfs`).
- Aborts planning on non-conformance or SHACL runtime errors.

Gate mode selection:

- `PLANNER_SHACL_GATE_ENABLED=true|false|auto`.
- `auto` probes the SHACL graph endpoint and enables the gate only when a non-empty SHACL graph is reachable.

## Structural Reasoning and Materialization Retirement

`kg-bridge` now exposes explicit toggles:

- `KG_ENABLE_STRUCTURAL_REASONING`
- `KG_DISABLE_LEGACY_STRUCTURAL_MATERIALIZATION`
- `KG_DISABLED_MATERIALIZATION_RULE_PREFIXES`

When both of the first two are `true`, legacy rule prefixes are disabled by default:

- `010-`
- `020-`
- `030-`

This preserves backward compatibility by default while allowing Phase 2 migration without removing old files.

## Ingestion Hardening

`kg-bridge/conversion/projection.py` now includes Phase 2 ingestion hardening controls:

- Shell-kind inference prioritizes explicit metadata (`category`, `assetType`, `globalAssetId`) before keyword fallback.
- Keyword fallback uses boundary-aware matching to reduce false positives (for example `production*` no longer matches `product`).
- Submodel semanticId-to-class mapping is externalized to `contracts/submodel-semantic-id-map.phase2.json`.
- Optional runtime override: `KG_SUBMODEL_SEMANTIC_ID_MAP_PATH`.

## Phase 3 Semantic Binding Shift

- Dynamic predicate strategy views now require semanticId bindings (`apex:smElementSemanticId`) and no longer use path-regex fallback.
- Canonical APEX semantic variable IDs are now expected to be authored at source in Resource AAS YAML configs and emitted by Registration Service generation.
- Registration Service variable generation now propagates variable semantic IDs to mirrored leaf Properties so runtime predicate views consume semantically tagged scalar values directly.

Ontology disjointness hardening:

- `arsox:ProductAssetAdministrationShell owl:disjointWith arsox:ProcessAssetAdministrationShell`.

## SHACL Constraints Added in APEX

`kg-bridge/Ontology/APEX/apex-shacl.ttl` now includes Phase 2 structural constraints:

- `apex:ResourceLocationShape`
- `apex:PredicateDefinitionShape`
- `apex:ActionSkillReferenceShape`
- `apex:CppmBelongsToExactlyOneCppsShape`

These complement existing predicate argument binding constraints and enforce structural consistency relevant to planning.

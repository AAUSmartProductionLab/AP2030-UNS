# kg-bridge

## Local Development

Install runtime + test dependencies and run the conversion-layer tests:

```bash
pip install -r kg-bridge/requirements.txt -r kg-bridge/requirements-dev.txt
PYTHONPATH=kg-bridge pytest kg-bridge/tests -v
```

## Inference Split

The bridge now separates inference into two categories:

- Structural, low-churn enrichment is materialized at event time from [sparql/materialization](sparql/materialization).
- Dynamic, high-frequency state predicates are evaluated on demand as SPARQL CONSTRUCT views from [sparql/views](sparql/views).

Dynamic runtime views currently include:

- `resource-at.rq`
- `product-at.rq`
- `occupied.rq`
- `operational.rq`
- `in-range.rq`

## Named Graphs

- `urn:kg:tbox`: ontology vocabulary and axioms (AAS metamodel, CSS, ARSO, APEX)
- `urn:kg:abox`: instance data from AAS events and structural materialization outputs
- `urn:kg:shacl`: SHACL shapes used for validation workflows

By default, event projection and materialization write to `urn:kg:abox`. Dynamic view queries include `FROM <urn:kg:tbox>` and `FROM <urn:kg:abox>` so they can resolve both schema and instance data.

## Phase 0 Contract Artifacts

The KG contract baseline for roadmap Phase 0 is versioned under `contracts/`:

- `contracts/kg-contract-phase0.md`
- `contracts/predicate-dispatch.phase0.yaml`
- `contracts/semantic-id-contract.phase0.yaml`
- `contracts/submodel-semantic-id-map.phase2.json`
- `contracts/capability-taxonomy.phase0.yaml`
- `contracts/phase1-ontology-layout.md`
- `contracts/phase2-runtime-validation.md`

## Phase 1 Ontology Layout

APEX ontology now follows a core + extension layout:

- Core module index: `Ontology/APEX/README.md`
- Extension governance: `Ontology/APEX/extensions/README.md`
- Main use-case capability extension: `Ontology/APEX/extensions/apex-extension-main-capabilities.ttl`

## Phase 2 Runtime Validation and Reasoning Controls

Planner-side SHACL fail-fast gate and structural migration toggles are now available:

- `PLANNER_SHACL_GATE_ENABLED=true|false|auto` (default: `auto` in planner compose)
- `PLANNER_SHACL_QUERY_ENDPOINT`
- `PLANNER_SHACL_ABOX_GRAPH`
- `PLANNER_SHACL_TBOX_GRAPH`
- `PLANNER_SHACL_SHAPES_GRAPH`
- `PLANNER_SHACL_TIMEOUT_SECONDS`
- `PLANNER_SHACL_INFERENCE`
- `KG_ENABLE_STRUCTURAL_REASONING`
- `KG_DISABLE_LEGACY_STRUCTURAL_MATERIALIZATION`
- `KG_DISABLED_MATERIALIZATION_RULE_PREFIXES`
- `KG_SUBMODEL_SEMANTIC_ID_MAP_PATH` (optional override for Submodel semanticId-to-class mapping)

Details and policy notes are recorded in `contracts/phase2-runtime-validation.md`.

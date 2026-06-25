# Generation pipeline v2 — CSSx_AAS + IDTA semanticIds + unified pyshacl

This folder is the v2 (default) generation pipeline. It runs alongside v1
(`generation/AAS_generation/` + `generation/pipeline.py`); a flag in
`generation/config.yaml` switches between them at request time:

```yaml
validation:
  profile: v2   # default; "v1" falls back to legacy
```

Nothing in v1 was rewritten. The single touch outside v2 was a guard around
`generation/AAS_generation/__init__.py:1` (`from .aas_generation import main`)
because that import already references a missing module — wrapping it in
`try/except` lets the rest of the v1 package import.

## Layout

```
generation/v2/
├── pipeline_v2.py             retry loop; mirror of generation/pipeline.py
├── validator_v2.py            single pyshacl call (AAS shapes + CSSx shapes)
├── AAS_builder_v2.py          thin wrapper, picks v2 AASGenerator
└── AAS_generation_v2/         basyx-SDK builder package, subclasses v1
    ├── core/
    │   ├── semantic_ids.py    IDTA-aligned IDs (the one source of truth)
    │   ├── element_factory.py guard: required SMEs MUST carry semantic_id
    │   └── aas_builder.py     re-export (no shell-level changes yet)
    ├── submodels/
    │   ├── nameplate_builder.py            adds semantic_id to mandatory SMEs
    │   ├── asset_interfaces_builder.py     adds semantic_id to EndpointMetadata
    │   └── *.py                            re-exports — the v2 SemanticIdFactory
    │                                        injects the corrected URLs via inheritance
    └── cli/generate_aas.py    AASGenerator subclass that wires v2 builders
```

## Companion files outside v2

| Path | Purpose |
|---|---|
| `tools/aas_to_rdf.py` | Generic AAS-JSON → RDF serializer aligned to `CSSx_AAS.ttl`. Uses semanticId for typing; falls back to bare AAS class on unknown IDs. |
| `tools/generate_shapes_v2.py` | One-shot script that re-derives `shacl/generated_v2/shapes.generated.shacl.ttl` from `CSSx_AAS.ttl`. |
| `ontology/CSSx_AAS.ttl` | Domain ontology imported by validator_v2 (transitively pulls AAS v3.1). |
| `ontology/aas-rdf-ontology.ttl` | Local copy of AAS v3.1 OWL — resolves the `owl:imports` offline. |
| `ontology/aas-shacl-schema.ttl` | AAS v3.1 SHACL shapes — replaces the basyx metamodel pre-check. |
| `ontology/catalog-v001.xml` | Catalog mapping `https://admin-shell.io/aas/3/1/` → local file. |
| `shacl/generated_v2/shapes.generated.shacl.ttl` | Auto-derived CSSx shapes (regenerate with `tools/generate_shapes_v2.py`). |
| `api/context_v2/` | LLM context for `json` mode — preamble + nameplate template fully list IDTA semanticIds. |

## How v2 differs from v1

1. **Semantic IDs corrected** — `core/semantic_ids.py` overrides the broken
   `https://admin-shell.io/IDTA 02006-3-0` (had a space) and the non-IDTA
   `smartfactory.de` URLs for Capabilities/Skills.
2. **Mandatory SME semanticIds added** — `ManufacturerName`,
   `ManufacturerProductDesignation`, `ContactInformation`,
   `OrderCodeOfManufacturer`, `EndpointMetadata` now carry IDTA IRIs that
   `aas_to_rdf.py` recognises and types as `cssx:ManufacturerNameMLP`,
   `cssx:ContactInformationSMC`, etc.
3. **Single pyshacl validation** — no more basyx metamodel pre-check. AAS
   structural shapes (`aas-shacl-schema.ttl`) and CSSx domain shapes
   (`shapes.generated.shacl.ttl`) load into one shapes graph, run in one call.
4. **Issue partitioning** — `validator_v2._is_aas_shape` classifies each
   ValidationResult as "metamodel" if its `sh:sourceShape` or `sh:resultPath`
   sits in the AAS namespace, otherwise "ontology". Drives the existing
   UI message-routing without UI changes.

## Verified end-to-end (smoke tests)

Unit-level (handcrafted AAS):
- Shell typed as `aas:AssetAdministrationShell` ✓
- Submodel typed as both `aas:Submodel` AND `cssx:DigitalNameplateSubmodel` ✓
- `cssx:hasDigitalNameplateSubmodel` typed link ✓
- `cssx:representsResource` ↔ `css:Resource` ✓
- `aas:Submodel/submodelElements` containment ✓
- `cssx:ManufacturerNameMLP`, `cssx:OrderCodeProperty` SME typing ✓
- Unknown semanticId → bare `aas:Property` (no false `cssx:*` typing) ✓

Integration (real `aas_configs/imaDispensing.json` profile through v2 builder):
- Builder emits IDTA-aligned semanticIds on all mandatory Nameplate SMEs ✓
- `aas_to_rdf` produces a parseable RDF graph (no crash) ✓
- `validator_v2` runs without error ✓
- 124 SHACL violations reported, all classified as metamodel ✓
- All ontology shapes (cssx:DigitalNameplateSubmodel constraints etc.) pass ✓

## Known serializer gaps (drive count down iteratively)

The 124 metamodel violations are real and break down as:
- **92×** `Value does not have class aas:Reference` — `aas_to_rdf` emits
  Reference targets as plain string literals; AAS shapes expect a proper
  `aas:Reference` resource with `aas:type` and `aas:keys`. Affects
  `RelationshipElement/first`, `RelationshipElement/second`,
  `ReferenceElement/value`, AAS shell submodel refs, semantic-id reference
  structures.
- **22×** `Value is not Literal with datatype xsd:string` — Property values
  emit untyped literals; should carry `^^xsd:string` (or the matching
  xsd type from `valueType`).
- **4×** `Value does not have class aas:EntityType` / `aas:LangStringTextType`
  — `Entity/entityType` and `MultiLanguageProperty/value` need typed objects
  rather than literals/lang-tagged strings.
- **2×** `Less than 1 values on <…>` — missing properties on shell + submodel
  (likely `aas:AssetAdministrationShell/assetInformation` and
  `aas:Submodel/kind`).

These do not block the pipeline; v2 produces correct semantic typing today.
Closing them improves AAS-spec conformance — a clear unit of follow-up work.

## Manual SPARQL rules

The four constraints noted at the bottom of `CSSx_AAS.ttl` (SkillInterfaceRef
referent, RealizedByRef referent, SelfManagedEntity → globalAssetId, ArcheType
enum) are not yet ported to `shacl/manual_v2/`. Out of scope for v2's first
landing.

## Packaging for publication

Run `bash package_v2.sh [DEST]` from the repo root. The script gathers all v2
components plus the ontology and UI into a sibling folder, then mechanically
rewrites import paths (`generation.v2.` → `generation.`,
`AAS_generation_v2` → `AAS_generation`, `*V2` class names → bare). The result
is a **starter** scaffold — the rewrite will collide with the v1-subclassing
strategy in a few spots (e.g. v2 element_factory inherits from v1's; after the
rename the inheritance becomes self-referential). Treat the output as a
candidate tree to inspect by hand before `git init`. Plan for ~30 min of cleanup
on the first run.

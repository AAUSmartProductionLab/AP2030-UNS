# Web UI Handoff (TypeScript Frontend + Python Backend)

This document is a handoff for building a web UI around the current AAS generation + validation stack.

---

## 1) Objective

Build a UI that supports the workflow:

1. AAS UI editing
2. AAS YAML profile creation/update
3. AAS JSON generation
4. SHACL validation

with **live validation/guidance during editing** to make iteration faster and reduce invalid configs.

---

## 2) Current Repository Map

### Ontology and Shapes

- `ontology/CSS-Ontology.ttl`
	- Base CSS ontology.
- `ontology/CSSx.ttl`
	- CSS extension ontology (imports modular files in `ontology/`).
- `ontology/`
	- Modular CSSx ontology files.
- `shacl/resourceaas-core.shacl.ttl`
	- Mandatory submodel checks.
- `shacl/resourceaas-dependencies.shacl.ttl`
	- Dependency/link checks.
- `shacl/resourceaas-semantics.shacl.ttl`
	- Semantic trace checks (URI policy currently aligned to `smartproductionlab.aau.dk`).

### Generation (YAML -> AAS JSON)

- `generation/cli/generate_aas.py`
	- Main generator entrypoint.
	- Contains ontology-guided prebuild enrichment (`_ensure_ontology_guidance`, `_apply_ontology_guidance`).
- `generation/core/`
	- Builder/factory helpers (`aas_builder.py`, `element_factory.py`, `schema_handler.py`, `semantic_ids.py`).
- `generation/submodels/`
	- Submodel builders:
		- `nameplate_builder.py`
		- `asset_interfaces_builder.py`
		- `variables_builder.py`
		- `parameters_builder.py`
		- `hierarchical_structures_builder.py`
		- `capabilities_builder.py`
		- `skills_builder.py`
		- `process_submodels_builder.py`
- `generation/services/unified_service.py`
	- Registration/deployment-oriented service integration logic.

### Validation

- `tools/run_resourceaas_validation.py`
	- Main validation entrypoint.
	- Converts JSON -> RDF and runs SHACL using pySHACL.
- `tools/mock_resourceaas_to_rdf.py`
	- AAS JSON -> RDF mapping (semantic trace extraction, capability/skill linking).
- `tools/run_resourceaas_test_matrix.py`
	- Matrix regression runner.
- `validation-output/`
	- Generated RDF and SHACL reports.

### Data and Samples

- `imaDispensing.yaml`
- `imaLoadingSystem.yaml`
- `resourceaas-cases/valid_resourceaas.json`
- `resourceaas-cases/*.json` negative cases
- `resourceaas-cases/valid_resourceaas.yaml`
	- Lossless YAML representation of `valid_resourceaas.json`.
- `resourceaas-cases/valid_resourceaas.generator-profile.yaml`
	- Compact generator-profile YAML (not lossless).

### Utility Conversion Script

- `tools/convert_resourceaas_json_to_yaml.py`
	- Converts a full ResourceAAS JSON to the compact generator-oriented YAML profile.

---

## 3) Canonical Runtime Flow

### Flow

`AAS UI -> YAML profile -> generate JSON -> validate JSON`

### Commands (backend calls)

Generate:

```bash
python -m generation.cli.generate_aas --config <input.yaml> --output <output_dir> --no-validate
```

Validate:

```bash
python tools/run_resourceaas_validation.py --input <generated.json> --generated-rdf <out.ttl> --report <report.ttl>
```

Matrix regression:

```bash
python tools/run_resourceaas_test_matrix.py --cases-dir resourceaas-cases
```

---

## 4) Live Guidance Requirement (Important)

The UI should not only run validation at the end. It should use guidance during editing.

Current guidance is already implemented in `generation/cli/generate_aas.py` and can be surfaced in UI.

### Existing guidance behavior

- Canonicalizes `AssetInterfacesDescription` -> `AID`.
- Creates minimal `AID` scaffold when Skills/OperationalData/Parameters exist without AID.
- Auto-creates Skills from AID actions when missing.
- Fills missing `interface` and `semantic_id` in Skills.
- Auto-creates Capabilities from Skills when missing.
- Fills missing `semantic_id` / `realizedBy` in Capabilities.

### UI expectation

- Run guidance on each meaningful edit (debounced).
- Show guidance actions as explicit suggestions/diffs.
- Allow apply-all / apply-selected actions.
- Keep YAML editor and structured-form editor synchronized.

---

## 5) Required Architecture

## Frontend

- TypeScript app (recommended React + Vite).
- Two editing modes:
	- Structured form for common fields/submodels.
	- Raw YAML editor.
- Live panes:
	- Generated JSON preview.
	- Validation status + issue list.
	- Guidance panel (auto-fix suggestions).

## Backend

- Python service layer wrapping existing scripts (FastAPI recommended).
- Backend responsibilities:
	- Parse/validate YAML syntax.
	- Run ontology guidance.
	- Run generation.
	- Run SHACL validation.
	- Return normalized machine-readable diagnostics.

## Frontend-backend contract (minimum endpoints)

- `POST /api/guidance/preview`
	- Input: YAML text
	- Output: suggested changes + normalized YAML snapshot
- `POST /api/generate`
	- Input: YAML text
	- Output: generated JSON + generation messages
- `POST /api/validate`
	- Input: JSON text or file id
	- Output: conforms flag + SHACL issues + report text/TTL path
- `POST /api/pipeline/run`
	- Input: YAML text
	- Output: guidance + generated JSON + validation result in one response

---

## 6) Notes for the Next Agent

1. Distinguish **lossless YAML** vs **generator profile YAML** clearly in UI.
2. Keep semantic URI policy consistent with SHACL (`smartproductionlab.aau.dk`).
3. Preserve compatibility with existing sample files and matrix cases.
4. Prefer deterministic backend responses (stable ordering of messages/diagnostics).
5. Expose raw report download (`.ttl`) for debugging/audit.

---

## 7) Recommended UX Sequence

1. User edits YAML/form.
2. UI calls `/guidance/preview` (debounced ~300–600 ms).
3. UI displays suggestions and allows applying fixes.
4. On demand or autosave, call `/generate`.
5. Call `/validate` and render errors mapped back to YAML paths where possible.

This gives the “guided editing” behavior needed for faster authoring and fewer late-stage failures.


# v2 architecture — every file, every input, every connection

A reference for the v2 generation + validation pipeline. Read this when you
need to know what a file does, what calls it, what it returns, or where to
plug in.

Read [README.md](README.md) first for the 30-second overview. This document
is the deep dive.

---

## 1. Bird's-eye data flow

```
                           ┌─────────────────────────────────────────────────┐
       Browser  ───POST───▶│  FastAPI  (api/main.py + routers)               │
       (Vue/React           │  ───┐                                          │
       UI in ui/)           │     │   /api/generate-aas    (SSE stream)      │
                            │     │   /api/validate        (live edits)      │
                            │     │   /api/generation-config                 │
                            └─────┼──────────────────────────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │  generation/pipeline router │   _select_pipeline(cfg)
                    │  (in api/routers/           │   reads validation.profile
                    │   generate_aas.py)          │
                    └──────┬───────────────┬──────┘
                           │               │
                ┌──────────▼──────┐   ┌────▼─────────────────────┐
                │ pipeline_v2     │   │ pipeline (v1, fallback)  │
                │ (default)       │   │                          │
                └──────┬──────────┘   └──────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────────────┐
        │ Per-attempt loop:                            │
        │  1. call_llm        → raw text               │
        │  2. profile parse   → profile dict           │
        │  3. AAS_builder_v2  → full AAS JSON          │
        │     (uses AAS_generation_v2 + basyx SDK)     │
        │  4. validator_v2    → conforms + issues      │
        │     a. tools/aas_to_rdf.py    → RDF graph    │
        │     b. ontology/CSSx_AAS.ttl  loaded         │
        │        + transitively imports                │
        │          ontology/aas-rdf-ontology.ttl       │
        │     c. shapes:                               │
        │        ontology/aas-shacl-schema.ttl         │
        │        + shacl/generated_v2/...shacl.ttl     │
        │     d. pyshacl.validate (one call)           │
        │  5. retry on violations (build_retry_message)│
        └──────────────────────────────────────────────┘
                       │
                       ▼
                  SSE stream → UI
```

Two upstream concerns drive the design:

1. **One source of truth for semantic IDs.** A submodel/SME is typed by its
   `semanticId`, not by its `idShort`. The same constant string is used in
   the builder (to stamp it onto the JSON) and in the serializer (to map
   it to a `cssx:` subclass).
2. **One pyshacl call covers metamodel + domain.** No separate basyx
   metamodel pre-check. The combined shapes graph (AAS shapes + auto-derived
   CSSx shapes) is loaded once, validated once, partitioned at report time.

---

## 2. Ontology layer (the rules)

### `ontology/CSSx_AAS.ttl` — domain ontology
- **Inputs:** none (hand-authored, source).
- **Outputs:** OWL classes/restrictions read by `tools/generate_shapes_v2.py`
  to derive SHACL shapes; loaded by `validator_v2` as ontology context.
- **Imports:** `<https://admin-shell.io/aas/3/1/>` (resolved via the catalog
  to the local `aas-rdf-ontology.ttl`).
- **What it declares:** every CSSx submodel/SME class as a subclass of the
  appropriate `aas:` class, OWL restrictions for cardinality / mandatory
  child elements / cross-submodel dependencies, and the `cssx:has*Submodel`
  typed-link properties used for cross-SM constraints.

### `ontology/aas-rdf-ontology.ttl` — official AAS v3.1 OWL
- **Inputs:** none (vendored from admin-shell.io).
- **Outputs:** loaded by `tools/generate_shapes_v2.py` and `validator_v2`
  via `owl:imports` resolution from `CSSx_AAS.ttl`.
- **What it declares:** every AAS metamodel class (`Submodel`, `Property`,
  `MultiLanguageProperty`, `Entity`, `Reference`, …) and the property IRIs
  the serializer emits (`aas:Submodel/submodelElements`, `aas:Property/value`,
  `aas:HasSemantics/semanticId`, `aas:Property/valueType`, …).

### `ontology/aas-shacl-schema.ttl` — official AAS v3.1 SHACL
- **Inputs:** none (vendored).
- **Outputs:** loaded by `validator_v2` as half of the combined shapes graph.
- **What it does:** structural validation of AAS instances — language code
  format, idShort regex, mandatory cardinalities, valueType correctness,
  Reference structure (`aas:type`, `aas:keys`), etc. Replaces the basyx
  metamodel pre-check.

### `ontology/owl2shacl/owl2sh-semi-closed.ttl` — derivation rules
- **Inputs:** none (vendored).
- **Outputs:** SHACL-AF rules graph used by `tools/generate_shapes_v2.py`.
- **What it does:** transforms each OWL restriction in `CSSx_AAS.ttl` into a
  SHACL constraint. "Semi-closed" means: declared properties get strict
  cardinality, undeclared ones are tolerated (so vendor-specific extra fields
  don't trip the validator).

### `ontology/catalog-v001.xml` — URI → file map
- **Inputs:** none.
- **Outputs:** consulted by `tools/generate_shapes_v2.py` and `validator_v2`
  before any network attempt.
- **Entries:** `https://admin-shell.io/aas/3/1/` → `aas-rdf-ontology.ttl`,
  `http://www.w3id.org/hsu-aut/css` → `CSS-Ontology.ttl`. Add a line here
  whenever a new ontology is introduced with a network URI you'd otherwise
  hit at validation time.

---

## 3. Tools layer (the executables)

### `tools/aas_to_rdf.py` — full AAS JSON → RDF serializer
- **Public API:**
  - `serialize(document: dict) -> rdflib.Graph`
  - `convert(aas_json_path: Path, output_ttl_path: Path) -> None`
  - CLI: `python tools/aas_to_rdf.py --input X.json --output Y.ttl`
- **Imports from v2:** `generation.v2.AAS_generation_v2.core.semantic_ids`
  (string constants for submodel + SME semanticIds).
- **Lookup tables:**
  - `_AAS_CLASS_BY_MODEL_TYPE` — modelType string → AAS class IRI.
  - `SUBMODEL_TYPE_BY_SEMANTIC_ID` — IDTA URI → CSSx submodel subclass.
  - `SME_TYPE_BY_SEMANTIC_ID` — IDTA URI → CSSx SME subclass.
  - `_TYPED_LINK_BY_SUBTYPE` — CSSx submodel subclass → `cssx:has…Submodel`
    property on the AAS shell. These typed links drive the OWL cross-SM
    cardinality constraints in `CSSx_AAS.ttl`.
- **Walker:** one recursive `_walk_element` that dispatches on
  `modelType`. For every node it emits the AAS class type plus, when the
  semanticId is recognised, the matching `cssx:` subclass — so SHACL shapes
  on either type fire automatically. Unknown semanticId → only bare AAS
  type (graceful degradation for third-party AAS).
- **Containment via official AAS property IRIs** (not custom predicates):
  `aas:Submodel/submodelElements`, `aas:SubmodelElementCollection/value`,
  `aas:Entity/statements`, etc.
- **Resource ↔ shell link:** every AAS shell gets a `cssx:representsResource`
  triple to a `css:Resource` minted from `assetInformation.globalAssetId`,
  which satisfies the cross-SM OWL restrictions.

### `tools/generate_shapes_v2.py` — SHACL regeneration (offline)
- **Run when:** `CSSx_AAS.ttl` changes.
- **Inputs:** `ontology/CSSx_AAS.ttl`, `ontology/aas-rdf-ontology.ttl`
  (resolved via the catalog), `ontology/owl2shacl/owl2sh-semi-closed.ttl`.
- **Output:** `shacl/generated_v2/shapes.generated.shacl.ttl`.
- **Mechanism:** loads the union ontology graph (CSSx + AAS), applies the
  semi-closed ruleset via `pyshacl.shacl_rules`, serializes the resulting
  shapes graph to Turtle. Last run produced ~4,200 triples.

### `tools/generate_shapes_from_ontology.py` — v1 SHACL regeneration
- Reused as a library by `generate_shapes_v2.py` (`import_uri_to_local_path`,
  `run_owl2shacl_rules`). Standalone use targets the v1 ontology stack.

---

## 4. Generation layer

### Shared (used by both v1 and v2)

| File | Purpose | Inputs | Outputs |
|---|---|---|---|
| [generation/config.py](../config.py) | Loads `config.yaml` into a `Config` dataclass; resolves all paths and the `validation_profile`. | `generation/config.yaml`. | `Config` instance; `load_validation_paths()` helper. |
| [generation/config.yaml](../config.yaml) | User-edited config: provider, asset, submodels, options, model lists, paths, **`validation.profile`**. | — | YAML loaded by `config.py`. |
| [generation/profile_structure.py](../profile_structure.py) | Profile-shape helpers — pruning by selected submodels, AID↔AssetInterfacesDescription aliasing, defaulting. | Raw profile dict. | Normalized profile dict consumed by `AAS_builder*`. |
| [generation/json_description_generation.py](../json_description_generation.py) | Builds the example profile + per-field semantic guide JSON shown to the LLM in `json-description` mode; parses LLM output back into a profile dict. | `Config`, `aas_configs/*.json` template. | Strings (example, guide, retry msgs); dicts (parsed profile). |
| [generation/context_loader.py](../context_loader.py) | Concatenates `cfg.context_dir/00-preamble.md` + `shacl-rules.md` + (optional) `valid-example.json` + per-submodel `submodels/<name>.md`. | `cfg.context_dir`. | Single Markdown string fed to the LLM as system instruction. |
| [generation/rag_loader.py](../rag_loader.py) | Loads `generation/RAG/*` (PDFs + JSONs) into Gemini parts and/or text blocks. | `generation/RAG/`. | `(gemini_parts, text_blocks)`. |
| [generation/llm_client.py](../llm_client.py) | Provider-agnostic LLM call: cycles through model list on rate limit, returns first successful response. | provider, api_key, models list, prompt parts. | `(raw_text, next_model_idx)`. |
| [generation/prompt_builder.py](../prompt_builder.py) | Composes `system_instruction` from preamble+context+RAG, `user_prompt` per request, and `retry_msg` from violation list. | `Config`, context strings, issue lists. | Strings. |
| [generation/pdf_extractor.py](../pdf_extractor.py) | Extracts text from PDFs for non-Gemini providers. | PDF path. | Plain text. |
| [generation/text_parsing.py](../text_parsing.py) | Strips Markdown code fences, extracts the outermost JSON object from LLM text. | Raw LLM text. | Cleaned JSON text. |

`config.py` decides `cfg.context_dir`:
- `validation.profile = v2` AND `generation_mode = json` → `api/context_v2/`.
- otherwise → `api/context/`.

That single line in [generation/config.py:172-176](../config.py#L172-L176) is
why the json-mode LLM sees the IDTA-aligned templates only when v2 is active.

### v2-specific (in this folder)

| File | Purpose | Inputs | Outputs |
|---|---|---|---|
| [pipeline_v2.py](pipeline_v2.py) | Main retry loop. Calls LLM, parses output, runs validator, builds retry messages, repeats up to `max_attempts`. | `Config`, `system_instruction`, `user_prompt`, `pdf_base64`, `rag_gemini_parts`, optional `progress_callback`. | `(aas_json: str, conforms: bool, issues: list[dict], attempts: int)`. |
| [AAS_builder_v2.py](AAS_builder_v2.py) | Wraps the v2 `AASGenerator` in a `profile_json_text_to_aas_json` function that the pipeline calls. | Profile JSON text + `Config`. | Full AAS JSON text. |
| [validator_v2.py](validator_v2.py) | Single pyshacl call against the unified shapes graph. Classifies issues (`metamodel` vs `ontology`) by `sh:sourceShape`/`sh:resultPath` namespace. | AAS JSON text + tmp dir. | `(conforms, all_issues, metamodel_issues, ontology_issues)`. |
| [AAS_generation_v2/](AAS_generation_v2/) | Builder package — see below. |

### `AAS_generation_v2/` — the basyx-SDK builder

Everything here subclasses or re-exports from v1, with overrides only where
v2 needs corrected/added semanticIds. The class names match v1 with a `V2`
suffix; submodel-builder constructors take the same arguments as v1, so
swapping factories is a one-line change.

| File | What it does |
|---|---|
| [core/semantic_ids.py](AAS_generation_v2/core/semantic_ids.py) | `SemanticIdFactoryV2(SemanticIdFactory)` — overrides `_DIGITAL_NAMEPLATE_SUBMODEL`, `_HIERARCHICAL_STRUCTURES`, `_CAPABILITIES_SUBMODEL`, `_SKILLS_SUBMODEL`, `_VARIABLES_SUBMODEL`, `_PARAMETERS_SUBMODEL` with IDTA-aligned URLs. Adds new properties for missing SME-level IDs (`NP_MANUFACTURER_NAME`, …, `AID_ENDPOINT_METADATA`). Module-level string constants are imported by `tools/aas_to_rdf.py` to keep one source of truth. |
| [core/element_factory.py](AAS_generation_v2/core/element_factory.py) | `AASElementFactoryV2(AASElementFactory)` — same API plus a guard: any `id_short` in `_REQUIRES_SEMANTIC_ID` (ManufacturerName, ContactInformation, OrderCodeOfManufacturer, …) without a `semantic_id=` argument raises `ValueError` immediately. Turns a silent gap into a build-time failure. |
| [core/aas_builder.py](AAS_generation_v2/core/aas_builder.py) | Re-export of v1 `AASBuilder` — shell construction is namespace-agnostic and currently has no v2-specific changes. |
| [submodels/nameplate_builder.py](AAS_generation_v2/submodels/nameplate_builder.py) | Subclasses v1; overrides `build()` to thread `semantic_id=` through every mandatory child SME and to materialize a typed `ContactInformation` SMC + `OrderCodeOfManufacturer` Property with their IDTA IDs. |
| [submodels/asset_interfaces_builder.py](AAS_generation_v2/submodels/asset_interfaces_builder.py) | Subclasses v1; overrides `_create_mqtt_endpoint_metadata` to attach `AID_ENDPOINT_METADATA` to the `EndpointMetadata` SMC. |
| `submodels/{hierarchical_structures,capabilities,skills,variables,parameters}_builder.py` | Re-exports — the v2 SemanticIdFactory's overridden constants flow through inheritance, so the existing submodel-level `semanticId` URLs are automatically corrected without code changes. |
| [cli/generate_aas.py](AAS_generation_v2/cli/generate_aas.py) | `AASGenerator(_V1Generator)` — only `_initialize_builders` is overridden, swapping every factory/builder for its V2 counterpart. Every other method (`generate_system`, `_build_object_store`, `_serialize_to_dict`, ontology guidance) is inherited unchanged. |

### Why subclassing rather than rewriting
- Each v2 file lists exactly what changed — code review of "what's v2"
  is the file content, not a diff against thousands of lines.
- The v1 implementations of complex submodels (Skills, Capabilities, AID
  with action/property/forms structures) keep working untouched.
- One v1 patch was needed to make this safe:
  [generation/AAS_generation/__init__.py](../AAS_generation/__init__.py)
  had a stale `from .aas_generation import main`; wrapped in `try/except`
  so the package imports even though the file is gone.

---

## 5. API layer

### `api/main.py` — FastAPI app + CORS
- Three routers mounted under `/api`: `validate`, `context`, `generate_aas`.
- CORS allows `localhost:5173` (Vite UI) and `localhost:5678` (n8n).
- Run: `uvicorn api.main:app --reload --port 8000` from the repo root.

### `api/routers/generate_aas.py` — generation endpoint
- **Routes:**
  - `POST /api/generate-aas` — SSE stream (`text/event-stream`).
  - `GET  /api/generation-config` — provider list + per-provider model list +
    defaults, scraped from `config.yaml` (no API keys).
- **Request model `GenerateAasRequest`** carries asset identity, selected
  submodels, spec sheet (text and/or PDF base64), supplemental files,
  provider/model, and generation options (`generation_mode`, `use_rag`,
  `use_example`, `force_full_aas_output`, `max_pdf_chars`, `max_attempts`).
- **Pipeline dispatch:** [_select_pipeline(cfg)](../../api/routers/generate_aas.py#L37-L42)
  reads `cfg.validation_profile` and returns `run_pipeline_v2` (default) or
  `run_pipeline_v1`. Both accept the same arguments (last positional being
  `progress_callback`).
- **SSE event types** (matched in [ui/src/api/client.ts](../../ui/src/api/client.ts#L70-L74)):
  - `{ type: "log", message }` — every line the pipeline prints, forwarded
    via the `progress_callback` injected into `pipeline_v2.run_pipeline`.
  - `{ type: "stage", stage, attempt, max_attempts }` — phase markers
    (`preparing`, `querying`, `validating`, `done`).
  - `{ type: "result", conforms, aas_json, attempts, issues }` — final
    payload after the loop exits.
  - `{ type: "error", message }` — abort signal.
- The endpoint also extracts OPC UA NodeSet hints from supplemental XML
  files before building the user prompt; that summary is appended as
  context in `build_user_prompt`.

### `api/routers/validate.py` — live SHACL endpoint
- **Route:** `POST /api/validate`.
- **Used by:** the UI's `useValidation` hook on every (debounced) edit of
  the AAS JSON in the model builder.
- **Current wiring:** still calls v1's `tools/run_resourceaas_validation`
  with v1's shapes/ontologies (loaded once at module import via
  `load_validation_paths()`). v2's `run_shacl_v2` is **not** wired here yet.
- **Output:** `ValidateResponse` with `conforms`, `issues[]`, `report_ttl`.
  Each `ValidationIssue` includes a `field` dot-path computed by
  `_MESSAGE_TO_FIELD` regex matching, used by the UI to route the issue to
  the relevant wizard step.
- **Known gap:** when v2 should also drive live validation, swap line 20 to
  import `generation.v2.validator_v2.run_shacl_v2` and adapt the
  `run_validation` call (it returns `(conforms, all, meta, onto)` instead
  of writing a TTL — replace the `_parse_report_ttl` step with the issue
  list directly). The `field` regex map in this file should still apply,
  since v2 surfaces the same `sh:resultMessage` strings.

### `api/routers/context.py` — provider config
- Returns the public part of `config.yaml` (model lists, defaults). Keys
  never leave the server.

### `api/models.py` — pydantic models
- `ValidateRequest`, `ValidateResponse`, `ValidationIssue`. Shared across
  the validate route and the SSE result event.

---

## 6. UI layer (Vue/React frontend in `ui/`)

| File | Role | Talks to |
|---|---|---|
| [ui/src/api/client.ts](../../ui/src/api/client.ts) | Single fetch wrapper. Defines TS types matching the API's pydantic models. Streams SSE events for `/api/generate-aas`. | `/api/*`. |
| [ui/src/hooks/useGenerateAI.ts](../../ui/src/hooks/useGenerateAI.ts) | State machine for the generation dialog: `preparing` → `querying` → `validating` → `done`. Subscribes to SSE events, updates progress, stores the final AAS JSON. | `api.generateAas` (SSE). |
| [ui/src/hooks/useValidation.ts](../../ui/src/hooks/useValidation.ts) | Debounced (~400 ms) re-validation on every model edit. Pushes results into the per-node validation map in the Zustand store. | `api.validate`. |
| [ui/src/components/modelbuilder/GenerateAIDialog.tsx](../../ui/src/components/modelbuilder/GenerateAIDialog.tsx) | The dialog the user fills out. Uploads PDFs, picks submodels, submits. | `useGenerateAI`. |
| [ui/src/components/shared/ValidationIssueCard.tsx](../../ui/src/components/shared/ValidationIssueCard.tsx) | One card per issue, colored by severity. Clicking the `field` jumps to the wizard step with that idShort. | Zustand store. |
| [ui/src/store/useAppStore.ts](../../ui/src/store/useAppStore.ts) | Single Zustand store: model JSON, per-node validation, dialog state. | — |

The UI is **profile-agnostic**. It doesn't know whether v1 or v2 ran — it
only sees the AAS JSON and the issue list. This is why v2 needed no UI
changes; the toggle lives in `config.yaml`.

---

## 7. Data formats at the boundaries

| Where | Shape |
|---|---|
| Profile JSON (LLM output, json-description mode) | `{ "<SystemName>": { "idShort", "id", "globalAssetId", … plus per-submodel sections by friendly name } }`. No `semanticId`, no `modelType`. See [README.md §profile contract](README.md). |
| Full AAS JSON (LLM output, json mode; builder output, json-description mode) | Standard AAS Part 5 envelope: `{ "assetAdministrationShells": [...], "submodels": [...], "conceptDescriptions": [] }`. Carries `semanticId` and `modelType`. |
| RDF (validator input) | Turtle. Generated by `tools/aas_to_rdf.py`. Uses AAS v3.1 namespace + cssx + css. |
| SHACL report | Standard `sh:ValidationReport` graph. `validator_v2._extract_issues` flattens into a list of dicts. |
| `ValidateResponse` (HTTP) | `{ conforms, issues[], report_ttl }`. |
| SSE event (HTTP) | One JSON object per `data:` line; types listed in §5. |

---

## 8. End-to-end walkthrough — a generate request

1. **User** clicks "Generate" in the GenerateAIDialog, passes a PDF + asset
   name + selected submodels.
2. **`useGenerateAI`** sends `POST /api/generate-aas` with the request body
   and opens an SSE reader.
3. **`api/routers/generate_aas.py`**:
   - calls `load_config()` → `Config(validation_profile="v2", generation_mode="json-description", …)`,
   - decides `cfg.context_dir = api/context/` (json-description mode reuses v1's
     templates),
   - loads context (preamble + per-submodel templates) and RAG (IDTA PDFs),
   - builds `system_instruction` and `user_prompt` (PDF base64 inlined for
     Gemini, extracted to text for Groq),
   - emits SSE `stage: "querying"`,
   - calls `_select_pipeline(cfg)` → `run_pipeline_v2`.
4. **`pipeline_v2.run_pipeline`** loops up to `cfg.max_attempts`:
   - **a.** `call_llm` → raw text (cycles models on 429),
   - **b.** strip code fences, parse profile JSON,
   - **c.** `validate_profile_document` (lightweight checks: idShort regex,
     URI shape, mandatory submodel sections present),
   - **d.** `AAS_builder_v2.profile_json_text_to_aas_json` →
     `AASGenerator(v2).generate_system` → full AAS JSON with IDTA semanticIds
     baked in by `SemanticIdFactoryV2` and `DigitalNameplateSubmodelBuilderV2`,
   - **e.** `validator_v2.run_shacl_v2`:
      - `tools/aas_to_rdf.convert` → Turtle,
      - load `CSSx_AAS.ttl` (transitively pulls AAS v3.1) into the data graph,
      - load combined shapes (AAS SHACL + auto-derived CSSx shapes),
      - one `pyshacl.validate` call,
      - partition into `metamodel` / `ontology` issues,
   - **f.** if not conforms, build a retry message that repeats the violations
     and append it to the conversation; loop.
5. **Final** SSE `result` event with the AAS JSON, attempt count, and issue
   list.
6. **`useGenerateAI`** writes the AAS into the store; the model builder
   re-renders, and `useValidation` immediately re-runs `/api/validate` on the
   stored JSON to populate the per-node issue cards.

## 9. End-to-end walkthrough — a live validate request

1. **User** edits a node in the wizard.
2. **`useValidation`** debounces ~400 ms, then `POST /api/validate { json_text }`.
3. **`api/routers/validate.py`** writes the JSON to a temp file and calls
   `tools/run_resourceaas_validation.run_validation` (v1 path — see Known
   gap in §5). Returns `{ conforms, issues[], report_ttl }`.
4. **`useValidation`** pushes the issues into the per-node store map; the
   `ValidationIssueCard` for each node re-renders.

When this endpoint is migrated to v2, the contract on the wire stays the
same (`ValidateResponse` shape unchanged). Only the inside of the route
function changes.

---

## 10. Running everything locally

```bash
# Backend
cd ppr-ontology
.venv/Scripts/python -m uvicorn api.main:app --reload --port 8000

# Frontend (separate terminal)
cd ui
npm install
npm run dev          # Vite on :5173

# CLI shortcut for v2 builder + validator (no LLM, no UI)
.venv/Scripts/python -m generation.v2.AAS_generation_v2.cli.generate_aas \
    --config aas_configs/imaDispensing.json \
    --output /tmp/aas-out

# Regenerate v2 SHACL shapes after editing CSSx_AAS.ttl
.venv/Scripts/python tools/generate_shapes_v2.py
```

Switch validation profile by editing [generation/config.yaml](../config.yaml):
```yaml
validation:
  profile: v2   # or "v1"
```

---

## 11. Where to extend

| You want to | Touch |
|---|---|
| Add a new IDTA semanticId | `AAS_generation_v2/core/semantic_ids.py` (constant + property) AND `tools/aas_to_rdf.py` (`SUBMODEL_TYPE_BY_SEMANTIC_ID` or `SME_TYPE_BY_SEMANTIC_ID`). Both must agree. |
| Add a new mandatory SME | The semanticId step above + an entry in `core/element_factory.py:_REQUIRES_SEMANTIC_ID` so build-time guards fire. Override the relevant submodel builder in `AAS_generation_v2/submodels/`. |
| Add a new submodel type | Same as above + a new `cssx:has<X>Submodel` typed-link property in `CSSx_AAS.ttl` + a new `_TYPED_LINK_BY_SUBTYPE` entry in `aas_to_rdf.py` + a new submodel builder. Regenerate SHACL. |
| Tighten a CSSx OWL constraint | Edit `ontology/CSSx_AAS.ttl`. Rerun `tools/generate_shapes_v2.py`. No Python changes. |
| Change LLM context for json mode | Edit `api/context_v2/00-preamble.md` or `submodels/<name>.md`. |
| Change LLM context for json-description mode | Edit `api/context/...` (still shared with v1). |
| Wire `/api/validate` to v2 | Replace `from tools.run_resourceaas_validation import run_validation` with the v2 import + adapter (see §5). |
| Add a new LLM provider | Add a branch in `generation/llm_client.py` and a new `models.<provider>` list in `config.yaml`. |
| Surface validation profile in the UI | Add a field to `GenerateAasRequest`, plumb it through to `_select_pipeline`. (Currently server-side only.) |

---

## 12. Cheat sheet — what calls what

```
api/main.py
└── api/routers/generate_aas.py
    ├── generation/config.py            (load_config)
    ├── generation/context_loader.py    (preamble + submodel md)
    ├── generation/rag_loader.py        (IDTA PDFs/JSONs)
    ├── generation/prompt_builder.py    (system + user + retry msgs)
    └── _select_pipeline(cfg)
        ├── generation/pipeline.py            (v1, fallback)
        └── generation/v2/pipeline_v2.py      (v2, default)
            ├── generation/llm_client.py
            ├── generation/json_description_generation.py  (parse profile)
            ├── generation/profile_structure.py            (normalize)
            ├── generation/v2/AAS_builder_v2.py
            │   └── generation/v2/AAS_generation_v2/cli/generate_aas.py
            │       └── AAS_generation_v2/{core,submodels}/*  (basyx SDK)
            └── generation/v2/validator_v2.py
                ├── tools/aas_to_rdf.py
                ├── ontology/CSSx_AAS.ttl
                │   └── owl:imports → ontology/aas-rdf-ontology.ttl
                ├── ontology/aas-shacl-schema.ttl
                └── shacl/generated_v2/shapes.generated.shacl.ttl

api/main.py
└── api/routers/validate.py     (live edit validation)
    ├── generation/config.py    (load_validation_paths)
    └── tools/run_resourceaas_validation.py  ← still v1; see §5 to migrate
```

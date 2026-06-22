# Ontology-Grounded LLM Architecture for Automated AAS Generation

This document describes the architecture of the ResourceAAS generation system at two levels of abstraction -- first as a conceptual framework explaining *what* the system does and *why*, then as a technical specification explaining *how* each component is implemented -- followed by a discussion of the design choices that shaped the system.

---

## Part I: Conceptual Architecture

### 1. The Problem

The Asset Administration Shell (AAS) is the Industrie 4.0 standard for creating digital twins of physical and software assets. An AAS instance is a deeply structured JSON document containing an envelope (identifiers, asset metadata) and multiple submodels (DigitalNameplate, Skills, Capabilities, AssetInterfacesDescription, etc.), each with typed elements carrying standardized semantic identifiers from IDTA catalogs.

Creating AAS instances today is manual, slow, and requires simultaneous expertise in:

- The AAS Part 2 v3.1 metamodel (JSON structure, element types, reference formats).
- Domain-specific submodel templates (IDTA 02006 Nameplate, IDTA HierarchicalStructures, etc.).
- The specific asset being described (datasheets, integration documentation, OPC UA NodeSets).
- Cross-submodel consistency rules (e.g., if Skills exist, Capabilities and an interface description must also exist).

The system automates this by combining LLM-based information extraction with ontology-grounded validation.

### 2. Core Idea: The Dual Role of the Ontology

The central architectural insight is that a formal ontology can serve two complementary roles simultaneously:

1. **As generative context** -- The ontology's concepts, constraints, and relationships are translated into natural language and embedded in the LLM's prompt. This steers the LLM toward structurally and semantically valid outputs during generation.

2. **As validation specification** -- The same ontology is compiled into executable SHACL shapes that mechanically check the LLM's output. Violations are fed back to the LLM for correction.

This dual role creates a closed feedback loop:

```
                Ontology (OWL)
               /              \
     [translated to           [compiled to
      natural language]        SHACL shapes]
          |                        |
          v                        v
    LLM Prompt Context      Validation Rules
          |                        |
          v                        v
       LLM Generation  --->  Validation Check
                                   |
                            violations (if any)
                                   |
                              Retry Prompt
                                   |
                                   v
                           LLM Re-generation
```

The ontology is the single source of truth. What the LLM is told to produce and what the validator checks are derived from the same formal specification. This eliminates the class of errors where instructions and validation diverge.

### 3. Three-Layer Separation

The system separates three fundamentally different concerns into distinct layers:

#### Layer 1: Generation (Probabilistic)

An LLM reads a product datasheet (PDF or text) and produces a *profile document* -- a simplified JSON capturing the semantic content of the asset (manufacturer name, serial number, capabilities, skill definitions, interface endpoints). The LLM operates under rich context: ontology-derived rules, submodel templates, semantic guidance, and reference examples.

The profile is intentionally simpler than the full AAS JSON. It captures *what* should be in each submodel without requiring the LLM to produce the AAS metamodel's deeply nested structure (modelTypes, reference formats, semanticId key arrays). This drastically reduces the surface area for structural errors.

#### Layer 2: Transformation (Deterministic)

A code-driven builder pattern expands the profile into a fully compliant AAS JSON using the BaSyx Python SDK. Each submodel has a dedicated builder class that:

- Creates properly typed AAS elements (Property, MultiLanguageProperty, SubmodelElementCollection, Operation, etc.).
- Attaches correct semantic identifiers from the IDTA catalog.
- Generates well-formed references (ModelReference, ExternalReference) with correct key structures.

This layer is entirely deterministic. Given the same profile input, it always produces the same AAS output. Structural compliance is guaranteed by the SDK, not by the LLM.

#### Layer 3: Validation (Symbolic)

The full AAS JSON passes through two independent validation stages:

1. **Metamodel validation** (BaSyx SDK): Checks that the JSON conforms to the AAS Part 2 schema -- correct modelTypes, required fields, valid value types, proper reference structures.

2. **Ontology validation** (SHACL + OWL): The AAS JSON is projected into an RDF graph, merged with the domain ontology, and validated against SHACL shapes with RDFS inference. This catches *semantic* violations: missing mandatory submodels, broken cross-submodel dependencies, capabilities without linked skills, bills of material with no entries.

If either validation stage reports violations, they are formatted into a structured retry message and appended to the LLM's conversation history. The LLM then generates a corrected profile, and the cycle repeats (up to a configurable maximum).

### 4. The Ontology Stack

The domain knowledge is organized as a layered OWL ontology:

```
CSS Ontology (Plattform Industrie 4.0)
  Resource, Skill, Capability, Service, SkillInterface, StateMachine
     |
     | owl:imports
     v
CSSx Extension Ontology (Aalborg University ResourceAAS)
     |
     | owl:imports (10 domain modules)
     v
+-- cssx-nameplate.ttl          Manufacturer, serialNumber, dateOfManufacture
+-- cssx-skills.ttl             SkillOperation, SkillMode, interface bindings
+-- cssx-capabilities.ttl       Capability extensions, semantic groundings
+-- cssx-bom.ttl                Bill of materials, part-whole relationships
+-- cssx-resource-interface.ttl SoftwareInterface, InterfaceProperty/Action
+-- cssx-operational-data.ttl   Variable mappings, runtime data bindings
+-- cssx-parameters.ttl         Configuration parameters
+-- cssx-technical-data.ttl     Hardware/software versions
+-- cssx-resource-hierarchy.ttl Resource composition hierarchy
+-- cssx-aas-validation.ttl     Validation projection vocabulary + OWL constraints
```

The `cssx-aas-validation.ttl` module is architecturally critical. It defines a *projection vocabulary* -- a set of OWL classes and properties that bridge the AAS JSON world and the RDF world. Each AAS submodel type maps to a projection class (e.g., `DigitalNameplateSubmodel`, `SkillsSubmodel`), and OWL axioms over these classes encode the domain rules:

- Every Resource must have exactly one DigitalNameplate and exactly one HierarchicalStructures submodel.
- If a Resource has a Skills submodel, it must also have an AID (AssetInterfacesDescription) submodel.
- If a Resource has a Capabilities submodel, it must also have a Skills submodel (and vice versa).
- Every Capability must be linked to at least one Skill via `isRealizedBySkill`.
- Every HierarchicalStructures submodel must contain at least one BoM entry.

These axioms are *automatically transformed* into executable SHACL shapes via an OWL-to-SHACL ruleset. Manual SPARQL-based SHACL rules supplement the auto-generated shapes for constraints that require graph pattern matching beyond OWL DL's expressivity (e.g., "each SkillInterface must reference a ResourceInterface provided by the same Resource").

### 5. Uncertainty Handling

The system implements a calibrated uncertainty mechanism via `[VERIFY: reason]` markers:

- When the LLM cannot find a value in the datasheet, it inserts `[VERIFY: SerialNumber not found in datasheet]` instead of guessing.
- These markers are **allowed** in data value fields (manufacturer name, serial number) -- they signal human review points without blocking generation.
- They are **forbidden** in structural identifier fields (idShort, id, globalAssetId, semantic ID keys) -- these must be machine-parseable. The LLM is instructed to generate a deterministic fallback instead.

The validation layer enforces this boundary: `[VERIFY: ...]` markers in identifier fields are flagged as violations, triggering a retry.

### 6. Multi-Provider Abstraction

The generation layer abstracts over three LLM providers:

- **Google Gemini**: Receives PDFs as native multimodal inline data (base64-encoded). Best for datasheet-heavy generation.
- **Groq** (via OpenAI-compatible API): Receives extracted PDF text. Token-per-minute (TPM) budgeting limits output tokens dynamically.
- **Claude** (via CLI subprocess): Receives extracted PDF text via temporary files. Supports system instruction files and JSON output format.

The same ontological constraints, prompt templates, and validation rules apply regardless of provider. The architecture treats the LLM as a replaceable component -- *what is correct* is defined by the ontology, not by the model.

When a model hits a rate limit (HTTP 429), the system automatically cycles to the next model in a configured fallback list without losing conversation history.

### 7. Information Flow Summary

```
                                  Ontology (OWL/SHACL)
                                 /         |          \
                   context      /   projection     validation
                  templates    /    vocabulary     shapes
                     |        /         |              |
                     v       v          |              v
PDF -----> [Extract] ---> [LLM] --> Profile JSON      |
                                       |              |
                                       v              |
                              [Builder Pattern]       |
                              (basyx SDK)             |
                                       |              |
                                       v              |
                              Full AAS JSON           |
                                       |              |
                                       v              v
                              [JSON -> RDF] ----> [SHACL Validator]
                                                      |
                                               violations (if any)
                                                      |
                                                      v
                                               [Retry Prompt] ---> back to LLM
```

---

## Part II: Technical Architecture

### 8. Configuration System

**File**: `generation/config.py` + `generation/config.yaml`

All runtime configuration is centralized in a single `Config` dataclass. No module accesses `os.environ` directly -- all environment-specific values are resolved at config load time and injected via the dataclass.

```python
@dataclass
class Config:
    provider: str               # "gemini" | "groq" | "claude"
    api_key: str                # resolved for the chosen provider
    asset_name: str             # e.g., "CA18CLC12BPM1"
    base_url: str               # e.g., "https://smartproductionlab.aau.dk"
    pdf_path: Optional[Path]    # None = text-only mode
    submodels: list[str]        # e.g., ["Nameplate", "Skills", "Capabilities"]
    generation_mode: str        # "json" | "json-description"
    use_rag: bool               # load RAG reference documents
    use_example: bool           # include valid AAS example in context
    max_attempts: int           # retry loop bound
    models: list[str]           # ordered fallback list for rate-limit cycling
    shacl_shapes: list[Path]    # SHACL shape files for validation
    ontology_paths: list[Path]  # OWL ontology files for inference
    # ... (paths, multi-provider keys, output locations)
```

The `load_config()` function parses `config.yaml`, validates the provider, resolves all paths relative to the repository root, and returns an immutable `Config` instance. A separate `load_validation_paths()` function loads only shape and ontology paths without requiring API key validation -- used by the validation-only API endpoint.

The config stores API keys for *all three* providers simultaneously, enabling runtime provider switching (e.g., via CLI override or API request) without reloading configuration.

### 9. Prompt Construction

**Files**: `generation/prompt_builder.py`, `generation/prompts.yaml`

Prompts are assembled from YAML templates with runtime placeholders. The template system (`prompts.yaml`) defines 11 templates:

| Template | Purpose |
|----------|---------|
| `uncertainty_rules` | `[VERIFY: ...]` marker protocol |
| `system_base` / `system_base_json_description` | Core LLM role and rules (per generation mode) |
| `user_spec_note_gemini_with_pdf` | "PDF is attached -- read carefully" |
| `user_spec_note_text_with_pdf` | Inline extracted PDF text |
| `user_spec_note_no_pdf` | "Generate realistic values" |
| `user_prompt_base` / `user_prompt_base_json_description` | Asset metadata + spec + mode-specific sections |
| `retry_template` / `retry_template_json_description` | Retry message with violation placeholders |

Templates are loaded once via `@lru_cache` and validated for required placeholder keys at load time.

The **system instruction** is composed as:

```
system_base template (with {uncertainty_rules} expanded)
---
context_text (from context_loader.py):
  - 00-preamble.md: AAS envelope rules, ID conventions, dependency rules
  - shacl-rules.md: human-readable summary of all SHACL constraints
  - [optional] valid-example.json: complete valid AAS JSON example
  - per-submodel templates: nameplate.md, skills.md, capabilities.md, etc.
---
[for non-Gemini providers] RAG text blocks
```

The **user prompt** in `json-description` mode includes two dynamically generated JSON structures:

1. **Profile example JSON**: A template profile with placeholder values and `[VERIFY: ...]` markers, assembled from JSON config templates (e.g., `aas_configs/imaDispensing.json`) or generated stub profiles. Selected submodel sections are scaffolded automatically.

2. **Profile semantic guide JSON**: Per-field guidance describing purpose, constraints, source priority, and examples:

```json
{
  "SystemAAS": {
    "idShort": {
      "purpose": "Human-readable stable identifier for the AAS shell.",
      "constraints": ["AAS-safe token", "letters/digits/underscore only"],
      "source_priority": ["template/default", "config"]
    },
    "DigitalNameplate": {
      "SerialNumber": {
        "purpose": "Serial number in nameplate payload.",
        "constraints": ["string", "must match shell serialNumber when available"],
        "source_priority": ["datasheet"]
      }
    }
  }
}
```

This semantic guide is the natural language projection of the ontology's constraints for each field.

### 10. Context and RAG Loading

**Files**: `generation/context_loader.py`, `generation/rag_loader.py`

**Context loading** reads Markdown files from `api/context/` and concatenates them with `---` separators. The preamble and SHACL rules are always loaded; submodel templates are loaded based on the configured submodel selection (with Nameplate and HierarchicalStructures always mandatory).

The preamble (`00-preamble.md`) contains:
- The exact AAS JSON envelope structure the LLM must produce.
- Submodel ID conventions (`{base_url}/submodels/instances/{systemId}/{idShort}`).
- Mandatory submodel rules (DigitalNameplate, HierarchicalStructures always required).
- Cross-submodel dependency rules (Skills requires Capabilities and AID; etc.).
- Element type reference table (Property, MultiLanguageProperty, SubmodelElementCollection, etc.).
- Common semantic ID URIs from IDTA catalogs.

The SHACL rules file (`shacl-rules.md`) is a human-readable translation of every SHACL shape the validator will check, organized by shape file (core, dependencies, semantics, BoM). It ends with a checklist the LLM can use before outputting.

**RAG loading** reads supplemental reference documents from `generation/RAG/`:
- PDFs are base64-encoded for Gemini or text-extracted for other providers.
- JSON and Markdown files are wrapped as labeled text blocks.
- Both formats are returned; the caller selects based on provider.

### 11. PDF Extraction

**File**: `generation/pdf_extractor.py`

PDF handling is provider-aware:

- **Gemini**: Base64-encodes the PDF for multimodal `inline_data` parts. The model reads the PDF natively.
- **Groq/Claude**: Extracts text via `pymupdf4llm.to_markdown()`. Optional `max_pdf_chars` truncation prevents TPM exhaustion on Groq's free tier.

The `load_pdf()` function returns a tuple `(pdf_base64 | None, pdf_text | None)` -- exactly one is non-None based on provider.

### 12. LLM Client

**File**: `generation/llm_client.py`

The `call_llm()` function provides a unified interface across providers:

```python
def call_llm(
    provider, api_key, models, model_idx, system_instruction,
    gemini_contents=None, groq_history=None, generation_mode="json"
) -> tuple[str, int]:  # (raw_text, new_model_idx)
```

#### Provider Implementations

**Gemini** (`google.genai`):
- Uses multi-turn `contents` list with inline_data parts for PDFs.
- Fixed 32,768 max output tokens, temperature 0.1.
- Response parsed via `_extract_gemini_text()` handling both `.text` attribute and `.candidates[0].content.parts[]`.

**Groq** (OpenAI-compatible):
- Uses message history with system message prepended.
- TPM-aware token budgeting: estimates input tokens (`len(text) // 4`), reserves 7,000 TPM budget, caps output between 256-2,048 tokens.
- Temperature 0.1.

**Claude** (CLI subprocess):
- Invokes `claude -p <prompt> --bare --output-format json --allowedTools Read`.
- System instruction and conversation history written to temporary files.
- Graceful flag degradation: if `--bare`, `--max-output-tokens`, or `--append-system-prompt-file` are unsupported, the CLI is retried without them (up to 4 attempts).
- JSON response parsed for `"result"` field.

#### Error Handling and Model Cycling

All API calls are wrapped in `_invoke_with_timeout()` using `ThreadPoolExecutor` with a 90-second timeout. Errors are classified as "switchable" if they indicate:

- Rate limits (HTTP 429, `rate_limit_exceeded`).
- Payload too large (HTTP 413, `request too large`).
- Model decommissioned (`decommissioned`, `no longer supported`).
- Timeout.

On switchable errors, `model_idx` increments to the next model in the fallback list. The caller receives an empty string and retries. If all models are exhausted, the process exits.

#### Debug I/O

When `GEN_DEBUG_IO=1`, the client writes timestamped files to `generation/output/debug_io/`:
- `{timestamp}-{provider}-{model}-{uuid}.system.txt`: System instruction.
- `...conversation.txt` / `...conversation.json`: Conversation history.
- `...request.json`: Request payload.
- `...response.txt`: Raw LLM response.
- `...meta.txt`: Provider, model, generation mode.

### 13. The Pipeline Loop

**File**: `generation/pipeline.py`

The `run_pipeline()` function orchestrates the entire generation-validation-retry cycle:

```python
def run_pipeline(cfg, system_instruction, user_prompt,
                 pdf_base64, rag_gemini_parts, progress_callback
) -> tuple[str, bool, list[dict], int]:
    # Returns: (aas_json, conforms, issues, attempt_count)
```

**Step-by-step flow:**

1. **Initialize conversation history** -- Provider-specific format:
   - Gemini: `[{"role": "user", "parts": [rag_parts, pdf_inline_data, {"text": user_prompt}]}]`
   - Groq/Claude: `[{"role": "user", "content": user_prompt}]`

2. **Loop** (up to `max_attempts`):

   a. Call `call_llm()` with current conversation history.

   b. Append model response to conversation history.

   c. **In `json-description` mode:**
      - Parse profile JSON from response (strip code fences, extract outer JSON object).
      - Validate profile: check required root fields (idShort, id, globalAssetId), AAS-safe idShort, valid URIs, no `[VERIFY:]` in identifiers, date formats, all selected submodel sections present.
      - Convert profile to full AAS JSON via deterministic builder.
      - Run SHACL validation on full AAS JSON.
      - Merge profile issues and SHACL issues.

   d. **In `json` mode:**
      - Parse AAS JSON directly.
      - Run SHACL validation.

   e. If validation passes (`conforms = True`), break.

   f. Otherwise, format violations into retry message and append to conversation history.

3. Return best result (even if not fully conformant after all attempts).

The conversation history grows across retries. Each retry sees the full context: original prompt, previous attempts, model responses, and specific violation feedback. This enables the LLM to make *targeted corrections* rather than regenerating from scratch.

### 14. Profile Validation

**File**: `generation/json_description_generation.py`

Profile validation is a pre-builder check that catches content errors before the expensive AAS construction:

- **Required root fields**: `idShort`, `id`, `globalAssetId` must exist.
- **idShort safety**: Must match `[A-Za-z0-9_]+` (AAS-safe token). No `[VERIFY:]` markers.
- **URI validity**: `id` and `globalAssetId` must be absolute URIs or `/`-relative paths. No `[VERIFY:]` markers.
- **Date format**: `DateOfManufacture` must match `YYYY-MM-DD`.
- **Submodel completeness**: All selected submodel sections must be present in the profile.
- **Full AAS detection**: If the LLM returns a full AAS package (with `assetAdministrationShells` key) in `json-description` mode, it is flagged as a violation.

### 15. Profile Normalization and Builder Bridge

**Files**: `generation/profile_structure.py`, `generation/AAS_builder.py`

Before the builder runs, the profile is normalized:

- **Alias resolution**: `AID` maps to `AssetInterfacesDescription`, `Variables` maps to `OperationalData`. The LLM may use either name; normalization ensures the builder receives the canonical key.
- **Section scaffolding**: If a selected submodel's section is missing, an empty template with `[VERIFY:]` placeholders is injected.
- **Section pruning**: Submodel sections not in the selection are removed to prevent the builder from generating unrequested submodels.
- **DigitalNameplate guarantee**: Always present after normalization, regardless of selection.

The `AAS_builder.py` module bridges profile JSON to full AAS JSON:

```python
def profile_document_to_aas_json(document, cfg) -> str:
    normalized = normalize_profile_for_builder(document, cfg)
    generator = AASGenerator(config=normalized_config)
    aas_dict = generator.generate_system(system_id, config)
    return json.dumps(aas_dict, indent=2)
```

### 16. The AAS Generation Subsystem

**Directory**: `generation/AAS_generation/`

This subsystem implements the deterministic profile-to-AAS transformation using the BaSyx Python SDK.

#### Core Components

**`AASGenerator`** (`cli/generate_aas.py`): Orchestrates all builders. Its `generate_system()` method:
1. Builds the AAS shell (metadata, asset information, submodel references) via `AASBuilder`.
2. Instantiates each submodel builder based on which sections exist in the config.
3. Each builder returns a `model.Submodel` instance.
4. The result is packaged as `{"assetAdministrationShells": [...], "submodels": [...], "conceptDescriptions": []}`.
5. The package is serialized to JSON via the BaSyx SDK's serialization.

**`AASBuilder`** (`core/aas_builder.py`): Creates the top-level AAS shell with:
- Asset information (globalAssetId, assetType, serialNumber, location).
- Specific asset IDs (serialNumber and location as SpecificAssetId entries).
- Submodel references (dynamically determined from config presence).
- Optional `derivedFrom` reference to a parent AAS.

**`ElementFactory`** (`core/element_factory.py`): Static factory methods for creating AAS elements:
- `create_property(id_short, value, value_type, semantic_id, description)`: Auto-detects value type (bool, int, float, string).
- `create_collection()`, `create_multi_language_property()`, `create_file()`, `create_range()`.

**`SemanticIdFactory`** (`core/semantic_ids.py`): Centralized catalog of 30+ IDTA/W3C semantic URIs. Each property returns an `ExternalReference` wrapping the URI. Prevents URI drift across builders.

#### Submodel Builders

Each submodel type has a dedicated builder class following the same pattern:

| Builder | Submodel | Key Elements Created |
|---------|----------|---------------------|
| `DigitalNameplateSubmodelBuilder` | Nameplate | URIOfTheProduct, ManufacturerName (MLP), SerialNumber, DateOfManufacture |
| `HierarchicalStructuresBuilder` | BoM | ArcheType, EntryNode entity with HasPart/IsPartOf relationships |
| `AssetInterfacesBuilder` | AID | InterfaceMQTT SMC with endpoint metadata, InteractionMetadata (actions/properties) |
| `SkillsSubmodelBuilder` | Skills | Operations wrapped in SMCs, with SkillInterface references and state machine properties |
| `CapabilitiesSubmodelBuilder` | Capabilities | Capability SMCs with SemanticId properties and realizedBy relationship lists |
| `VariablesSubmodelBuilder` | Variables | Variable entries linked to interface property references |
| `ParametersSubmodelBuilder` | Parameters | Configuration parameters with semantic IDs |

Each builder reads its configuration from the corresponding profile section and falls back to top-level profile fields when submodel-specific fields are missing.

#### Guidance Engine

**`guidance/ontology_guidance_engine.py`**: Provides pre-validation SHACL-based guidance for UI editors. Converts YAML config to lightweight RDF (via `yaml_to_rdf_lite.py`), runs SHACL shapes against it, and maps violations to UI field dot-paths (e.g., `"AID submodel must be present"` maps to `"AssetInterfacesDescription"`). This enables live constraint feedback during manual editing, using the same SHACL shapes as production validation.

### 17. JSON-to-RDF Projection

**File**: `tools/mock_resourceaas_to_rdf.py`

This converter bridges the AAS JSON and RDF worlds by projecting AAS structure into the validation ontology's vocabulary.

**Projection mappings:**

```python
# Submodel type classification by idShort
SUBMODEL_TYPE_BY_IDSHORT = {
    "digitalnameplate": AASV.DigitalNameplateSubmodel,
    "nameplate":        AASV.DigitalNameplateSubmodel,
    "skills":           AASV.SkillsSubmodel,
    "capabilities":     AASV.CapabilitiesSubmodel,
    "aid":              AASV.AIDSubmodel,
    "parameters":       AASV.ParametersSubmodel,
    # ...
}

# Type-to-property links
SUBMODEL_LINK_BY_TYPE = {
    AASV.DigitalNameplateSubmodel: AASV.hasDigitalNameplateSubmodel,
    AASV.SkillsSubmodel:          AASV.hasSkillsSubmodel,
    AASV.CapabilitiesSubmodel:    AASV.hasCapabilitiesSubmodel,
    # ...
}
```

For each submodel in the AAS JSON:
1. A typed RDF node is created (`ex:submodel_1 rdf:type aasv:SkillsSubmodel`).
2. The node is linked to the Resource via the type-specific property (`ex:resource aasv:hasSkillsSubmodel ex:submodel_1`).
3. Semantic IDs are extracted from submodel elements and recorded as `aasv:sourceSemanticId` triples.
4. Skills and Capabilities are projected as `css:Skill` and `css:Capability` instances with their interface bindings and `isRealizedBySkill` links.
5. BoM entries are projected as `aasv:BomEntry` nodes with name and globalAssetId.

The projection is *intentionally lossy* -- it captures only the aspects of the AAS that the ontology constrains. This avoids RDF verbosity while ensuring that every ontological constraint has sufficient data to evaluate against.

### 18. Two-Stage Validation

**Files**: `tools/run_resourceaas_validation.py`, `tools/validate_with_basyx.py`, `generation/validator.py`

#### Stage 1: Metamodel Validation

`validate_json_with_basyx()` parses the AAS JSON using the BaSyx SDK's deserializer and reports structural violations: missing required fields, incorrect modelTypes, invalid value types, malformed references.

#### Stage 2: Ontology Validation

`run_validation_detailed()` performs the full SHACL-based validation:

```python
def run_validation_detailed(input_json, generated_rdf, report_ttl,
                            shapes_paths, ontology_paths) -> dict:
    # 1. Metamodel validation (BaSyx)
    basyx_result = validate_json_with_basyx(input_json)

    # 2. JSON -> RDF projection
    convert(input_json, generated_rdf)

    # 3. Load ontologies with transitive OWL imports
    data_graph = Graph().parse(generated_rdf)
    for ontology_file in ontology_paths:
        _load_ontology_with_imports(data_graph, ontology_file, visited)

    # 4. Load SHACL shapes (auto-generated + manual)
    shapes_graph = Graph()
    for shape_file in _resolve_combined_shapes(shapes_paths):
        shapes_graph.parse(shape_file)

    # 5. Run PyShacl with RDFS inference
    conforms, report_graph, report_text = validate(
        data_graph, shacl_graph=shapes_graph,
        inference="rdfs", advanced=True  # Enable SPARQL-based rules
    )

    # 6. Extract and categorize issues
    return {
        "conforms": metamodel_conforms and ontology_conforms,
        "metamodel_issues": [...],
        "ontology_issues": [...]
    }
```

**Ontology import resolution**: `_load_ontology_with_imports()` recursively follows `owl:imports` triples, resolving HTTP URIs to local file paths by looking in the same directory, `modules/`, or parent `modules/` directories. A visited set prevents circular imports.

**Shape resolution**: `_resolve_combined_shapes()` deduplicates shape files and auto-discovers manual SPARQL rules alongside generated shapes. If the manual rules file is not explicitly listed, it is found by convention (`shacl/manual/resourceaas-sparql-rules.shacl.ttl` adjacent to `shacl/generated/`).

**Issue extraction**: `_extract_shacl_issues()` parses the SHACL validation report graph, extracting `sh:ValidationResult` entries with severity mapping (`sh:Violation`, `sh:Warning`, `sh:Info`).

### 19. SHACL Shape Architecture

**Directory**: `shacl/`

The shapes are organized into semantic groups:

| File | Purpose | Source |
|------|---------|--------|
| `generated/shapes.generated.shacl.ttl` | Auto-derived from OWL ontology axioms | `generate_shapes_from_ontology.py` |
| `manual/resourceaas-sparql-rules.shacl.ttl` | Hand-written SPARQL constraint rules | Manual |
| `resourceaas-core.shacl.ttl` | Mandatory submodel constraints | Manual |
| `resourceaas-dependencies.shacl.ttl` | Cross-submodel dependency rules | Manual |
| `resourceaas-semantics.shacl.ttl` | Semantic ID format/pattern validation | Manual |
| `resourceaas-bom.shacl.ttl` | Bill of materials structure rules | Manual |

The dependency shapes (`resourceaas-dependencies.shacl.ttl`) use SPARQL constraints for rules that exceed basic SHACL property shapes:

```turtle
sh:sparql [
  a sh:SPARQLConstraint ;
  sh:message "If Skills, OperationalData, or Parameters are present,
              AID submodel must be present." ;
  sh:select """
    SELECT $this WHERE {
      FILTER(
        ( EXISTS { $this css:providesSkill ?skill }
          || EXISTS { $this aasv:hasSubmodel ?sm . ?sm a aasv:SkillsSubmodel }
          || EXISTS { $this aasv:hasSubmodel ?sm . ?sm a aasv:OperationalDataSubmodel }
          || EXISTS { $this aasv:hasSubmodel ?sm . ?sm a aasv:ParametersSubmodel }
        )
        && !EXISTS { $this aasv:hasSubmodel ?aid . ?aid a aasv:AIDSubmodel }
      )
    }
  """ ] .
```

### 20. OWL-to-SHACL Transformation

**File**: `tools/generate_shapes_from_ontology.py`

This offline tool derives SHACL shapes from OWL ontology axioms:

```python
def main():
    # 1. Load all ontology files with transitive imports
    ontology_graph = Graph()
    for ontology in [CSS_Ontology, CSSx]:
        load_ontology_with_imports(ontology_graph, ontology, visited)

    # 2. Load OWL2SHACL transformation ruleset
    rules_graph = Graph().parse(OWL2SHACL_RULESET)  # owl2sh-semi-closed.ttl

    # 3. Apply rules via PyShacl's SHACL-AF engine
    generated_shapes = shacl_rules(
        ontology_graph, shacl_graph=rules_graph,
        inference="rdfs", advanced=True, iterate_rules=True
    )

    # 4. Write generated shapes
    generated_shapes.serialize("shacl/generated/shapes.generated.shacl.ttl")
```

Three OWL-to-SHACL rulesets are available in `ontology/owl2shacl/`:
- `owl2sh-closed.ttl`: Closed-world assumption (any property not declared is forbidden).
- `owl2sh-open.ttl`: Open-world assumption (undeclared properties are allowed).
- `owl2sh-semi-closed.ttl`: **Used by default**. Declared properties are constrained; undeclared ones are allowed. This matches the AAS use case where the ontology constrains known submodel types but allows vendor-specific extensions.

### 21. REST API

**Directory**: `api/`

A FastAPI application exposes three endpoints:

**`POST /api/validate`**: Standalone validation of existing AAS JSON.
- Input: `{"json_text": "..."}`.
- Runs both metamodel and SHACL validation.
- Maps SHACL violation messages to UI field dot-paths via 30+ regex patterns.
- Returns: `{"conforms": bool, "issues": [...], "report_ttl": "..."}`.

**`GET /api/generate-context`**: Returns assembled prompt context for external workflows.
- Query params: `submodels` (comma-separated), `asset_type`.
- Loads and concatenates preamble, SHACL rules, optional example, per-submodel templates.
- Returns: `{"context_text": "...", "submodels_included": [...]}`.
- Designed for integration with n8n, Zapier, or custom workflows that use their own LLM orchestration but need the ontology-derived context.

**`POST /api/generate-aas`**: Full generation pipeline with Server-Sent Events streaming.
- Accepts: asset metadata, spec text/PDF, provider/model overrides, generation options.
- Supports supplemental file uploads including OPC UA NodeSet XML (parsed for skills/variables/endpoints).
- Streams progress messages as JSON SSE events during the retry loop.
- Returns final AAS JSON and validation results.
- API keys are read server-side from `config.yaml`; never exposed to the client.

**`GET /api/generation-config`**: Returns available providers and model lists (without API keys).

CORS is configured for `localhost:5173` (Vite dev server) and `localhost:5678` (n8n).

---

## Part III: Design Choices

### 22. Why a Profile Intermediate Format?

**Decision**: In `json-description` mode, the LLM generates a simplified profile JSON (50 key-value pairs) instead of the full AAS JSON (2,000+ lines of deeply nested structure).

**Rationale**: A full AAS JSON requires correct `modelType` fields on every element, properly structured `semanticId` objects with nested `keys` arrays, correct `type` discriminators on references (`ModelReference` vs `ExternalReference`), and valid `valueType` strings for properties. These are mechanical concerns that the LLM has no reason to handle -- they are deterministic given the semantic content. By restricting the LLM to the *semantic extraction* task and delegating structural compliance to code, the system:

1. Reduces the LLM's output token budget by ~10x.
2. Eliminates an entire class of structural errors (wrong modelType, malformed references).
3. Enables two-tier validation: fast profile checks before expensive SHACL validation.
4. Makes the builder pattern the single point of control for AAS metamodel compliance.

**Alternative considered**: Direct AAS JSON generation (`json` mode) is still supported. It is faster (skips the builder step) but produces significantly more validation failures, particularly structural ones that the LLM struggles to correct in retries because the corrections themselves introduce new structural errors.

### 23. Why OWL + SHACL Instead of JSON Schema?

**Decision**: Domain constraints are expressed as OWL axioms and validated via SHACL shapes, not as JSON Schema.

**Rationale**: JSON Schema can validate structure (required fields, type checking, pattern matching) but cannot express:

- **Cross-submodel dependencies**: "If Skills exists, AID must exist." JSON Schema has no mechanism for conditional requirements across sibling array elements.
- **Ontological subsumption**: "A SkillInterface that uses a SoftwareInterface implies the existence of a ResourceInterface on the same Resource." This requires class membership reasoning.
- **Transitive closure**: The OWL import chain (CSSx imports CSS imports module ontologies) enables modular constraint composition. JSON Schema's `$ref` is purely structural.
- **Inference**: SHACL validation with `inference="rdfs"` derives implicit type memberships from `rdfs:subClassOf` chains. This allows constraints written against `css:Resource` to apply to all its subtypes without enumeration.

JSON Schema is used implicitly (via BaSyx metamodel validation) for structural checks. OWL/SHACL handles the semantic layer that JSON Schema cannot reach.

### 24. Why Automatic OWL-to-SHACL Derivation?

**Decision**: SHACL shapes are automatically derived from OWL axioms, with manual SPARQL rules for exceptions.

**Rationale**: Maintaining two parallel constraint systems (OWL ontology and hand-written SHACL) creates a synchronization problem. When a new constraint is added to the ontology (e.g., a new cardinality restriction), the SHACL shapes must be updated manually -- and forgetting to do so creates a silent validation gap.

The OWL-to-SHACL transformation eliminates this problem for constraints expressible as OWL axioms:
- `owl:minCardinality` / `owl:maxCardinality` become `sh:minCount` / `sh:maxCount`.
- `rdfs:range` becomes `sh:class` or `sh:datatype`.
- `owl:FunctionalProperty` becomes `sh:maxCount 1`.

The semi-closed world assumption (`owl2sh-semi-closed.ttl`) is deliberate: it constrains properties the ontology declares while allowing vendor-specific extensions. This matches the AAS philosophy of standardized structure with extensibility.

Manual SPARQL rules handle constraints that OWL DL cannot express:
- "Each SkillInterface must reference a ResourceInterface *from the same Resource*" (requires graph pattern matching with identity).
- "If Skills or OperationalData or Parameters exist, AID must exist" (disjunctive precondition with existential check).

### 25. Why Separate Metamodel and Ontology Validation?

**Decision**: Validation is split into two independent stages with separate issue lists.

**Rationale**: The two stages catch different classes of errors with different root causes:

- **Metamodel issues** (BaSyx): Wrong JSON structure. Root cause is usually the builder code or a profile normalization bug. Fix by editing the builder.
- **Ontology issues** (SHACL): Wrong semantic content. Root cause is usually the LLM's extraction or the user's configuration. Fix by re-prompting the LLM or adjusting the config.

Separating them allows the retry mechanism to provide targeted feedback. The LLM receives both categories but labeled distinctly, so it can focus on content corrections without attempting to fix structural issues (which it cannot control in `json-description` mode).

### 26. Why Provider Abstraction with Model Cycling?

**Decision**: A single `call_llm()` function wraps three providers with automatic fallback on rate limits.

**Rationale**: The system is designed for production use where:
- Free-tier API quotas are common (Groq's 7,000 TPM limit).
- Models are periodically deprecated or rate-limited during high-traffic periods.
- Different providers have different strengths (Gemini for PDF understanding, Claude for structured output adherence).

Model cycling treats rate limits as *expected operational events*, not errors. When a model returns HTTP 429, the system advances to the next model in the configured list and retries without losing conversation history. This is invisible to the pipeline logic -- `call_llm()` returns an empty string on rate-limit switches, and the pipeline simply decrements its attempt counter to avoid counting the rate-limited call.

The conversation history is maintained in provider-specific formats (Gemini's multi-part `contents` vs. OpenAI-compatible `messages`). This is a deliberate pragmatic choice: the formats differ enough (Gemini supports multimodal `inline_data` parts; OpenAI uses string `content`) that a unified format would require lossy conversion.

### 27. Why `[VERIFY: ...]` Markers Instead of Refusing to Generate?

**Decision**: When the LLM cannot find a value, it inserts a `[VERIFY: reason]` marker and continues generating.

**Rationale**: In industrial contexts, a partially complete AAS with flagged uncertainties is more useful than no AAS at all. The alternative -- refusing to generate when any value is uncertain -- would make the system unusable for most real-world datasheets, which rarely contain every required field.

The distinction between "allowed in data values" and "forbidden in identifiers" is a principled boundary:
- Data values (manufacturer name, serial number) are consumed by humans who can resolve the `[VERIFY]` flag.
- Identifiers (URIs, idShorts) are consumed by machines (BaSyx servers, reference resolvers) that cannot handle placeholder syntax.

The validation layer enforces this boundary mechanically, so the LLM's instructions and the system's enforcement are aligned.

### 28. Why Closed-Loop Feedback Instead of One-Shot Generation?

**Decision**: Validation failures are fed back to the LLM for iterative correction rather than being returned as-is.

**Rationale**: LLM outputs are stochastic. A single generation attempt may miss constraints that the LLM "knows" from its context but failed to satisfy due to attention limitations, token budget constraints, or conflicting signals in the input.

The retry mechanism exploits a key property of the feedback: **SHACL violations are specific and actionable.** Each violation names the constraint, the focus node, and often the missing property. When formatted as a retry prompt, this gives the LLM *precisely targeted* guidance for correction.

Empirically, most violations resolve within 2-3 iterations because:
- First-attempt errors are typically omissions (missing submodel section, missing field), not fundamental misunderstandings.
- The LLM sees its previous output alongside the violations, enabling minimal corrections rather than regeneration.
- The conversation history accumulates context: each retry adds information about what the validator expects.

The `max_attempts` bound prevents runaway costs. When the system cannot converge, the best partial result is returned with its violation report.

### 29. Why Markdown Context Templates Instead of Fine-Tuning?

**Decision**: Ontology constraints are translated into Markdown templates embedded in the prompt, not baked into a fine-tuned model.

**Rationale**:
- **Modifiability**: Adding or changing a constraint means editing a Markdown file, not retraining a model. Turnaround is minutes, not hours.
- **Transparency**: The exact instructions given to the LLM are visible as text files in `api/context/`. Debugging "why did the LLM do X?" reduces to reading the prompt.
- **Provider independence**: The same templates work across Gemini, Groq, and Claude. Fine-tuning would require per-provider retraining.
- **Composability**: Templates are loaded per-submodel. Requesting only Nameplate + Skills loads only those templates. A fine-tuned model would need to handle all submodel combinations in one training set.
- **Validation alignment**: The Markdown templates in `api/context/shacl-rules.md` are a *natural language translation* of the same SHACL shapes used for validation. Changes to either can be synchronized by updating the other.

### 30. Why a REST API with SSE Streaming?

**Decision**: The system exposes a FastAPI backend with Server-Sent Events for the generation endpoint.

**Rationale**: The generation pipeline takes 30-300 seconds depending on retries. Without streaming, the client would face a long unresponsive wait. SSE provides:
- Real-time progress updates ("Attempt 2/5", "Validation: 3 issues found").
- Intermediate results visible before the final output.
- Clean integration with web frontends and workflow tools (n8n).

The `/api/generate-context` endpoint decouples context assembly from generation, enabling external systems to use the ontology-grounded context with their own LLM orchestration. This supports workflows where the LLM call happens in n8n or a custom agent, but the prompt context comes from the same ontology-derived source.

### 31. Why Defensive Profile Normalization?

**Decision**: The profile undergoes extensive normalization (alias resolution, section scaffolding, key canonicalization) before the builder runs.

**Rationale**: LLMs are inconsistent in naming. The same concept may appear as:
- `AID`, `AssetInterfacesDescription`, `AssetInterfaceDescription`
- `Variables`, `OperationalData`
- `Nameplate`, `DigitalNameplate`

Rather than training the LLM to always use the canonical name (fragile) or rejecting non-canonical names (user-hostile), the system normalizes all variants to canonical keys. This absorbs LLM naming inconsistency as a feature of the transformation layer, not a validation failure.

Section scaffolding (injecting empty templates for missing submodel sections) ensures the builder always has a complete config to work with, even if the LLM omitted a section. The scaffolded sections contain `[VERIFY: ...]` markers that surface in the final output as human review points.

---

## Appendix: File Map

```
ppr-ontology/
  generation/
    config.py                  Config dataclass + YAML loader
    config.yaml                Runtime configuration (provider, keys, asset, options)
    pipeline.py                Generation-validation-retry loop
    llm_client.py              Multi-provider LLM wrapper with model cycling
    prompt_builder.py          Prompt assembly from YAML templates
    prompts.yaml               11 prompt templates
    context_loader.py          Loads api/context/ Markdown files
    rag_loader.py              Loads generation/RAG/ reference documents
    pdf_extractor.py           PDF -> base64 (Gemini) or text (Groq/Claude)
    text_parsing.py            Code fence stripping, JSON extraction
    json_description_generation.py  Profile JSON parsing, validation, semantic guide
    profile_structure.py       Profile normalization, alias resolution, section scaffolding
    AAS_builder.py             Profile -> AAS JSON bridge
    validator.py               SHACL validation wrapper
    AAS_generation/
      cli/generate_aas.py      AASGenerator orchestrating all builders
      core/aas_builder.py      AAS shell builder
      core/element_factory.py  AAS element factory
      core/semantic_ids.py     Semantic ID catalog (30+ IDTA/W3C URIs)
      core/schema_handler.py   Interface schema processing
      submodels/               7 submodel builder classes
      guidance/                Pre-validation SHACL guidance for UI editors

  ontology/
    CSS-Ontology.ttl           Plattform I4.0 CSS ontology (Resource, Skill, Capability)
    CSSx.ttl                   Extension ontology importing all modules
    modules/
      cssx-nameplate.ttl       Digital nameplate domain model
      cssx-skills.ttl          Skill operations, modes, interface bindings
      cssx-capabilities.ttl    Capability extensions
      cssx-bom.ttl             Bill of materials
      cssx-resource-interface.ttl  Software/resource interfaces
      cssx-operational-data.ttl    Variable mappings
      cssx-parameters.ttl      Configuration parameters
      cssx-technical-data.ttl  Technical specifications
      cssx-resource-hierarchy.ttl  Resource composition
      cssx-aas-validation.ttl  Validation projection vocabulary + OWL constraints
    owl2shacl/
      owl2sh-semi-closed.ttl   OWL-to-SHACL transformation rules (default)

  shacl/
    generated/shapes.generated.shacl.ttl  Auto-derived from OWL axioms
    manual/resourceaas-sparql-rules.shacl.ttl  Hand-written SPARQL rules
    resourceaas-core.shacl.ttl              Mandatory submodel constraints
    resourceaas-dependencies.shacl.ttl      Cross-submodel dependency rules
    resourceaas-semantics.shacl.ttl         Semantic ID format validation
    resourceaas-bom.shacl.ttl               BoM structure rules

  tools/
    run_resourceaas_validation.py   Two-stage validation orchestrator
    validate_with_basyx.py          BaSyx metamodel validation
    mock_resourceaas_to_rdf.py      AAS JSON -> RDF projection
    generate_shapes_from_ontology.py  OWL -> SHACL offline derivation

  api/
    main.py                    FastAPI application (CORS, routers, health)
    routers/validate.py        POST /api/validate
    routers/context.py         GET /api/generate-context
    routers/generate_aas.py    POST /api/generate-aas (SSE), GET /api/generation-config
    context/
      00-preamble.md           AAS envelope rules, ID conventions, dependency rules
      shacl-rules.md           Human-readable SHACL constraint summary
      submodels/*.md           Per-submodel templates (nameplate, skills, etc.)

  aas_configs/
    imaDispensing.json         Example profile template (dispensing system)
    imaLoadingSystem.json      Example profile template (loading system)
```

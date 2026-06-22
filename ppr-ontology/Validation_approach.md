# Evaluation Implementation Plan

## Overview

This document describes how to implement the experimental evaluation for the ETFA paper on ontology-grounded LLM-based AAS generation. The goal is to produce the data needed for Tables I and II in the paper, answering three research questions:

- **RQ1 (Conformance):** What proportion of generated AAS instances achieve full SHACL conformance, and how does the feedback loop improve this?
- **RQ2 (Convergence):** How many retry iterations are needed to resolve validation violations?
- **RQ3 (Human effort):** What is the volume and nature of residual edits after the pipeline completes?

---

## 1. Experimental Matrix

### 1.1 Configurations to test

There are **three configurations** to compare:

| Config ID | Name | Description |
|-----------|------|-------------|
| `baseline_llm_only` | LLM-only | LLM generates full AAS JSON directly. No builder, no ontology validation, no retry. Use the `json` generation mode. Run the SHACL validator on the output *after the fact* to measure conformance, but do NOT feed violations back. |
| `baseline_builder` | Single-pass + builder | Use the `json-description` generation mode (profile → builder → AAS JSON). Run SHACL validation *after the fact* to measure conformance, but do NOT trigger the retry loop. One pass only. |
| `full_pipeline` | Full pipeline | Use the `json-description` mode with the full retry loop enabled (SHACL validation + feedback + retry up to `max_attempts`). This is the normal pipeline operation. |

### 1.2 Test matrix dimensions

- **Datasheets:** 10 components (see Section 2)
- **Providers:** 3 (Gemini, Groq/Llama, Claude)
- **Repetitions:** 5 per (datasheet, provider, config) combination
- **Submodels per run:** DigitalNameplate, HierarchicalStructures, AID

Total runs:
- `full_pipeline`: 10 × 3 × 5 = 150
- `baseline_builder`: 10 × 3 × 5 = 150
- `baseline_llm_only`: 10 × 3 × 5 = 150
- **Grand total: 450 runs**

> **Cost note:** The baselines are cheaper per run (no retries). Budget the full_pipeline runs at up to 5× the single-call cost due to retries. Consider running baselines with 3 repetitions instead of 5 if budget is tight (reducing to 10×3×3×2 + 150 = 330 total).

---

## 2. Dataset Preparation

### 2.1 Component selection

Select 10 components covering diverse asset types. For each, document:

| # | Component type | Manufacturer | Model | Input files | Notes |
|---|---------------|-------------|-------|-------------|-------|
| 1 | Proximity sensor | e.g. Pepperl+Fuchs | e.g. CA18CLC12BPM1 | PDF datasheet | Simple, few capabilities |
| 2 | Proximity sensor | different mfg | ... | PDF datasheet | Comparison within type |
| 3 | Motor drive | ... | ... | PDF datasheet | More complex nameplate |
| 4 | Motor drive | ... | ... | PDF + OPC UA NodeSet | Tests multi-source input |
| 5 | PLC module | ... | ... | PDF datasheet | |
| 6 | PLC module | ... | ... | PDF + PLC XML export | Tests multi-source input |
| 7 | I/O module | ... | ... | PDF datasheet | |
| 8 | I/O module | ... | ... | PDF datasheet | |
| 9 | Conveyor unit | ... | ... | PDF + integration doc | More complex system |
| 10 | Vision sensor | ... | ... | PDF datasheet | Different domain |

### 2.2 Ground truth preparation

For each component, a domain expert must prepare a **reference AAS profile** (the "gold standard") before running experiments. This is needed for RQ3 (human edit distance). The reference should contain:

- All fields filled correctly for DN, HS, AID submodels
- Correct semantic IDs
- Correct identifier formats
- No `[VERIFY]` markers (all values resolved)

Store these as JSON files alongside the datasheets:
```
evaluation/
  datasets/
    01_proximity_sensor_pf/
      datasheet.pdf
      reference_profile.json   # gold standard
      config.yaml              # asset_name, base_url, submodels list
    02_proximity_sensor_xx/
      ...
```

### 2.3 Config file per component

Each component needs a small config specifying the generation parameters:

```yaml
asset_name: "CA18CLC12BPM1"
base_url: "/aas"
submodels:
  - DigitalNameplate
  - HierarchicalStructures
  - AID
input_files:
  - datasheet.pdf
# optional:
#  - nodeset.xml
#  - plc_export.xml
```

---

## 3. Data Collection Per Run

### 3.1 What to log

Every single run must produce a structured log record. Create a JSON log file per run:

```json
{
  "run_id": "uuid",
  "timestamp": "ISO8601",
  "config": "full_pipeline | baseline_builder | baseline_llm_only",
  "component_id": "01_proximity_sensor_pf",
  "provider": "gemini | groq | claude",
  "model": "gemini-1.5-pro",
  "repetition": 1,
  "submodels": ["DigitalNameplate", "HierarchicalStructures", "AID"],

  "attempts": [
    {
      "attempt_number": 1,
      "profile_json": "path/to/profile_attempt_1.json",
      "aas_json": "path/to/aas_attempt_1.json",
      "rdf_turtle": "path/to/rdf_attempt_1.ttl",

      "metamodel_validation": {
        "conforms": false,
        "issues": [
          {"severity": "error", "message": "..."}
        ],
        "issue_count": 2
      },

      "ontology_validation": {
        "conforms": false,
        "issues": [
          {
            "severity": "Violation",
            "source_shape": "aasv:ResourceShape",
            "focus_node": "ex:resource",
            "message": "AID submodel must be present when Skills submodel exists",
            "path": "aasv:hasAIDSubmodel"
          }
        ],
        "issue_count": 1
      },

      "combined_conforms": false,
      "retry_message_sent": "Your profile JSON produced validation issues...",

      "generation_time_seconds": 45.2,
      "validation_time_seconds": 1.3,
      "input_tokens": 52000,
      "output_tokens": 3200
    },
    {
      "attempt_number": 2,
      "...": "..."
    }
  ],

  "final_result": {
    "conforms": true,
    "total_attempts": 2,
    "final_profile_json": "path/to/final_profile.json",
    "final_aas_json": "path/to/final_aas.json"
  },

  "verify_markers": {
    "total_count": 4,
    "by_field": [
      {"field": "DigitalNameplate.DateOfManufacture", "reason": "Not found in datasheet"},
      {"field": "AID.MQTTEndpoint", "reason": "No interface info in PDF"},
      {"field": "AID.MQTTPort", "reason": "No interface info in PDF"},
      {"field": "HierarchicalStructures.BoM.Entry2", "reason": "Uncertain sub-component"}
    ],
    "in_identifier_fields": 0
  },

  "errors": []
}
```

### 3.2 Implementation approach

The cleanest way is to wrap the existing pipeline in a test harness:

```
evaluation/
  run_evaluation.py       # main orchestrator
  configs/
    evaluation_matrix.yaml  # defines all (component, provider, config, rep) combos
  results/
    runs/                   # one JSON log per run
    artifacts/              # generated profiles, AAS JSONs, RDF files
  analysis/
    compute_metrics.py      # reads all run logs, produces tables
    generate_tables.py      # outputs LaTeX tables
```

**Key implementation points:**

1. **Wrap the existing pipeline call** so that it returns structured results rather than just the final AAS. You need access to per-attempt validation results and the retry messages.

2. **For `baseline_llm_only`:** Switch to `json` generation mode and set `max_attempts=1`. After generation, still run the SHACL validator to record conformance, but do not feed back.

3. **For `baseline_builder`:** Use `json-description` mode but set `max_attempts=1`. Same idea: validate after to record conformance, no retry.

4. **For `full_pipeline`:** Use `json-description` mode with `max_attempts=5` (or your default). This is the normal pipeline.

5. **Rate limiting:** Build in delays between calls. Use the provider cycling mechanism already in the pipeline. Log any rate limit events.

6. **Determinism:** Set temperature to the same value across all runs. Log the exact model string used.

7. **Error handling:** If a run fails entirely (API error, JSON parse failure, timeout), log it as a failed run with the error. Do not retry silently. These failures are data too.

---

## 4. Metric Computation

### 4.1 RQ1: Conformance

From the run logs, compute:

```python
# First-pass conformance: did attempt_number=1 pass?
first_pass_conforms = run["attempts"][0]["combined_conforms"]

# Final conformance: did the final result pass?
final_conforms = run["final_result"]["conforms"]
```

Aggregate into rates:

| Metric | Formula |
|--------|---------|
| First-pass conformance rate | `count(first_pass_conforms=True) / total_runs * 100` |
| Final conformance rate | `count(final_conforms=True) / total_runs * 100` |

Group by: config, provider, and overall.

### 4.2 RQ2: Convergence

Only for `full_pipeline` runs where `final_result.conforms == True`:

```python
iterations = run["final_result"]["total_attempts"]
```

Compute:
- Mean iterations to convergence
- Median iterations to convergence
- Distribution (histogram: how many runs converged at attempt 1, 2, 3, 4, 5)

Also compute for runs that did NOT converge:
- Count of non-converging runs
- Most common residual violations (group by violation message)

### 4.3 RQ3: Human effort

#### 4.3.1 VERIFY marker analysis

From the run logs:

```python
verify_count = run["verify_markers"]["total_count"]
verify_in_identifiers = run["verify_markers"]["in_identifier_fields"]  # should be 0
```

Compute:
- Mean VERIFY markers per run (by provider, overall)
- Breakdown by submodel (DN vs HS vs AID)
- Cases where VERIFY was used but the value was actually in the datasheet (= unnecessary marker, measure of LLM conservatism)
- Cases where a value was wrong but NOT marked with VERIFY (= undetected error, measure of LLM overconfidence)

The second and third points require comparison against the reference profile:

```python
for field in all_fields:
    generated_value = get_field(generated_profile, field)
    reference_value = get_field(reference_profile, field)

    if "[VERIFY" in str(generated_value):
        if reference_value_is_in_datasheet(field):
            category = "unnecessary_verify"  # LLM was too cautious
        else:
            category = "justified_verify"    # LLM correctly flagged
    elif generated_value != reference_value:
        category = "undetected_error"        # LLM was wrong without flagging
    else:
        category = "correct"                 # no issue
```

#### 4.3.2 Human edit distance

For the subset of 30 runs (10 per provider) reviewed by the domain expert:

1. Expert loads the final generated profile JSON
2. Expert corrects it to production quality, tracking every change
3. Each change is categorised:

| Category | Description |
|----------|-------------|
| `verify_resolution` | Expert filled in a `[VERIFY]` marked field |
| `factual_correction` | Expert corrected a confidently wrong value |
| `missing_value` | Expert added a value the LLM left empty (without VERIFY) |
| `semantic_id_fix` | Expert corrected a semantic identifier |
| `structural_fix` | Expert restructured a submodel section |

Compute:
- Total edits per run
- Edits as % of total fields
- Breakdown by category

**Tooling suggestion:** Build a simple diff tool that compares the generated profile against the expert-corrected profile field by field and auto-categorises changes. The expert then reviews and adjusts categories.

---

## 5. Output Artefacts

The analysis scripts should produce:

### 5.1 Table I: Conformance rates

```
| Configuration          | First-pass | Final  | Avg. Iter. |
|------------------------|-----------|--------|------------|
| LLM-only (no builder)  | X%        | X%     | N/A        |
| Single-pass + builder   | X%        | X%     | N/A        |
| Full pipeline - Gemini  | X%        | X%     | X.X        |
| Full pipeline - Groq    | X%        | X%     | X.X        |
| Full pipeline - Claude   | X%        | X%     | X.X        |
| Full pipeline (all)     | X%        | X%     | X.X        |
```

### 5.2 Table II: Human edit breakdown

```
| Edit Category        | Avg. Edits | % of Total Fields |
|---------------------|-----------|-------------------|
| [VERIFY] resolution | X         | X%                |
| Factual correction  | X         | X%                |
| Missing value       | X         | X%                |
| Semantic ID fix     | X         | X%                |
| Structural fix      | X         | X%                |
| Total               | X         | X%                |
```

### 5.3 Additional figures (optional but valuable)

- **Convergence histogram:** Bar chart showing number of runs converging at each attempt count (1, 2, 3, 4, 5, did not converge)
- **VERIFY calibration scatter:** Plot of "justified VERIFY" vs "undetected errors" per provider
- **Violation type frequency:** Bar chart of most common SHACL violations across all first-pass failures

---

## 6. Implementation Checklist

### Phase 1: Preparation
- [ ] Select and document 10 components with datasheets
- [ ] Create config.yaml for each component
- [ ] Prepare reference profiles (gold standard) for each component
- [ ] Set up evaluation directory structure

### Phase 2: Test harness
- [ ] Create `run_evaluation.py` that iterates over the evaluation matrix
- [ ] Modify pipeline to return structured per-attempt results (not just final output)
- [ ] Implement `baseline_llm_only` mode (json mode, max_attempts=1, validate after)
- [ ] Implement `baseline_builder` mode (json-description mode, max_attempts=1, validate after)
- [ ] Implement structured JSON logging per run
- [ ] Add VERIFY marker extraction and counting to the log
- [ ] Test with 1 component × 1 provider × 1 repetition before full run

### Phase 3: Execution
- [ ] Run full evaluation matrix (budget ~450 runs)
- [ ] Monitor for API errors, rate limits, timeouts
- [ ] Spot-check a few results manually during the run

### Phase 4: Analysis
- [ ] Implement `compute_metrics.py` to read all run logs
- [ ] Compute RQ1 metrics (conformance rates by config/provider)
- [ ] Compute RQ2 metrics (convergence distribution)
- [ ] Compute RQ3 metrics (VERIFY analysis, edit distance)
- [ ] Generate LaTeX table snippets
- [ ] Expert review of 30 runs for human edit distance

### Phase 5: Write-up
- [ ] Fill in Table I and Table II in the paper
- [ ] Write results narrative based on actual numbers
- [ ] Update abstract results sentence with actual findings
- [ ] Review threats to validity based on what actually happened

---

## 7. Practical Notes

- **Run time estimate:** At ~60s per attempt and up to 5 attempts for full_pipeline, expect ~75s average per full_pipeline run. 150 runs ≈ 3 hours. Baselines at ~60s each: 300 runs ≈ 5 hours. Total ≈ 8–10 hours, but can parallelise across providers.

- **Cost estimate:** Rough budget per run at ~80K input tokens + ~5K output tokens. At typical API pricing, expect $0.10–0.50 per run depending on provider. Full evaluation: $50–$200.

- **Reproducibility:** Save all generated artefacts (profiles, AAS JSONs, RDF files). Log the exact model version string. Record API response headers if they include model version info.

- **Failure modes to watch for:** JSON parse failures from the LLM (log these as generation failures); rate limit exhaustion mid-run (the pipeline's model cycling should handle this, but log it); timeout on very large datasheets.
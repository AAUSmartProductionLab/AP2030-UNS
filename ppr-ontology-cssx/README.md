# ppr-ontology-arso

A self-contained AAS-generation + ontology-validation pipeline built around
**`ARSO_AAS.ttl`** â€” a domain ontology that imports the official AAS v3.1
metamodel and adds ARSO subclasses (DigitalNameplateSubmodel, AIDSubmodel,
SkillsSubmodel, â€¦) typed by IDTA semantic IDs.

This repo is the publishable companion to the AP2030-UNS research paper.

## What's inside

```
ontology/             ARSO_AAS.ttl, AAS v3.1 OWL+SHACL (vendored), owl2shacl rules
shacl/generated/      Auto-derived ARSO SHACL shapes (regen with tools/generate_shapes.py)
tools/                aas_to_rdf.py serializer + SHACL regenerator
generation/           LLM-driven AAS generator + unified pyshacl validator
api/                  FastAPI backend (validate, generate-aas SSE stream, generation-config)
ui/                   Vue/React frontend (Vite, talks to /api/*)
evaluation/           Eval harness â€” equipment + ground truth + metrics + matrix runner
aas_configs/          Example AAS profiles (JSON)
```

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate          # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Regenerate ARSO SHACL shapes (only needed when ARSO_AAS.ttl changes)
python tools/generate_shapes.py

# Run the FastAPI backend
uvicorn api.main:app --reload --port 8000

# In another terminal, run the UI dev server
cd ui && npm install && npm run dev    # http://localhost:5173

# Run an evaluation experiment
python -m evaluation.run_eval --equipment ca18clc12bpm1 \
    --provider claude --ablation full \
    --output evaluation/results/run.jsonl
```

## How it works

1. **Profile JSON** â€” the LLM emits a small abstract profile (no semanticIds).
2. **Builder** â€” `generation.AAS_generation.cli.generate_aas.AASGenerator`
   converts profile â†’ full AAS JSON, stamping IDTA semanticIds on every
   submodel and mandatory SME from `core/semantic_ids.py` (single source of
   truth).
3. **Serializer** â€” `tools/aas_to_rdf.py` walks the AAS JSON and emits AAS-spec
   RDF (Reference / Key / LangStringTextType / AssetInformation as proper
   resources, not bare literals).
4. **Validator** â€” `generation/validator.py` does ONE `pyshacl.validate` call
   against `aas-shacl-schema.ttl` + `shapes.generated.shacl.ttl`, partitioning
   issues into "metamodel" (AAS-spec) vs "ontology" (ARSO domain) by source
   shape namespace.
5. **Retry loop** â€” `pipeline.run_pipeline` feeds violations back to the LLM
   up to `max_attempts` times.



#!/usr/bin/env bash
# package_v2.sh — gather every v2 component into a single sibling folder that
# can be lifted into its own git repo (the publishable companion to the paper).
#
# Usage:
#   bash package_v2.sh [DEST]
#
# DEST defaults to ../ppr-ontology-cssx (sibling of this repo). The script
# performs a one-way copy + import-path rewrite (`generation.v2.` -> `generation.`,
# `AAS_generation_v2` -> `AAS_generation`). Review the output manually, then
# `git init && git add . && git commit` inside DEST when ready.
#
# Idempotent: safe to re-run; existing files are overwritten.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR"
DEST="${1:-${SCRIPT_DIR}/../ppr-ontology-cssx}"

echo "→ Source: $SRC"
echo "→ Dest:   $DEST"
mkdir -p "$DEST"/{ontology,tools,generation,shacl,api,api/context}

echo "  ontology/ …"
cp  "$SRC/ontology/CSSx_AAS.ttl" \
    "$SRC/ontology/aas-rdf-ontology.ttl" \
    "$SRC/ontology/aas-shacl-schema.ttl" \
    "$SRC/ontology/catalog-v001.xml"  "$DEST/ontology/"
cp -r "$SRC/ontology/owl2shacl"      "$DEST/ontology/"

echo "  tools/ …"
cp  "$SRC/tools/aas_to_rdf.py" \
    "$SRC/tools/generate_shapes_from_ontology.py" \
    "$SRC/tools/generate_shapes_v2.py"  "$DEST/tools/"

echo "  shacl/ …"
mkdir -p "$DEST/shacl/generated"
cp "$SRC/shacl/generated_v2/shapes.generated.shacl.ttl" "$DEST/shacl/generated/"

echo "  generation/ — v2 sources flattened …"
# v2/ subfolder contents flattened to generation/ root in the package
cp  "$SRC/generation/v2/__init__.py"          "$DEST/generation/__init__.py"
cp  "$SRC/generation/v2/AAS_builder_v2.py"    "$DEST/generation/AAS_builder.py"
cp  "$SRC/generation/v2/validator_v2.py"      "$DEST/generation/validator.py"
cp  "$SRC/generation/v2/pipeline_v2.py"       "$DEST/generation/pipeline.py"

# AAS_generation_v2 → AAS_generation
mkdir -p "$DEST/generation/AAS_generation"/{core,submodels,cli}
cp  "$SRC/generation/v2/AAS_generation_v2/__init__.py"            "$DEST/generation/AAS_generation/__init__.py"
cp  "$SRC/generation/v2/AAS_generation_v2/core/__init__.py"       "$DEST/generation/AAS_generation/core/__init__.py"
cp  "$SRC/generation/v2/AAS_generation_v2/core/semantic_ids.py"   "$DEST/generation/AAS_generation/core/semantic_ids.py"
cp  "$SRC/generation/v2/AAS_generation_v2/core/element_factory.py" "$DEST/generation/AAS_generation/core/element_factory.py"
cp  "$SRC/generation/v2/AAS_generation_v2/core/aas_builder.py"    "$DEST/generation/AAS_generation/core/aas_builder.py"
cp  "$SRC/generation/v2/AAS_generation_v2/submodels/__init__.py"  "$DEST/generation/AAS_generation/submodels/__init__.py"
for f in "$SRC"/generation/v2/AAS_generation_v2/submodels/*.py; do
  cp "$f" "$DEST/generation/AAS_generation/submodels/$(basename "$f")"
done
cp  "$SRC/generation/v2/AAS_generation_v2/cli/__init__.py"        "$DEST/generation/AAS_generation/cli/__init__.py"
cp  "$SRC/generation/v2/AAS_generation_v2/cli/generate_aas.py"    "$DEST/generation/AAS_generation/cli/generate_aas.py"

# Subclassed-from-v1 helpers — copy v1 files into the package so the subclasses
# resolve. After the rewrite step below, the subclasses will reference the
# in-package copies.
cp  "$SRC/generation/AAS_generation/core/element_factory.py"   "$DEST/generation/AAS_generation/core/_v1_element_factory.py"
cp  "$SRC/generation/AAS_generation/core/aas_builder.py"       "$DEST/generation/AAS_generation/core/_v1_aas_builder.py"
cp  "$SRC/generation/AAS_generation/core/schema_handler.py"    "$DEST/generation/AAS_generation/core/schema_handler.py"
cp  "$SRC/generation/AAS_generation/core/semantic_ids.py"      "$DEST/generation/AAS_generation/core/_v1_semantic_ids.py"
for f in "$SRC"/generation/AAS_generation/submodels/*.py; do
  base="$(basename "$f")"
  if [ ! -f "$DEST/generation/AAS_generation/submodels/$base" ]; then
    cp "$f" "$DEST/generation/AAS_generation/submodels/$base"
  fi
done

# Shared helpers used by both v1 and v2
for f in profile_structure.py json_description_generation.py context_loader.py \
         config.py config.yaml prompts.yaml requirements.txt llm_client.py \
         prompt_builder.py rag_loader.py pdf_extractor.py text_parsing.py; do
  if [ -f "$SRC/generation/$f" ]; then
    cp "$SRC/generation/$f" "$DEST/generation/$f"
  fi
done
[ -d "$SRC/generation/RAG" ] && cp -r "$SRC/generation/RAG" "$DEST/generation/RAG"

echo "  api/ …"
cp -r "$SRC/api/context_v2/." "$DEST/api/context/"
mkdir -p "$DEST/api/routers"
cp "$SRC/api/routers/generate_aas.py" "$DEST/api/routers/generate_aas.py"
# Best-effort: copy any other non-router api files (validate.py, schema, etc.)
for f in "$SRC"/api/*.py "$SRC"/api/__init__.py; do
  [ -f "$f" ] || continue
  cp "$f" "$DEST/api/"
done
for f in "$SRC"/api/routers/*.py; do
  [ -f "$f" ] || continue
  base="$(basename "$f")"
  [ -f "$DEST/api/routers/$base" ] || cp "$f" "$DEST/api/routers/$base"
done

echo "  ui/ …"
[ -d "$SRC/ui" ] && cp -r "$SRC/ui" "$DEST/ui"

echo "→ Mechanical import-path rewrites …"
# generation.v2. → generation. ; AAS_generation_v2 → AAS_generation ; generation/v2/ → generation/
find "$DEST" -name "*.py" -print0 | xargs -0 -I{} sed -i \
    -e 's|generation\.v2\.AAS_generation_v2|generation.AAS_generation|g' \
    -e 's|generation\.v2\.|generation.|g' \
    -e 's|AAS_generation_v2|AAS_generation|g' \
    -e 's|AASGeneratorV2|AASGenerator|g' \
    -e 's|AASBuilderV2|AASBuilder|g' \
    -e 's|AASElementFactoryV2|AASElementFactory|g' \
    -e 's|SemanticIdFactoryV2|SemanticIdFactory|g' \
    -e 's|DigitalNameplateSubmodelBuilderV2|DigitalNameplateSubmodelBuilder|g' \
    -e 's|AssetInterfacesBuilderV2|AssetInterfacesBuilder|g' \
    -e 's|HierarchicalStructuresSubmodelBuilderV2|HierarchicalStructuresSubmodelBuilder|g' \
    -e 's|CapabilitiesSubmodelBuilderV2|CapabilitiesSubmodelBuilder|g' \
    -e 's|SkillsSubmodelBuilderV2|SkillsSubmodelBuilder|g' \
    -e 's|VariablesSubmodelBuilderV2|VariablesSubmodelBuilder|g' \
    -e 's|ParametersSubmodelBuilderV2|ParametersSubmodelBuilder|g' \
    -e 's|run_shacl_v2|run_shacl|g' \
    -e 's|pipeline_v2|pipeline|g' \
    -e 's|validator_v2|validator|g' \
    -e 's|AAS_builder_v2|AAS_builder|g' \
    {}

cat > "$DEST/README.md" <<'EOF'
# ppr-ontology-cssx

A self-contained AAS generation + validation package built around `CSSx_AAS.ttl`.

This folder is the publishable companion to the AP2030-UNS research paper. It
contains the v2 pipeline (semanticId-driven serialization, unified pyshacl
validation against AAS v3.1 + CSSx_AAS), generated from the parent repo via
`package_v2.sh`.

Quick start:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r generation/requirements.txt
python tools/generate_shapes_v2.py     # regenerate SHACL shapes from CSSx_AAS.ttl
python tools/aas_to_rdf.py --input <path/to/aas.json> --output out.ttl
```
EOF

echo "✓ Packaged v2 → $DEST"
echo "  Review the tree, then 'cd $DEST && git init && git add . && git commit'."

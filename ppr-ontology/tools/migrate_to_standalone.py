"""migrate_to_standalone.py — produce a clean self-contained `ppr-ontology-cssx/`
repo from the v2 components of this monorepo.

What the new repo contains:
  - The CSSx_AAS.ttl ontology stack + the AAS v3.1 vendored OWL/SHACL.
  - Auto-generated CSSx SHACL shapes.
  - tools/aas_to_rdf.py + tools/generate_shapes.py.
  - generation/ — pipeline, validator, builder, prompts, config (no v1/v2 dispatch).
  - generation/AAS_generation/ — flattened builders (v2 inheritance inlined into v1 bodies).
  - api/ — main, routers (validate/generate_aas/context), pydantic models.
  - api/context/ — IDTA-aligned LLM templates (was api/context_v2/).
  - ui/ — Vue/React frontend, entire tree minus node_modules / dist / .vite.
  - evaluation/ — eval harness, equipment + ground-truth + metrics + run_eval + plot.
  - aas_configs/ — example profile JSONs.
  - README.md, pyproject.toml, requirements.txt, .gitignore.

What it does NOT contain:
  - Anything `*_v2*` named (everything is dropped to plain v2 names since there's
    no v1 in the new repo).
  - The legacy tools/mock_resourceaas_to_rdf.py, ontology/CSS-Ontology.ttl,
    ontology/CSSx.ttl, ontology/modules/, shacl/manual/, shacl/generated/ —
    those are v1-only.
  - .venv, __pycache__, ide settings, OneDrive metadata.

Run from the repo root:
    python tools/migrate_to_standalone.py [DEST]
DEST defaults to `../ppr-ontology-cssx`.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------- copies


# (src, dst) — both relative to REPO and DEST respectively. Files only.
FILE_COPIES: list[tuple[str, str]] = [
    # Ontology layer
    ("ontology/CSSx_AAS.ttl",            "ontology/CSSx_AAS.ttl"),
    ("ontology/aas-rdf-ontology.ttl",    "ontology/aas-rdf-ontology.ttl"),
    ("ontology/aas-shacl-schema.ttl",    "ontology/aas-shacl-schema.ttl"),
    ("ontology/catalog-v001.xml",        "ontology/catalog-v001.xml"),

    # SHACL: the v2-generated shapes become THE shapes file in the new repo
    ("shacl/generated_v2/shapes.generated.shacl.ttl", "shacl/generated/shapes.generated.shacl.ttl"),

    # Tools
    ("tools/aas_to_rdf.py",                  "tools/aas_to_rdf.py"),
    ("tools/generate_shapes_from_ontology.py", "tools/generate_shapes_from_ontology.py"),
    ("tools/generate_shapes_v2.py",          "tools/generate_shapes.py"),

    # Generation: shared helpers (unchanged in v2)
    ("generation/llm_client.py",                  "generation/llm_client.py"),
    ("generation/context_loader.py",              "generation/context_loader.py"),
    ("generation/prompt_builder.py",              "generation/prompt_builder.py"),
    ("generation/rag_loader.py",                  "generation/rag_loader.py"),
    ("generation/pdf_extractor.py",               "generation/pdf_extractor.py"),
    ("generation/text_parsing.py",                "generation/text_parsing.py"),
    ("generation/profile_structure.py",           "generation/profile_structure.py"),
    ("generation/json_description_generation.py", "generation/json_description_generation.py"),
    ("generation/prompts.yaml",                   "generation/prompts.yaml"),

    # Generation: v2 modules → renamed to plain names
    ("generation/v2/AAS_builder_v2.py",  "generation/AAS_builder.py"),
    ("generation/v2/pipeline_v2.py",     "generation/pipeline.py"),
    ("generation/v2/validator_v2.py",    "generation/validator.py"),

    # AAS_generation v1 files that v2 just re-exports — copied wholesale
    ("generation/AAS_generation/core/aas_builder.py",      "generation/AAS_generation/core/aas_builder.py"),
    ("generation/AAS_generation/core/schema_handler.py",   "generation/AAS_generation/core/schema_handler.py"),
    ("generation/AAS_generation/submodels/capabilities_builder.py",            "generation/AAS_generation/submodels/capabilities_builder.py"),
    ("generation/AAS_generation/submodels/hierarchical_structures_builder.py", "generation/AAS_generation/submodels/hierarchical_structures_builder.py"),
    ("generation/AAS_generation/submodels/parameters_builder.py",              "generation/AAS_generation/submodels/parameters_builder.py"),
    ("generation/AAS_generation/submodels/process_submodels_builder.py",       "generation/AAS_generation/submodels/process_submodels_builder.py"),
    ("generation/AAS_generation/submodels/skills_builder.py",                  "generation/AAS_generation/submodels/skills_builder.py"),
    ("generation/AAS_generation/submodels/variables_builder.py",               "generation/AAS_generation/submodels/variables_builder.py"),

    # API: most files copy through; routers get rewritten below
    ("api/__init__.py",        "api/__init__.py"),
    ("api/main.py",            "api/main.py"),
    ("api/models.py",          "api/models.py"),
    ("api/routers/__init__.py","api/routers/__init__.py"),
    ("api/routers/context.py", "api/routers/context.py"),
]


# Whole directories to copy. Glob excludes are applied per-tree.
DIR_COPIES: list[tuple[str, str, list[str]]] = [
    # (src_dir, dst_dir, exclude_patterns)
    ("ontology/owl2shacl",       "ontology/owl2shacl",        []),
    ("generation/RAG",           "generation/RAG",            []),
    ("generation/AAS_generation/guidance", "generation/AAS_generation/guidance", []),
    ("aas_configs",              "aas_configs",               []),
    ("api/context_v2",           "api/context",               []),
    ("evaluation",               "evaluation",                ["__pycache__", "results", "_ablation_minimal_context"]),
    ("ui",                       "ui",                        ["node_modules", "dist", ".vite"]),
]


def _ignore(*excludes: str):
    def _f(_dir: str, names: list[str]) -> set[str]:
        out: set[str] = set()
        for n in names:
            if n in excludes or n in {"__pycache__", ".DS_Store"} or n.endswith(".pyc"):
                out.add(n)
        return out
    return _f


def _copy_files(dest: Path) -> None:
    for src_rel, dst_rel in FILE_COPIES:
        src = REPO / src_rel
        dst = dest / dst_rel
        if not src.exists():
            print(f"  SKIP (missing): {src_rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  copy  {src_rel}  →  {dst_rel}")


def _copy_dirs(dest: Path) -> None:
    for src_rel, dst_rel, excludes in DIR_COPIES:
        src = REPO / src_rel
        dst = dest / dst_rel
        if not src.exists():
            print(f"  SKIP (missing): {src_rel}/")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=_ignore(*excludes))
        print(f"  tree  {src_rel}/  →  {dst_rel}/")


# --------------------------------------------------------------------- flattening


# Flattened semantic_ids: drop the V2 subclass, mutate v1's class with corrected
# constants and the new property methods.
def _flatten_semantic_ids(dest: Path) -> None:
    src = (REPO / "generation/AAS_generation/core/semantic_ids.py").read_text(encoding="utf-8")
    out = src

    # Fix the broken submodel-level URLs.
    out = out.replace(
        '_DIGITAL_NAMEPLATE_SUBMODEL = "https://admin-shell.io/IDTA 02006-3-0"',
        '_DIGITAL_NAMEPLATE_SUBMODEL = "https://admin-shell.io/zvei/nameplate/2/0/Nameplate"',
    )
    out = out.replace(
        '_HIERARCHICAL_STRUCTURES = "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel"',
        '_HIERARCHICAL_STRUCTURES = "https://admin-shell.io/idta/HierarchicalStructures/1/0/Submodel"',
    )
    out = out.replace(
        '_SKILLS_SUBMODEL = "https://smartfactory.de/aas/submodel/Skills#1/0"',
        '_SKILLS_SUBMODEL = "https://smartproductionlab.aau.dk/CSSx/Skills/1/0/Submodel"',
    )
    out = out.replace(
        '_CAPABILITIES_SUBMODEL = "https://smartfactory.de/aas/submodel/Capabilities#1/0"',
        '_CAPABILITIES_SUBMODEL = "https://admin-shell.io/idta/CapabilityDescription/1/0"',
    )
    out = out.replace(
        '_VARIABLES_SUBMODEL = "https://admin-shell.io/idta/Variables/1/0/Submodel"',
        '_VARIABLES_SUBMODEL = "https://smartproductionlab.aau.dk/CSSx/OperationalData/1/0/Submodel"',
    )
    out = out.replace(
        '_PARAMETERS_SUBMODEL = "https://admin-shell.io/idta/Parameters/1/0/Submodel"',
        '_PARAMETERS_SUBMODEL = "https://smartproductionlab.aau.dk/CSSx/Parameters/1/0/Submodel"',
    )

    # Splice in the new SME-level constants and properties just before the
    # static helper at the bottom of the class.
    insertion = '''
    # --- Mandatory Nameplate SMEs (per IDTA 02006) ---
    _NP_MANUFACTURER_NAME                = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate/ManufacturerName"
    _NP_MANUFACTURER_PRODUCT_DESIGNATION = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate/ManufacturerProductDesignation"
    _NP_CONTACT_INFORMATION              = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate/ContactInformation"
    _NP_ORDER_CODE_OF_MANUFACTURER       = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate/OrderCodeOfManufacturer"
    _AID_ENDPOINT_METADATA               = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/EndpointMetadata"

    @property
    def NP_MANUFACTURER_NAME(self) -> model.ExternalReference:
        return self.create_external_reference(self._NP_MANUFACTURER_NAME)

    @property
    def NP_MANUFACTURER_PRODUCT_DESIGNATION(self) -> model.ExternalReference:
        return self.create_external_reference(self._NP_MANUFACTURER_PRODUCT_DESIGNATION)

    @property
    def NP_CONTACT_INFORMATION(self) -> model.ExternalReference:
        return self.create_external_reference(self._NP_CONTACT_INFORMATION)

    @property
    def NP_ORDER_CODE_OF_MANUFACTURER(self) -> model.ExternalReference:
        return self.create_external_reference(self._NP_ORDER_CODE_OF_MANUFACTURER)

    @property
    def AID_ENDPOINT_METADATA(self) -> model.ExternalReference:
        return self.create_external_reference(self._AID_ENDPOINT_METADATA)

'''
    out = out.replace("    @staticmethod\n    def create_external_reference",
                      insertion + "    @staticmethod\n    def create_external_reference",
                      1)

    # Append module-level string constants for direct import by tools/aas_to_rdf.py
    constants_block = '''

# --- Module-level constants (importable without instantiating the factory) ---

SM_NAMEPLATE                = SemanticIdFactory._DIGITAL_NAMEPLATE_SUBMODEL
SM_HIERARCHICAL_STRUCTURES  = SemanticIdFactory._HIERARCHICAL_STRUCTURES
SM_ASSET_INTERFACES         = SemanticIdFactory._ASSET_INTERFACES_SUBMODEL
SM_CAPABILITIES             = SemanticIdFactory._CAPABILITIES_SUBMODEL
SM_SKILLS                   = SemanticIdFactory._SKILLS_SUBMODEL
SM_OPERATIONAL_DATA         = SemanticIdFactory._VARIABLES_SUBMODEL
SM_PARAMETERS               = SemanticIdFactory._PARAMETERS_SUBMODEL

NP_MANUFACTURER_NAME                = SemanticIdFactory._NP_MANUFACTURER_NAME
NP_MANUFACTURER_PRODUCT_DESIGNATION = SemanticIdFactory._NP_MANUFACTURER_PRODUCT_DESIGNATION
NP_CONTACT_INFORMATION              = SemanticIdFactory._NP_CONTACT_INFORMATION
NP_ORDER_CODE_OF_MANUFACTURER       = SemanticIdFactory._NP_ORDER_CODE_OF_MANUFACTURER

HS_ARCHETYPE  = SemanticIdFactory._HIERARCHICAL_ARCHETYPE
HS_ENTRY_NODE = SemanticIdFactory._HIERARCHICAL_ENTRY_NODE

AID_INTERFACE             = SemanticIdFactory._ASSET_INTERFACES_INTERFACE
AID_ENDPOINT_METADATA     = SemanticIdFactory._AID_ENDPOINT_METADATA
AID_INTERACTION_METADATA  = SemanticIdFactory._ASSET_INTERFACES_INTERACTION
'''
    out = out + constants_block

    target = dest / "generation/AAS_generation/core/semantic_ids.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(out, encoding="utf-8")
    print(f"  flat  generation/AAS_generation/core/semantic_ids.py")


# Flattened element_factory: copy v1, splice in the SME-required guard.
def _flatten_element_factory(dest: Path) -> None:
    src = (REPO / "generation/AAS_generation/core/element_factory.py").read_text(encoding="utf-8")

    guard_block = '''

_REQUIRES_SEMANTIC_ID: set[str] = {
    "ManufacturerName",
    "ManufacturerProductDesignation",
    "ContactInformation",
    "OrderCodeOfManufacturer",
    "EndpointMetadata",
}


def _require_semantic_id(id_short, semantic_id):
    if id_short in _REQUIRES_SEMANTIC_ID and semantic_id is None:
        raise ValueError(
            f"AAS_generation: SME '{id_short}' requires a semanticId. "
            f"Pass semantic_id=SemanticIdFactory().<XXX>. See semantic_ids.py."
        )

'''
    # Insert just before `class AASElementFactory`.
    out = src.replace("class AASElementFactory:", guard_block + "class AASElementFactory:")

    # Add `_require_semantic_id(id_short, semantic_id)` at the top of three methods.
    for fn_signature in (
        "    def create_property(",
        "    def create_multi_language_property(",
        "    def create_collection(",
    ):
        # Find the function header, find the first non-blank line of its body
        # (after the docstring), and insert the guard call.
        marker = fn_signature
        idx = out.find(marker)
        if idx == -1:
            continue
        # Find the closing `):` then `"""...` docstring or first executable line.
        body_start = out.find("\n", idx) + 1
        # Walk lines until we find the first executable (not a `def`/`@`/docstring quote/empty).
        # Find docstring open
        rest = out[body_start:]
        # Find next executable line: skip leading lines that are part of param continuation,
        # the `):` or `) -> ...:` line, then the docstring.
        # Simpler: locate the next line that starts with `        # Auto-detect`,
        # `        kwargs = {`, `        kwargs[`, `        return ...` — the actual logic.
        m = re.search(r"\n        (kwargs|# Auto|return)", rest)
        if not m:
            continue
        insert_at = body_start + m.start() + 1  # position of the matched leading spaces
        guard_call = "        _require_semantic_id(id_short, semantic_id)\n"
        out = out[:insert_at] + guard_call + out[insert_at:]

    target = dest / "generation/AAS_generation/core/element_factory.py"
    target.write_text(out, encoding="utf-8")
    print(f"  flat  generation/AAS_generation/core/element_factory.py")


# Flattened nameplate_builder: take the v2 build() body, but drop the v2
# subclass header — it's now THE builder.
def _flatten_nameplate_builder(dest: Path) -> None:
    v2 = (REPO / "generation/v2/AAS_generation_v2/submodels/nameplate_builder.py").read_text(encoding="utf-8")
    # Replace the import + class header to reference the local v1 base class
    # (which we copied to AAS_generation/submodels/...) and rename the class.
    out = v2.replace(
        "from generation.AAS_generation.submodels.nameplate_builder import (\n    DigitalNameplateSubmodelBuilder,\n)\n",
        "",
    )
    out = out.replace(
        "class DigitalNameplateSubmodelBuilderV2(DigitalNameplateSubmodelBuilder):",
        "class DigitalNameplateSubmodelBuilder:",
    )
    # The v2 class only overrides build(); add the v1 __init__ inline so the
    # flat class is self-contained.
    out = out.replace(
        "class DigitalNameplateSubmodelBuilder:\n",
        "class DigitalNameplateSubmodelBuilder:\n"
        '    """DigitalNameplate submodel builder — IDTA 02006 aligned, basyx SDK based."""\n\n'
        "    def __init__(self, base_url: str, semantic_factory, element_factory):\n"
        "        self.base_url = base_url\n"
        "        self.semantic_factory = semantic_factory\n"
        "        self.element_factory = element_factory\n\n",
        1,
    )
    target = dest / "generation/AAS_generation/submodels/nameplate_builder.py"
    target.write_text(out, encoding="utf-8")
    print(f"  flat  generation/AAS_generation/submodels/nameplate_builder.py")


# Flattened asset_interfaces_builder: copy v1 wholesale, then patch the
# `_create_mqtt_endpoint_metadata` method body to attach AID_ENDPOINT_METADATA.
def _flatten_asset_interfaces_builder(dest: Path) -> None:
    v1 = (REPO / "generation/AAS_generation/submodels/asset_interfaces_builder.py").read_text(encoding="utf-8")
    # Replace the v1 method's create_collection call (no semantic_id) with one
    # that passes self.semantic_factory.AID_ENDPOINT_METADATA.
    patched = v1.replace(
        '        return self.element_factory.create_collection(\n            id_short="EndpointMetadata",\n            elements=endpoint_elements\n        )',
        '        return self.element_factory.create_collection(\n'
        '            id_short="EndpointMetadata",\n'
        '            elements=endpoint_elements,\n'
        '            semantic_id=self.semantic_factory.AID_ENDPOINT_METADATA,\n'
        '        )',
    )
    if patched == v1:
        print("  WARN: asset_interfaces_builder patch didn't match; manual review needed")
    target = dest / "generation/AAS_generation/submodels/asset_interfaces_builder.py"
    target.write_text(patched, encoding="utf-8")
    print(f"  flat  generation/AAS_generation/submodels/asset_interfaces_builder.py")


# Flattened cli/generate_aas: take v1, no V2 subclass needed since the
# semantic_ids/element_factory/nameplate/aid builders in this repo already ARE
# the v2 versions. Just copy v1 verbatim — its imports point at
# `..core.AASElementFactory` and `..submodels.DigitalNameplateSubmodelBuilder`,
# both of which are already v2-shape in this new repo.
def _flatten_cli_generate_aas(dest: Path) -> None:
    v1 = (REPO / "generation/AAS_generation/cli/generate_aas.py").read_text(encoding="utf-8")
    target = dest / "generation/AAS_generation/cli/generate_aas.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(v1, encoding="utf-8")
    print(f"  flat  generation/AAS_generation/cli/generate_aas.py")


# --------------------------------------------------------------------- cleaned files


_INIT_AAS_GENERATION = """# Re-export the v2-aligned generator for `from generation.AAS_generation import main`.
try:
    from .cli.generate_aas import main  # type: ignore[import-not-found]
except ImportError:
    main = None  # type: ignore[assignment]
"""

_INIT_CORE = """from .element_factory import AASElementFactory
from .schema_handler import SchemaHandler
from .semantic_ids import SemanticIdFactory
from .aas_builder import AASBuilder

__all__ = ["AASElementFactory", "SchemaHandler", "SemanticIdFactory", "AASBuilder"]
"""

_INIT_SUBMODELS = """from .asset_interfaces_builder import AssetInterfacesBuilder
from .variables_builder import VariablesSubmodelBuilder
from .skills_builder import SkillsSubmodelBuilder
from .parameters_builder import ParametersSubmodelBuilder
from .hierarchical_structures_builder import HierarchicalStructuresSubmodelBuilder
from .capabilities_builder import CapabilitiesSubmodelBuilder
from .nameplate_builder import DigitalNameplateSubmodelBuilder
from .process_submodels_builder import (
    ProcessInformationSubmodelBuilder,
    RequiredCapabilitiesSubmodelBuilder,
    PolicySubmodelBuilder,
)

__all__ = [
    "AssetInterfacesBuilder",
    "VariablesSubmodelBuilder",
    "SkillsSubmodelBuilder",
    "ParametersSubmodelBuilder",
    "HierarchicalStructuresSubmodelBuilder",
    "CapabilitiesSubmodelBuilder",
    "DigitalNameplateSubmodelBuilder",
    "ProcessInformationSubmodelBuilder",
    "RequiredCapabilitiesSubmodelBuilder",
    "PolicySubmodelBuilder",
]
"""

_INIT_CLI = """from .generate_aas import AASGenerator, main

__all__ = ["AASGenerator", "main"]
"""


_INIT_GENERATION = '''"""Generation pipeline — v2 (CSSx_AAS + IDTA semanticIds + unified pyshacl)."""
'''


def _write_init_files(dest: Path) -> None:
    inits = {
        "generation/__init__.py":                          _INIT_GENERATION,
        "generation/AAS_generation/__init__.py":           _INIT_AAS_GENERATION,
        "generation/AAS_generation/core/__init__.py":      _INIT_CORE,
        "generation/AAS_generation/submodels/__init__.py": _INIT_SUBMODELS,
        "generation/AAS_generation/cli/__init__.py":       _INIT_CLI,
    }
    for rel, content in inits.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  init  {rel}")


# Cleaned config.py: drop validation_profile + v2 context_dir branching.
def _clean_config_py(dest: Path) -> None:
    src = (REPO / "generation/config.py").read_text(encoding="utf-8")
    out = src

    # Drop the validation_profile field from the dataclass.
    out = re.sub(
        r"\n    # Validation profile:.*?\n    validation_profile: str = \"v2\"\n",
        "\n",
        out,
        flags=re.DOTALL,
    )

    # Drop the validation block read from yaml + the validation_profile arg in load_config().
    out = re.sub(
        r"    validation_cfg = raw\.get\(\"validation\", \{\}\) if isinstance\(raw, dict\) else \{\}\n"
        r"    validation_profile = str\(validation_cfg\.get\(\"profile\", \"v2\"\)\)\.strip\(\)\.lower\(\)\n"
        r"    if validation_profile not in \{\"v1\", \"v2\"\}:\n"
        r"        sys\.exit\(\"ERROR: validation\.profile must be 'v1' or 'v2'\.\"\)\n",
        "",
        out,
    )
    out = out.replace(
        "        validation_profile = validation_profile,\n",
        "",
    )

    # Simplify context_dir back to api/context (no more conditional v2 path).
    out = re.sub(
        r"        # v2 \+ json mode → context_v2/.*?else _ROOT / \"api\" / \"context\"\n        \),\n",
        '        context_dir   = _ROOT / "api" / "context",\n',
        out,
        flags=re.DOTALL,
    )

    target = dest / "generation/config.py"
    target.write_text(out, encoding="utf-8")
    print(f"  clean generation/config.py")


# Cleaned config.yaml: drop the validation: block.
def _clean_config_yaml(dest: Path) -> None:
    src = (REPO / "generation/config.yaml").read_text(encoding="utf-8")
    out = re.sub(
        r"\n# -- Validation profile.*?validation:\n  profile: v2\n",
        "\n",
        src,
        flags=re.DOTALL,
    )
    target = dest / "generation/config.yaml"
    target.write_text(out, encoding="utf-8")
    print(f"  clean generation/config.yaml")


# Cleaned api/routers/generate_aas.py: drop _select_pipeline / v1 dispatch.
def _clean_router_generate_aas(dest: Path) -> None:
    src = (REPO / "api/routers/generate_aas.py").read_text(encoding="utf-8")
    out = src
    out = out.replace(
        "from generation.pipeline import run_pipeline as run_pipeline_v1\n"
        "from generation.v2.pipeline_v2 import run_pipeline as run_pipeline_v2\n"
        "\n"
        "\n"
        "def _select_pipeline(cfg: \"Config\"):\n"
        "    \"\"\"Return the run_pipeline callable for the active validation.profile.\"\"\"\n"
        "    profile = getattr(cfg, \"validation_profile\", \"v2\")\n"
        "    if profile == \"v1\":\n"
        "        return run_pipeline_v1\n"
        "    return run_pipeline_v2\n"
        "\n"
        "\n"
        "# Default `run_pipeline` — kept for any legacy callers that bypass cfg dispatch.\n"
        "run_pipeline = run_pipeline_v2\n",
        "from generation.pipeline import run_pipeline\n",
    )
    out = out.replace(
        "            run_pipeline_fn = _select_pipeline(cfg)\n"
        "            aas_json, conforms, issues, attempts = run_pipeline_fn(",
        "            aas_json, conforms, issues, attempts = run_pipeline(",
    )
    # Drop the validation_profile=base_cfg.validation_profile arg from the
    # Config(...) call site we patched earlier.
    out = out.replace(
        "        validation_profile=base_cfg.validation_profile,\n",
        "",
    )
    target = dest / "api/routers/generate_aas.py"
    target.write_text(out, encoding="utf-8")
    print(f"  clean api/routers/generate_aas.py")


# Cleaned api/routers/validate.py: keep ONLY the v2 path, drop _validate_v1 +
# _active_profile dispatch.
_VALIDATE_PY = '''"""POST /api/validate

Accepts AAS JSON, runs unified pyshacl validation (AAS metamodel SHACL +
auto-derived CSSx domain shapes), returns structured issues. Each issue
includes a `field` dot-path so the UI can route it to the right wizard step.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from api.models import ValidateRequest, ValidateResponse, ValidationIssue  # noqa: E402
from generation.validator import run_shacl  # noqa: E402

router = APIRouter()


_MESSAGE_TO_FIELD: list[tuple[re.Pattern, str]] = [
    (re.compile(r"DigitalNameplate submodel is mandatory",          re.I), "DigitalNameplate"),
    (re.compile(r"HierarchicalStructures.*submodel is mandatory",   re.I), "HierarchicalStructures"),
    (re.compile(r"AID submodel must be present",                    re.I), "AID"),
    (re.compile(r"SoftwareInterface must be present",               re.I), "AID"),
    (re.compile(r"ResourceInterface must be mapped",                re.I), "AID.InterfaceMQTT"),
    (re.compile(r"SkillInterface.*must use.*ResourceInterface",     re.I), "Skills"),
    (re.compile(r"exactly one SkillInterface",                      re.I), "Skills"),
    (re.compile(r"Skills submodel.*Capabilities submodel",          re.I), "Capabilities"),
    (re.compile(r"Capabilities submodel.*Skills submodel",          re.I), "Skills"),
    (re.compile(r"provides Skills.*must provide.*Capabilit",        re.I), "Capabilities"),
    (re.compile(r"provides Capabilit.*must provide.*Skill",         re.I), "Skills"),
    (re.compile(r"Capabilit.*isRealizedBySkill",                    re.I), "Capabilities"),
    (re.compile(r"serialNumber.*manufacturerName",                  re.I), "DigitalNameplate"),
    (re.compile(r"HierarchicalStructures.*Name is required",        re.I), "HierarchicalStructures.Name"),
    (re.compile(r"BoM entity.*globalAssetId",                       re.I), "HierarchicalStructures"),
    (re.compile(r"Archetype.*no entity entries",                    re.I), "HierarchicalStructures"),
    (re.compile(r"sourceSemanticId.*capabilit",                     re.I), "Capabilities"),
    (re.compile(r"sourceSemanticId.*skill",                         re.I), "Skills"),
    (re.compile(r"yearOfConstruction",                              re.I), "DigitalNameplate.YearOfConstruction"),
    (re.compile(r"dateOfManufacture",                               re.I), "DigitalNameplate.DateOfManufacture"),
    (re.compile(r"serialNumber",                                    re.I), "DigitalNameplate.SerialNumber"),
    (re.compile(r"manufacturerName",                                re.I), "DigitalNameplate.ManufacturerName"),
    (re.compile(r"ManufacturerName",                                re.I), "DigitalNameplate.ManufacturerName"),
    (re.compile(r"ContactInformation",                              re.I), "DigitalNameplate"),
    (re.compile(r"OrderCodeOfManufacturer",                         re.I), "DigitalNameplate"),
]


def _map_message_to_field(message: str) -> str:
    for pattern, field in _MESSAGE_TO_FIELD:
        if pattern.search(message):
            return field
    return ""


@router.post("/validate", response_model=ValidateResponse)
async def validate_aas(req: ValidateRequest) -> ValidateResponse:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        try:
            conforms, all_issues, _meta, _onto = run_shacl(req.json_text, tmp)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"validation error: {exc}")

        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        for issue in all_issues:
            message = issue.get("message", "No message")
            if message in seen:
                continue
            seen.add(message)
            issues.append(ValidationIssue(
                severity=issue.get("severity", "Violation"),
                message=message,
                field=_map_message_to_field(message),
                focus_node=issue.get("focus_node") or None,
                result_path=None,
            ))

        report_path = tmp / "report.ttl"
        report_ttl_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""

    return ValidateResponse(conforms=conforms, issues=issues, report_ttl=report_ttl_text)
'''


def _clean_router_validate(dest: Path) -> None:
    target = dest / "api/routers/validate.py"
    target.write_text(_VALIDATE_PY, encoding="utf-8")
    print(f"  clean api/routers/validate.py")


# Cleaned validator.py: it currently lives at generation/v2/validator_v2.py and
# imports from `tools.aas_to_rdf`. Point all paths at the new layout
# (generation_v2 → no longer exists; references shacl/generated_v2 → shacl/generated).
def _clean_validator(dest: Path) -> None:
    target = dest / "generation/validator.py"
    src = target.read_text(encoding="utf-8")
    out = src.replace("shacl/generated_v2", "shacl/generated")
    # Re-export the function under its public name `run_shacl` (drop the v2 suffix).
    out = out.replace("def run_shacl_v2(", "def run_shacl(")
    # Path resolution moved up one level (was generation/v2/validator_v2.py).
    out = out.replace(
        "_REPO_ROOT = Path(__file__).resolve().parent.parent.parent",
        "_REPO_ROOT = Path(__file__).resolve().parent.parent",
    )
    out = out + "\n\n# Backwards-compatibility alias retained for any local debug scripts:\nrun_shacl_v2 = run_shacl\n"
    target.write_text(out, encoding="utf-8")
    print(f"  clean generation/validator.py")


# pipeline.py — drops the v2 import paths AND the extra `..` from when this
# file lived two levels deep at `generation/v2/pipeline_v2.py`.
def _clean_pipeline(dest: Path) -> None:
    target = dest / "generation/pipeline.py"
    src = target.read_text(encoding="utf-8")
    out = src
    out = out.replace("from .AAS_builder_v2 import profile_json_text_to_aas_json", "from .AAS_builder import profile_json_text_to_aas_json")
    out = out.replace("from .validator_v2 import run_shacl_v2 as run_shacl", "from .validator import run_shacl")
    # Lift relative imports up one level (was generation/v2/pipeline_v2.py).
    out = out.replace("from ..config import Config", "from .config import Config")
    out = out.replace("from ..json_description_generation import", "from .json_description_generation import")
    out = out.replace("from ..llm_client import call_llm", "from .llm_client import call_llm")
    out = out.replace("from ..prompt_builder import build_retry_message", "from .prompt_builder import build_retry_message")
    out = out.replace("from ..text_parsing import", "from .text_parsing import")
    target.write_text(out, encoding="utf-8")
    print(f"  clean generation/pipeline.py")


# AAS_builder.py — drop the v2 paths AND lift relative imports.
def _clean_aas_builder(dest: Path) -> None:
    target = dest / "generation/AAS_builder.py"
    src = target.read_text(encoding="utf-8")
    out = src.replace("from .AAS_generation_v2.cli.generate_aas import AASGenerator",
                      "from .AAS_generation.cli.generate_aas import AASGenerator")
    out = out.replace("from ..config import Config", "from .config import Config")
    out = out.replace("from ..profile_structure import", "from .profile_structure import")
    out = out.replace("from ..text_parsing import", "from .text_parsing import")
    target.write_text(out, encoding="utf-8")
    print(f"  clean generation/AAS_builder.py")


# tools/aas_to_rdf.py — fix the v2 path imports.
def _clean_tools_aas_to_rdf(dest: Path) -> None:
    target = dest / "tools/aas_to_rdf.py"
    src = target.read_text(encoding="utf-8")
    out = src.replace(
        "from generation.v2.AAS_generation_v2.core.semantic_ids import",
        "from generation.AAS_generation.core.semantic_ids import",
    )
    target.write_text(out, encoding="utf-8")
    print(f"  clean tools/aas_to_rdf.py")


# tools/generate_shapes.py — produces shacl/generated/ now (was generated_v2).
def _clean_tools_generate_shapes(dest: Path) -> None:
    target = dest / "tools/generate_shapes.py"
    src = target.read_text(encoding="utf-8")
    out = src.replace("shacl/generated_v2", "shacl/generated")
    target.write_text(out, encoding="utf-8")
    print(f"  clean tools/generate_shapes.py")


# evaluation/run_eval.py — drop the v1/v2 dispatch; keep only the v2 import.
def _clean_evaluation(dest: Path) -> None:
    target = dest / "evaluation/run_eval.py"
    if not target.exists():
        return
    src = target.read_text(encoding="utf-8")
    out = src
    out = out.replace(
        "from generation.v2.pipeline_v2 import run_pipeline as run_pipeline_v2  # noqa: E402\n"
        "from generation.pipeline import run_pipeline as run_pipeline_v1  # noqa: E402\n",
        "from generation.pipeline import run_pipeline  # noqa: E402\n",
    )
    out = out.replace(
        "    runner = run_pipeline_v1 if pipeline == \"v1\" else run_pipeline_v2",
        "    runner = run_pipeline",
    )
    target.write_text(out, encoding="utf-8")
    print(f"  clean evaluation/run_eval.py")


# --------------------------------------------------------------------- project metadata


_README = """# ppr-ontology-cssx

A self-contained AAS-generation + ontology-validation pipeline built around
**`CSSx_AAS.ttl`** — a domain ontology that imports the official AAS v3.1
metamodel and adds CSSx subclasses (DigitalNameplateSubmodel, AIDSubmodel,
SkillsSubmodel, …) typed by IDTA semantic IDs.

This repo is the publishable companion to the AP2030-UNS research paper.

## What's inside

```
ontology/             CSSx_AAS.ttl, AAS v3.1 OWL+SHACL (vendored), owl2shacl rules
shacl/generated/      Auto-derived CSSx SHACL shapes (regen with tools/generate_shapes.py)
tools/                aas_to_rdf.py serializer + SHACL regenerator
generation/           LLM-driven AAS generator + unified pyshacl validator
api/                  FastAPI backend (validate, generate-aas SSE stream, generation-config)
ui/                   Vue/React frontend (Vite, talks to /api/*)
evaluation/           Eval harness — equipment + ground truth + metrics + matrix runner
aas_configs/          Example AAS profiles (JSON)
```

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate          # or .venv\\Scripts\\activate on Windows
pip install -r requirements.txt

# Regenerate CSSx SHACL shapes (only needed when CSSx_AAS.ttl changes)
python tools/generate_shapes.py

# Run the FastAPI backend
uvicorn api.main:app --reload --port 8000

# In another terminal, run the UI dev server
cd ui && npm install && npm run dev    # http://localhost:5173

# Run an evaluation experiment
python -m evaluation.run_eval --equipment ca18clc12bpm1 \\
    --provider claude --ablation full \\
    --output evaluation/results/run.jsonl
```

## How it works

1. **Profile JSON** — the LLM emits a small abstract profile (no semanticIds).
2. **Builder** — `generation.AAS_generation.cli.generate_aas.AASGenerator`
   converts profile → full AAS JSON, stamping IDTA semanticIds on every
   submodel and mandatory SME from `core/semantic_ids.py` (single source of
   truth).
3. **Serializer** — `tools/aas_to_rdf.py` walks the AAS JSON and emits AAS-spec
   RDF (Reference / Key / LangStringTextType / AssetInformation as proper
   resources, not bare literals).
4. **Validator** — `generation/validator.py` does ONE `pyshacl.validate` call
   against `aas-shacl-schema.ttl` + `shapes.generated.shacl.ttl`, partitioning
   issues into "metamodel" (AAS-spec) vs "ontology" (CSSx domain) by source
   shape namespace.
5. **Retry loop** — `pipeline.run_pipeline` feeds violations back to the LLM
   up to `max_attempts` times.
"""


_PYPROJECT = '''[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ppr-ontology-cssx"
version = "0.1.0"
description = "AAS generation + CSSx ontology validation pipeline"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "rdflib>=7.0.0",
  "pyshacl>=0.27.0",
  "basyx-python-sdk>=1.2.1,<2.0.0",
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "pydantic>=2.5",
  "pyyaml>=6.0",
  "openai>=1.40.0",
  "google-genai>=0.7.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["api*", "generation*", "tools*", "evaluation*"]
'''


_REQUIREMENTS = """rdflib>=7.0.0
pyshacl>=0.27.0
basyx-python-sdk>=1.2.1,<2.0.0
fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.5
pyyaml>=6.0
openai>=1.40.0
google-genai>=0.7.0
"""


_GITIGNORE = """# Python
.venv/
__pycache__/
*.pyc
*.pyo
*.egg-info/
build/
dist/

# Editor / OS
.idea/
.vscode/
.DS_Store
Thumbs.db

# Project
generation/output/
evaluation/results/
ui/node_modules/
ui/dist/
ui/.vite/

# Secrets — your config.yaml has API keys; copy it to config.local.yaml before publishing
"""


def _write_project_metadata(dest: Path) -> None:
    (dest / "README.md").write_text(_README, encoding="utf-8")
    (dest / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (dest / "requirements.txt").write_text(_REQUIREMENTS, encoding="utf-8")
    (dest / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    print(f"  meta  README.md / pyproject.toml / requirements.txt / .gitignore")


# --------------------------------------------------------------------- main


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("dest", nargs="?", default=str(REPO.parent / "ppr-ontology-cssx"))
    args = p.parse_args()

    dest = Path(args.dest).resolve()
    print(f"Migrating v2 components → {dest}")
    if dest.exists():
        print(f"  (wiping existing {dest})")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    print("\n[1/6] wholesale file copies")
    _copy_files(dest)

    print("\n[2/6] wholesale directory copies")
    _copy_dirs(dest)

    print("\n[3/6] flatten v2-subclasses-v1 builders")
    _flatten_semantic_ids(dest)
    _flatten_element_factory(dest)
    _flatten_nameplate_builder(dest)
    _flatten_asset_interfaces_builder(dest)
    _flatten_cli_generate_aas(dest)

    print("\n[4/6] write package __init__.py files")
    _write_init_files(dest)

    print("\n[5/6] clean v1/v2 dispatch out of routers, config, pipeline, tools, eval")
    _clean_config_py(dest)
    _clean_config_yaml(dest)
    _clean_router_generate_aas(dest)
    _clean_router_validate(dest)
    _clean_pipeline(dest)
    _clean_validator(dest)
    _clean_aas_builder(dest)
    _clean_tools_aas_to_rdf(dest)
    _clean_tools_generate_shapes(dest)
    _clean_evaluation(dest)

    print("\n[6/6] project metadata")
    _write_project_metadata(dest)

    print(f"\nDone. Standalone repo at: {dest}")
    print("Next steps:")
    print(f"  cd {dest}")
    print("  python -m venv .venv && . .venv/Scripts/activate")
    print("  pip install -r requirements.txt")
    print("  python tools/generate_shapes.py     # regenerate shapes from CSSx_AAS.ttl")
    print("  uvicorn api.main:app --reload --port 8000")
    print("  cd ui && npm install && npm run dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

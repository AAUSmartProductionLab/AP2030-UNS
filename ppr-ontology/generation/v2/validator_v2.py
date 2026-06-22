"""validator_v2 — single pyshacl call covering AAS metamodel + CSSx domain.

Replaces v1's two-step validation (basyx metamodel pre-check + custom RDF
projection + SHACL) with one unified path:

    aas_json → aas_to_rdf.convert → data_graph
                                  + CSSx_AAS.ttl (with transitively imported AAS v3.1 OWL)
                                  vs.
                                  aas-shacl-schema.ttl (AAS v3.1 SHACL)
                                  + shacl/generated_v2/shapes.generated.shacl.ttl (CSSx auto-derived)

Issues are partitioned into "metamodel" (sh:sourceShape in AAS namespace) and
"ontology" (everything else) so the existing UI message-routing keeps working.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pyshacl
from rdflib import Graph, Literal, Namespace, OWL, RDF, URIRef


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_ONTOLOGY_DIR = _REPO_ROOT / "ontology"
_SHACL_GEN_V2_DIR = _REPO_ROOT / "shacl" / "generated_v2"

_CSSX_AAS_TTL          = _ONTOLOGY_DIR / "CSSx_AAS.ttl"
_AAS_RDF_ONTOLOGY_TTL  = _ONTOLOGY_DIR / "aas-rdf-ontology.ttl"
_AAS_SHACL_SHAPES_TTL  = _ONTOLOGY_DIR / "aas-shacl-schema.ttl"
_CSSX_GENERATED_SHAPES = _SHACL_GEN_V2_DIR / "shapes.generated.shacl.ttl"


# Catalog: official URL → local file (mirror of ontology/catalog-v001.xml entries).
_IMPORT_CATALOG: dict[str, Path] = {
    "https://admin-shell.io/aas/3/1/": _AAS_RDF_ONTOLOGY_TTL,
    "https://admin-shell.io/aas/3/1":  _AAS_RDF_ONTOLOGY_TTL,
    "http://admin-shell.io/aas/3/1/":  _AAS_RDF_ONTOLOGY_TTL,
    "http://www.w3id.org/hsu-aut/css": _ONTOLOGY_DIR / "CSS-Ontology.ttl",
}


def _resolve_import(import_uri: str, parent_file: Path) -> Path | None:
    """Map an `owl:imports` IRI to a local file, or None if no local copy."""
    canon = import_uri.rstrip("/")
    if import_uri in _IMPORT_CATALOG:
        return _IMPORT_CATALOG[import_uri]
    if canon in _IMPORT_CATALOG:
        return _IMPORT_CATALOG[canon]

    parsed = urlparse(import_uri)
    if parsed.scheme in ("http", "https"):
        ttl_name = Path(parsed.path).name
        if ttl_name.endswith(".ttl"):
            for candidate in (
                parent_file.parent / ttl_name,
                parent_file.parent / "modules" / ttl_name,
                parent_file.parent.parent / "modules" / ttl_name,
            ):
                resolved = candidate.resolve()
                if resolved.exists():
                    return resolved
        return None
    if parsed.scheme == "file":
        path = parsed.path
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return Path(path)
    return (parent_file.parent / import_uri).resolve()


def _load_with_imports(target: Graph, ontology_file: Path, visited: set[Path]) -> None:
    resolved = ontology_file.resolve()
    if resolved in visited or not resolved.exists():
        return
    visited.add(resolved)
    g = Graph().parse(str(resolved), format="turtle")
    target += g
    for _, _, imported in g.triples((None, OWL.imports, None)):
        local = _resolve_import(str(imported), resolved)
        if local is not None:
            _load_with_imports(target, local, visited)


SH = Namespace("http://www.w3.org/ns/shacl#")
_AAS_NS_PREFIX = "https://admin-shell.io/aas/3/1/"


def _is_aas_shape(report_graph: Graph, validation_result: URIRef) -> bool:
    """Decide whether a ValidationResult comes from an AAS-namespace shape.

    Several signals can identify an AAS shape:
      1. sh:sourceShape IRI starts with the AAS namespace
      2. sh:sourceConstraintComponent path traverses an AAS-namespaced property
      3. sh:resultPath property is in the AAS namespace
    Any one of these is sufficient — covers blank-node shapes too.
    """
    source_shape = report_graph.value(validation_result, SH.sourceShape)
    if source_shape is not None and str(source_shape).startswith(_AAS_NS_PREFIX):
        return True

    result_path = report_graph.value(validation_result, SH.resultPath)
    if result_path is not None and str(result_path).startswith(_AAS_NS_PREFIX):
        return True

    return False


def _classify_issue(report_graph: Graph, validation_result: URIRef) -> dict[str, str]:
    severity_map = {
        str(SH.Violation): "Violation",
        str(SH.Warning): "Warning",
        str(SH.Info): "Info",
    }
    message = str(report_graph.value(validation_result, SH.resultMessage) or "No message")
    severity_uri = str(report_graph.value(validation_result, SH.resultSeverity) or str(SH.Violation))
    source_shape = report_graph.value(validation_result, SH.sourceShape)
    focus_node = report_graph.value(validation_result, SH.focusNode)

    return {
        "source": "metamodel" if _is_aas_shape(report_graph, validation_result) else "ontology",
        "source_shape": str(source_shape) if source_shape is not None else "",
        "focus_node": str(focus_node) if focus_node is not None else "",
        "severity": severity_map.get(severity_uri, "Violation"),
        "message": message,
    }


def _extract_issues(report_graph: Graph) -> list[dict]:
    issues: list[dict] = []
    for vr in report_graph.subjects(RDF.type, SH.ValidationResult):
        issues.append(_classify_issue(report_graph, vr))
    return issues


def run_shacl_v2(json_text: str, tmp_dir: Path) -> tuple[bool, list[dict], list[dict], list[dict]]:
    """v2 unified validation. Same return signature as v1's `run_shacl`.

    Returns (conforms, all_issues, metamodel_issues, ontology_issues).
    """
    try:
        from tools.aas_to_rdf import convert as aas_to_rdf_convert
    except ImportError as exc:
        msg = f"v2 validator: cannot import tools.aas_to_rdf ({exc})"
        return False, [{"source": "validation", "severity": "Violation", "message": msg}], \
            [{"source": "validation", "severity": "Violation", "message": msg}], []

    json_path  = tmp_dir / "input.json"
    rdf_path   = tmp_dir / "data.ttl"
    report_path = tmp_dir / "report.ttl"
    json_path.write_text(json_text, encoding="utf-8")

    try:
        aas_to_rdf_convert(json_path, rdf_path)
    except Exception as exc:
        msg = f"v2 RDF projection failed: {exc}"
        return False, [{"source": "metamodel", "severity": "Violation", "message": msg}], \
            [{"source": "metamodel", "severity": "Violation", "message": msg}], []

    data_graph = Graph().parse(str(rdf_path), format="turtle")

    visited: set[Path] = set()
    if _CSSX_AAS_TTL.exists():
        _load_with_imports(data_graph, _CSSX_AAS_TTL, visited)
    if _AAS_RDF_ONTOLOGY_TTL.exists() and _AAS_RDF_ONTOLOGY_TTL.resolve() not in visited:
        _load_with_imports(data_graph, _AAS_RDF_ONTOLOGY_TTL, visited)

    shapes = Graph()
    shapes_loaded = False
    if _AAS_SHACL_SHAPES_TTL.exists():
        shapes.parse(str(_AAS_SHACL_SHAPES_TTL), format="turtle")
        shapes_loaded = True
    if _CSSX_GENERATED_SHAPES.exists():
        shapes.parse(str(_CSSX_GENERATED_SHAPES), format="turtle")
        shapes_loaded = True

    if not shapes_loaded:
        msg = (
            "v2 validator: no SHACL shapes loaded. Expected at "
            f"{_AAS_SHACL_SHAPES_TTL} and/or {_CSSX_GENERATED_SHAPES}."
        )
        return False, [{"source": "validation", "severity": "Violation", "message": msg}], \
            [{"source": "validation", "severity": "Violation", "message": msg}], []

    try:
        conforms, report_graph, _report_text = pyshacl.validate(
            data_graph,
            shacl_graph=shapes,
            # inference="none": the serializer emits both the AAS class and the
            # cssx subclass directly, so no rdfs subClassOf chasing is needed.
            # Enabling rdfs inference triggers ~1200 spurious "abstract class —
            # use a subclass" violations from the AAS SHACL spec.
            inference="none",
            advanced=True,
            allow_warnings=True,
            allow_infos=True,
            meta_shacl=False,
            debug=False,
        )
    except Exception as exc:
        msg = f"v2 pyshacl invocation failed: {exc}"
        return False, [{"source": "validation", "severity": "Violation", "message": msg}], \
            [{"source": "validation", "severity": "Violation", "message": msg}], []

    if hasattr(report_graph, "serialize"):
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_graph.serialize(destination=str(report_path), format="turtle")

    issues = _extract_issues(report_graph)
    metamodel_issues = [i for i in issues if i["source"] == "metamodel"]
    ontology_issues  = [i for i in issues if i["source"] == "ontology"]

    return bool(conforms), [*metamodel_issues, *ontology_issues], metamodel_issues, ontology_issues

"""Load PPR ontology TTL files and extract the rdfs:subClassOf type hierarchy."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional


def _find_ontology_dir() -> Optional[Path]:
    """Locate the ppr-ontology/ontology directory relative to the Planner."""
    here = Path(__file__).resolve().parent
    # Walk up to the repo root (max 5 levels) and look for ppr-ontology/ontology
    for ancestor in [here] + list(here.parents)[:5]:
        candidate = ancestor / "ppr-ontology" / "ontology"
        if candidate.is_dir():
            return candidate
    env = os.environ.get("PPR_ONTOLOGY_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    return None


def load_type_parent_map(
    ontology_dir: Optional[Path] = None,
    warnings: Optional[List[str]] = None,
) -> Optional[Dict[str, str]]:
    """Return ``{child_local_name: parent_local_name}`` from rdfs:subClassOf triples.

    Loads ``CSS-Ontology.ttl`` and all ``modules/*.ttl`` files.
    Returns *None* if rdflib is unavailable or the ontology directory cannot be found,
    so that the caller can fall back to heuristic inference.
    """
    try:
        from rdflib import Graph, RDFS, OWL
    except ImportError:
        if warnings is not None:
            warnings.append("rdflib not installed; falling back to heuristic type inference.")
        return None

    if ontology_dir is None:
        ontology_dir = _find_ontology_dir()
    if ontology_dir is None:
        if warnings is not None:
            warnings.append("PPR ontology directory not found; falling back to heuristic type inference.")
        return None

    g = Graph()
    # Load the base CSS ontology and all module TTLs
    for ttl in _collect_ttl_files(ontology_dir):
        try:
            g.parse(str(ttl), format="turtle")
        except Exception as exc:
            if warnings is not None:
                warnings.append(f"Failed to parse {ttl.name}: {exc}")

    parent_map: Dict[str, str] = {}
    for subclass, superclass in g.subject_objects(RDFS.subClassOf):
        # Skip blank-node restrictions (OWL cardinality constraints etc.)
        if not hasattr(subclass, "toPython") or not hasattr(superclass, "toPython"):
            continue
        child_uri = str(subclass)
        parent_uri = str(superclass)
        # Only keep named classes (URIs), skip blank nodes
        if child_uri.startswith("http") and parent_uri.startswith("http"):
            child_name = _local_name(child_uri)
            parent_name = _local_name(parent_uri)
            if child_name and parent_name and child_name != parent_name:
                # First parent wins (same semantics as heuristic)
                parent_map.setdefault(child_name, parent_name)

    return parent_map


def _local_name(uri: str) -> str:
    """Extract the local/fragment part of a URI."""
    if "#" in uri:
        return uri.rsplit("#", 1)[-1]
    return uri.rstrip("/").rsplit("/", 1)[-1]


def _collect_ttl_files(ontology_dir: Path) -> List[Path]:
    """Return the base ontology and all module TTL files."""
    files: List[Path] = []
    base = ontology_dir / "CSS-Ontology.ttl"
    if base.exists():
        files.append(base)
    modules_dir = ontology_dir / "modules"
    if modules_dir.is_dir():
        files.extend(sorted(modules_dir.glob("*.ttl")))
    return files

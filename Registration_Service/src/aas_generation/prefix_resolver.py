"""
Prefix resolver for ontology-aligned semantic IDs.

Expands compact prefixed IRIs (e.g. ``cssx:Transport``) found in YAML
configs into their full URIs before the AAS builders process them.
"""

from typing import Dict

# Prefix → base IRI mapping derived from the PPR ontology.
DEFAULT_PREFIX_MAP: Dict[str, str] = {
    "css:":  "http://www.w3id.org/hsu-aut/css#",
    "cssx:": "http://www.w3id.org/aau-ra/cssx#",
}


def expand_prefix(value: str, prefix_map: Dict[str, str] = None) -> str:
    """Expand a single prefixed IRI string, returning the full URI.

    If *value* does not match any known prefix it is returned unchanged,
    so existing full-URI strings pass through safely.
    """
    if not isinstance(value, str):
        return value
    pm = prefix_map or DEFAULT_PREFIX_MAP
    for prefix, base_iri in pm.items():
        if value.startswith(prefix):
            return base_iri + value[len(prefix):]
    return value


def expand_prefixes_in_config(obj, prefix_map: Dict[str, str] = None):
    """Recursively walk a parsed YAML config and expand prefixed IRIs.

    Expansion is applied to every *string value* in the tree — dict values
    and list elements — so that downstream code always sees full URIs.
    Dict keys are left untouched.
    """
    pm = prefix_map or DEFAULT_PREFIX_MAP
    if isinstance(obj, dict):
        return {k: expand_prefixes_in_config(v, pm) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_prefixes_in_config(item, pm) for item in obj]
    if isinstance(obj, str):
        return expand_prefix(obj, pm)
    return obj

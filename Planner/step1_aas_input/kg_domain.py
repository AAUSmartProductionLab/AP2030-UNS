"""Collect AI-Planning domain (fluents + actions) from projected KG data.

Reads the apex:Action individuals materialized by the 040 projection rule,
which consumes the bridge's apex:MirroredSubmodelElement + apex:RefKey data.
Produces List[_ParsedSource] compatible with the existing merge → build pipeline.

Only domain data (fluents, actions) is populated; objects/init/goal are left
empty and come from the AAS Problem section (see context.py).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

import requests

from .models import _ParsedSource
from ..step2_pddl_construction.utils import semantic_tail

logger = logging.getLogger(__name__)

# Timing-role predicate → (condition_group_key, is_effect)
_ROLE_MAP: Dict[str, tuple[str, bool]] = {
    "https://w3id.org/2026/apex/hasPrecondition":      ("preconditions", False),
    "https://w3id.org/2026/apex/hasAtStartCondition":  ("at_start_conditions", False),
    "https://w3id.org/2026/apex/hasAtEndCondition":    ("at_end_conditions", False),
    "https://w3id.org/2026/apex/hasOverAllCondition":  ("over_all_conditions", False),
    "https://w3id.org/2026/apex/hasEffect":            ("effects", True),
    "https://w3id.org/2026/apex/hasAtStartEffect":     ("at_start_effects", True),
    "https://w3id.org/2026/apex/hasAtEndEffect":       ("at_end_effects", True),
}


def collect_domain_sources_from_kg(
    query_endpoint: str,
    abox_graph: str,
    tbox_graph: str,
    timeout_seconds: float = 10.0,
) -> List[_ParsedSource]:
    """Query projected apex:Action individuals and return _ParsedSource list.

    Each source corresponds to one source AAS (one AIPlanning submodel) and
    carries the domain section only (fluents + actions).  Objects/init/goal
    are left empty; they continue to come from AAS parsing.
    """
    try:
        rows = _query_projected_actions(query_endpoint, abox_graph, tbox_graph, timeout_seconds)
    except Exception as exc:
        logger.warning("KG domain query failed: %s", exc)
        return []

    return _build_parsed_sources(rows)


# ── SPARQL query ─────────────────────────────────────────────────────────────

def _query_projected_actions(
    query_endpoint: str,
    abox_graph: str,
    tbox_graph: str,
    timeout_seconds: float,
) -> List[Dict[str, Any]]:
    """Return raw SPARQL result rows covering actions, parameters, and constraints."""
    query = f"""
PREFIX apex: <https://w3id.org/2026/apex/>
PREFIX arso: <https://w3id.org/2025/arso#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT
  ?action ?actionLabel ?actionSid ?actionKind ?skillKey
  ?aas
  ?param ?paramIdx ?paramTypeRef ?paramIsSelfRef
  ?constraint ?constraintSid ?role
  ?argBinding ?argPos ?argActionParamIdx
FROM <{abox_graph}>
WHERE {{
  ?action a apex:Action ;
    rdfs:label ?actionLabel ;
    apex:sourceSemanticId ?actionSid ;
    apex:hasSourceAAS ?aas .

  BIND(IF(EXISTS {{ ?action a apex:TemporalProcess }}, "Process",
         IF(EXISTS {{ ?action a apex:TemporalEvent }}, "Event", "Action")) AS ?actionKind)

  OPTIONAL {{ ?action apex:skillReferenceKey ?skillKey . }}

  OPTIONAL {{
    ?action apex:hasParameter ?param .
    ?param apex:parameterIndex ?paramIdx ;
           apex:parameterTypeRef ?paramTypeRef ;
           apex:parameterIsSelfRef ?paramIsSelfRef .
  }}

  OPTIONAL {{
    ?action ?role ?constraint .
    VALUES ?role {{
      apex:hasPrecondition apex:hasAtStartCondition apex:hasAtEndCondition
      apex:hasOverAllCondition apex:hasEffect apex:hasAtStartEffect apex:hasAtEndEffect
    }}
    ?constraint apex:sourceSemanticId ?constraintSid .
    OPTIONAL {{
      ?constraint apex:constraintArg ?argBinding .
      ?argBinding apex:constraintArgPosition ?argPos ;
                  apex:constraintArgActionParamIndex ?argActionParamIdx .
    }}
  }}
}}
ORDER BY ?action ?paramIdx ?role ?argPos
""".strip()

    response = requests.post(
        query_endpoint,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()

    def _get(row: Dict, key: str) -> Optional[str]:
        return (row.get(key) or {}).get("value")

    return [
        {k: _get(row, k) for k in row}
        for row in payload.get("results", {}).get("bindings", [])
    ]


# ── Assembly ─────────────────────────────────────────────────────────────────

def _build_parsed_sources(rows: List[Dict[str, Any]]) -> List[_ParsedSource]:
    """Group SPARQL rows by source AAS and assemble _ParsedSource objects."""

    # Group rows by (aas_iri, action_iri)
    actions_by_aas: Dict[str, Dict[str, Any]] = {}  # aas_iri → {action_iri → action_dict}

    for row in rows:
        action_iri = row.get("action")
        aas_iri = row.get("aas")
        if not action_iri or not aas_iri:
            continue

        if aas_iri not in actions_by_aas:
            actions_by_aas[aas_iri] = {}

        actions = actions_by_aas[aas_iri]
        if action_iri not in actions:
            actions[action_iri] = {
                "iri": action_iri,
                "label": row.get("actionLabel") or "",
                "sid": row.get("actionSid") or "",
                "kind": row.get("actionKind") or "Action",
                "skill_key": row.get("skillKey") or "",
                "params": {},        # idx → {typeRef, isSelfRef}
                "constraints": {},   # constraint_iri → {sid, role, args: {pos → param_idx}}
            }

        action = actions[action_iri]

        # Parameters
        param_iri = row.get("param")
        if param_iri and row.get("paramIdx") is not None:
            idx = int(row["paramIdx"])
            if idx not in action["params"]:
                action["params"][idx] = {
                    "typeRef": row.get("paramTypeRef") or "",
                    "isSelfRef": str(row.get("paramIsSelfRef") or "false").lower() == "true",
                }

        # Constraints (conditions/effects)
        constraint_iri = row.get("constraint")
        if constraint_iri and row.get("constraintSid"):
            if constraint_iri not in action["constraints"]:
                action["constraints"][constraint_iri] = {
                    "sid": row["constraintSid"],
                    "role": row.get("role") or "",
                    "args": {},
                }
            if row.get("argPos") is not None and row.get("argActionParamIdx") is not None:
                pos = int(row["argPos"])
                param_idx = int(row["argActionParamIdx"])
                action["constraints"][constraint_iri]["args"][pos] = param_idx

    # Build _ParsedSource objects, one per source AAS
    sources: List[_ParsedSource] = []
    for aas_iri, action_map in actions_by_aas.items():
        aas_name = _iri_local_name(aas_iri)
        parsed = _ParsedSource(aas_id=aas_iri, aas_name=aas_name)

        # Collect fluent signatures from all constraints across all actions
        fluent_sigs: Dict[str, set] = defaultdict(set)  # fluent_key → set of param count
        for action_dict in action_map.values():
            for cdict in action_dict["constraints"].values():
                fkey = _fluent_key(cdict["sid"])
                n_args = len(cdict["args"])
                fluent_sigs[fkey].add(n_args)

        # Emit fluents (one entry per unique (fluent_key, arg_count))
        emitted_fluents: set = set()
        for action_dict in action_map.values():
            for cdict in action_dict["constraints"].values():
                fkey = _fluent_key(cdict["sid"])
                n_args = len(cdict["args"])
                sig_key = (fkey, n_args)
                if sig_key not in emitted_fluents:
                    emitted_fluents.add(sig_key)
                    parsed.fluents.append({
                        "key": fkey,
                        "semantic_id": cdict["sid"],
                        "param_types": ["Thing"] * n_args,
                        "transformation": "",
                        "fluent_aas_path": "",
                        "transformation_aas_path": "",
                        "value_type": "bool",
                        "source": aas_name,
                        "source_aas_id": aas_iri,
                        "source_aas_name": aas_name,
                    })

        # Emit actions
        for action_dict in action_map.values():
            action_entry = _build_action_entry(action_dict, aas_iri, aas_name)
            if action_entry:
                parsed.actions.append(action_entry)

        sources.append(parsed)

    logger.info("Collected %d domain source(s) from KG (%d action(s) total)",
                len(sources), sum(len(m) for m in actions_by_aas.values()))
    return sources


def _build_action_entry(
    action_dict: Dict[str, Any],
    aas_iri: str,
    aas_name: str,
) -> Optional[Dict[str, Any]]:
    label = action_dict["label"]
    if not label:
        return None

    # Parameters: sorted by index, build {name, type, is_constant, bound_object?}
    params_by_idx = action_dict["params"]
    parameters: List[Dict[str, Any]] = []
    for idx in sorted(params_by_idx):
        p = params_by_idx[idx]
        type_ref = p["typeRef"]
        is_self = p["isSelfRef"]
        type_name = _type_name(type_ref)
        entry: Dict[str, Any] = {"name": f"p{idx}", "type": type_name}
        if is_self:
            entry["is_constant"] = True
            entry["bound_object"] = aas_name
        parameters.append(entry)

    # Group constraints by role
    preconditions: List[Dict[str, Any]] = []
    effects: List[Dict[str, Any]] = []
    timing_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for cdict in action_dict["constraints"].values():
        role = cdict["role"]
        atom = _constraint_to_atom(cdict)
        role_info = _ROLE_MAP.get(role)
        if role_info:
            group_key, is_eff = role_info
            if is_eff:
                effects.append(atom)
            else:
                preconditions.append(atom)
        else:
            preconditions.append(atom)

    kind = action_dict.get("kind", "Action")
    return {
        "key": label,
        "semantic_id": action_dict["sid"],
        "semantic_ids": [action_dict["sid"]] if action_dict["sid"] else [],
        "skill_target": action_dict.get("skill_key") or label,
        "action_aas_path": "",
        "transformation_aas_path": "",
        "transformation": "",
        "parameters": parameters,
        "preconditions": preconditions,
        "effects": effects,
        "action_kind": kind,
        "source_name": aas_name,
        "source_aas_id": aas_iri,
    }


def _constraint_to_atom(cdict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a projected constraint dict to the term-tree atom format."""
    fkey = _fluent_key(cdict["sid"])
    args_by_pos = cdict["args"]
    params = [
        {"kind": "action_param", "index": args_by_pos[pos]}
        for pos in sorted(args_by_pos)
    ]
    return {
        "kind": "atom",
        "fluent": fkey,
        "params": params,
        "semantic_id": cdict["sid"],
    }


def _fluent_key(sid: str) -> str:
    """Derive the PDDL fluent key from a predicate semantic ID."""
    return semantic_tail(sid) if sid else "Unknown"


def _type_name(type_ref: str) -> str:
    """Derive a PDDL type name from a parameter type reference IRI."""
    if not type_ref:
        return "Thing"
    tail = semantic_tail(type_ref)
    return tail if tail else "Thing"


def _iri_local_name(iri: str) -> str:
    """Extract a short local name from an IRI for use as aas_name."""
    if not iri:
        return "unknown"
    iri = iri.rstrip("/")
    if "#" in iri:
        return iri.rsplit("#", 1)[-1]
    if "/" in iri:
        return iri.rsplit("/", 1)[-1]
    return iri

"""Semantic-ID-driven projection of AI-Planning submodels into the apex:Action graph.

Walks the *typed* py_aas_rdf submodel tree at SM_CREATED/UPDATED time, recognizing
planning elements by their semanticId. Instead of navigating through structural
container roles (PlanningDomainSection, ActionCollection, ParameterList, etc.), it
recursively scans the tree for leaf-level planning semanticIds — SkillExecutionModel,
ActionParameter, timing-group roles, etc. — making the projection robust to container
idShort changes and eliminating the need for intermediate structural roles in the
ontology.

The emitted graph is identical in shape to the earlier container-based approach
(apex:Action / TemporalProcess / TemporalEvent, sourceSemanticId, rdfs:label,
skillReferenceKey, hasParameter→Parameter, the apex:has{Pre,AtStart,…}Condition/Effect
role edges → ProjectedConstraint → ConstraintArg), so the Planner ([kg_domain.py]) is
unchanged. Node IRIs are content-hashed for idempotency across re-ingest.
"""

from __future__ import annotations

import hashlib
from typing import Any

import rdflib

APEX = rdflib.Namespace("https://w3id.org/2026/apex/")
RDF = rdflib.RDF
RDFS = rdflib.RDFS
XSD = rdflib.XSD

# ── Canonical role IRIs (mirror apex-aas-planning-roles.ttl; pinned by a drift test) ──
ROLE_AIPLANNING_SUBMODEL = APEX["AIPlanningSubmodel"]
ROLE_SKILL_EXECUTION_MODEL = APEX["SkillExecutionModel"]
ROLE_PROCESS_EXECUTION_MODEL = APEX["ProcessExecutionModel"]
ROLE_EVENT_EXECUTION_MODEL = APEX["EventExecutionModel"]
ROLE_SKILL_REFERENCE = APEX["SkillReference"]
ROLE_FLUENT_REFERENCE = APEX["FluentReference"]
ROLE_ACTION_PARAMETER = APEX["ActionParameter"]
ROLE_PLANNING_TERM = APEX["PlanningTerm"]

# Execution model semanticId → (action-kind keyword, extra rdf:type for the projected node)
_EXECUTION_MODEL_KIND = {
    ROLE_SKILL_EXECUTION_MODEL: ("action", None),
    ROLE_PROCESS_EXECUTION_MODEL: ("process", APEX["TemporalProcess"]),
    ROLE_EVENT_EXECUTION_MODEL: ("event", APEX["TemporalEvent"]),
}

# Timing-group role class → projected timing-role edge on the action. Aligned 1:1 with
# kg_domain.py _ROLE_MAP (the seven roles the Planner consumes).
_TIMING_GROUP_ROLE = {
    APEX["PreconditionGroup"]: APEX["hasPrecondition"],
    APEX["AtStartConditionGroup"]: APEX["hasAtStartCondition"],
    APEX["AtEndConditionGroup"]: APEX["hasAtEndCondition"],
    APEX["OverallConditionGroup"]: APEX["hasOverAllCondition"],
    APEX["EffectGroup"]: APEX["hasEffect"],
    APEX["AtStartEffectGroup"]: APEX["hasAtStartEffect"],
    APEX["AtEndEffectGroup"]: APEX["hasAtEndEffect"],
    APEX["ContinuousEffectGroup"]: APEX["hasEffect"],
}


# ── Small typed-model helpers ─────────────────────────────────────────────────

def _own_semantic_id(model: Any) -> str | None:
    """First key value of the element's primary semanticId, or None."""
    ref = getattr(model, "semanticId", None)
    keys = getattr(ref, "keys", None) if ref is not None else None
    if not isinstance(keys, list):
        return None
    for key in keys:
        value = getattr(key, "value", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _children(element: Any) -> list[Any]:
    """SubmodelElementCollection / SubmodelElementList children, or []."""
    value = getattr(element, "value", None)
    return value if isinstance(value, list) else []


def _reference(element: Any) -> Any | None:
    """The Reference held by a ReferenceElement value, or None."""
    value = getattr(element, "value", None)
    if value is not None and hasattr(value, "keys") and hasattr(value, "type"):
        return value
    return None


def _last_key_value(reference: Any) -> str:
    keys = getattr(reference, "keys", None) or []
    return str(keys[-1].value) if keys else ""


def _find_child(element: Any, *, role: rdflib.URIRef | None = None, id_short: str | None = None) -> Any | None:
    for child in _children(element):
        if role is not None and _own_semantic_id(child) == str(role):
            return child
        if id_short is not None and getattr(child, "idShort", None) == id_short:
            return child
    return None


def _find_descendant(element: Any, *, role: rdflib.URIRef) -> Any | None:
    """Recursively search *element* subtree for the first child with the given semanticId."""
    for child in _children(element):
        if _own_semantic_id(child) == str(role):
            return child
        found = _find_descendant(child, role=role)
        if found is not None:
            return found
    return None


def _find_descendants(element: Any, *, role: rdflib.URIRef) -> list[Any]:
    """Recursively collect all descendants with the given semanticId."""
    results: list[Any] = []
    for child in _children(element):
        if _own_semantic_id(child) == str(role):
            results.append(child)
        results.extend(_find_descendants(child, role=role))
    return results


def _find_execution_models(submodel: Any) -> list[tuple[Any, str, rdflib.URIRef | None]]:
    """Return list of (element, kind, extra_type) for every execution model in the submodel tree."""
    results: list[tuple[Any, str, rdflib.URIRef | None]] = []
    for element in _children(submodel):
        results.extend(_find_execution_models_in_subtree(element))
    return results


def _find_execution_models_in_subtree(element: Any) -> list[tuple[Any, str, rdflib.URIRef | None]]:
    """Recursively scan for execution-model elements under *element*."""
    results: list[tuple[Any, str, rdflib.URIRef | None]] = []
    sid = _own_semantic_id(element)
    kind_type = _EXECUTION_MODEL_KIND.get(rdflib.URIRef(sid)) if sid else None
    if kind_type is not None:
        kind, extra_type = kind_type
        results.append((element, kind, extra_type))
    for child in _children(element):
        results.extend(_find_execution_models_in_subtree(child))
    return results


# ── IRI minting (deterministic SHA256-based IRIs for idempotent projection) ───

def _sha256_iri(prefix: str, content: str) -> rdflib.URIRef:
    return rdflib.URIRef(prefix + hashlib.sha256(content.encode("utf-8")).hexdigest())


def _bool_literal(value: bool) -> str:
    return rdflib.Literal(value, datatype=XSD.boolean).n3()


def _insert_data(lines: list[str], graph_iri: str | None) -> str:
    if not lines:
        return ""
    if graph_iri:
        body = "\n".join(f"    {line}" for line in lines)
        return f"INSERT DATA {{\n  GRAPH <{graph_iri}> {{\n{body}\n  }}\n}}"
    body = "\n".join(f"  {line}" for line in lines)
    return f"INSERT DATA {{\n{body}\n}}"


def _delete_prior_actions(submodel_node: rdflib.URIRef, graph_iri: str | None) -> list[str]:
    """Cascade-delete the action subgraph previously projected from this submodel.

    Keyed on the apex:projectedFromSubmodel back-link, leaf nodes first so each
    step still resolves its parents. Makes SM_UPDATED re-projection idempotent.
    """
    sm = submodel_node.n3()
    pf = APEX["projectedFromSubmodel"].n3()
    hp = APEX["hasParameter"].n3()
    ca = APEX["constraintArg"].n3()
    pc = APEX["ProjectedConstraint"].n3()

    def stmt(delete: str, where: str) -> str:
        if graph_iri:
            return (
                f"WITH <{graph_iri}>\nDELETE {{ {delete} }}\nWHERE {{ {where} }}"
            )
        return f"DELETE {{ {delete} }}\nWHERE {{ {where} }}"

    return [
        stmt("?carg ?p ?o .", f"?a {pf} {sm} . ?a ?role ?c . ?c {ca} ?carg . ?carg ?p ?o ."),
        stmt("?c ?p ?o .", f"?a {pf} {sm} . ?a ?role ?c . ?c a {pc} . ?c ?p ?o ."),
        stmt("?param ?p ?o .", f"?a {pf} {sm} . ?a {hp} ?param . ?param ?p ?o ."),
        stmt("?a ?p ?o .", f"?a {pf} {sm} . ?a ?p ?o ."),
    ]


# ── Projection ────────────────────────────────────────────────────────────────

def aiplanning_action_statements(
    submodel: Any,
    submodel_node: rdflib.URIRef,
    graph_iri: str | None,
    *,
    is_update: bool,
) -> list[str]:
    """Project the apex:Action graph for an AI-Planning submodel.

    Returns SPARQL UPDATE statements (cascade delete on update + one INSERT DATA),
    or [] if the submodel is not an AI-Planning submodel. Uses recursive scanning to
    find execution models anywhere in the submodel tree, rather than navigating via
    structural container roles.
    """
    if submodel is None or _own_semantic_id(submodel) != str(ROLE_AIPLANNING_SUBMODEL):
        return []

    # Adapt Submodel (which has submodelElements) to the _children protocol (reads .value)
    elements = getattr(submodel, "submodelElements", None)
    if elements is None:
        return []
    # Wrap so _children() can find the list via .value
    _submodel_wrapper = type("_SubmodelWrapper", (), {"value": elements})()

    root = str(submodel_node)
    lines: list[str] = []

    execution_models = _find_execution_models_in_subtree(_submodel_wrapper)
    for action, kind, extra_type in execution_models:
        action_key = getattr(action, "idShort", None)
        if not action_key:
            continue
        _project_action(action, action_key, kind, extra_type, root, submodel_node, lines)

    statements: list[str] = []
    if is_update:
        statements.extend(_delete_prior_actions(submodel_node, graph_iri))
    insert = _insert_data(lines, graph_iri)
    if insert:
        statements.append(insert)
    return statements


def _project_action(
    action: Any,
    action_key: str,
    kind: str,
    extra_type: rdflib.URIRef | None,
    root: str,
    submodel_node: rdflib.URIRef,
    lines: list[str],
) -> None:
    action_sid = _own_semantic_id(action)
    action_iri = _sha256_iri(f"urn:kg:apex:{kind}:", f"{root}|{action_key}")

    types = [APEX["Action"].n3()] + ([extra_type.n3()] if extra_type else [])
    lines.append(f"{action_iri.n3()} a {' , '.join(types)} .")
    if action_sid:
        lines.append(f"{action_iri.n3()} {APEX['sourceSemanticId'].n3()} {rdflib.Literal(action_sid).n3()} .")
    lines.append(f"{action_iri.n3()} {RDFS.label.n3()} {rdflib.Literal(action_key).n3()} .")
    lines.append(f"{action_iri.n3()} {APEX['projectedFromSubmodel'].n3()} {submodel_node.n3()} .")

    # Scan action subtree for SkillReference, ActionParameter, and timing-group roles.
    # Container roles (ParameterList, ConditionList, EffectList) are no longer required —
    # we find the meaningful elements directly by their semantic IDs.
    for child in _children(action):
        child_sid = _own_semantic_id(child)
        if child_sid == str(ROLE_SKILL_REFERENCE):
            ref = _reference(child)
            if ref is not None:
                lines.append(
                    f"{action_iri.n3()} {APEX['skillReferenceKey'].n3()} {rdflib.Literal(_last_key_value(ref)).n3()} ."
                )

    _project_parameters_in_subtree(action, action_iri, root, action_key, lines)
    _project_constraints_in_subtree(action, action_iri, root, action_key, lines)


def _project_parameters_in_subtree(container: Any, action_iri: rdflib.URIRef, root: str, action_key: str, lines: list[str]) -> None:
    """Find ActionParameter elements recursively in *container* and project them."""
    params = _find_descendants(container, role=ROLE_ACTION_PARAMETER)
    for idx, param in enumerate(params):
        ref = _reference(param)
        if ref is None:
            continue
        param_iri = _sha256_iri("urn:kg:apex:parameter:", f"{root}|{action_key}|{idx}")
        type_ref = _last_key_value(ref)
        first_key_type = str(ref.keys[0].type) if ref.keys else ""
        ref_type = ref.type.value if hasattr(ref.type, "value") else str(ref.type)
        is_self_ref = ref_type == "ModelReference" and first_key_type.endswith("AssetAdministrationShell")
        lines += [
            f"{action_iri.n3()} {APEX['hasParameter'].n3()} {param_iri.n3()} .",
            f"{param_iri.n3()} a {APEX['Parameter'].n3()} .",
            f"{param_iri.n3()} {APEX['parameterIndex'].n3()} {rdflib.Literal(idx, datatype=XSD.nonNegativeInteger).n3()} .",
            f"{param_iri.n3()} {APEX['parameterTypeRef'].n3()} {rdflib.Literal(type_ref).n3()} .",
            f"{param_iri.n3()} {APEX['parameterIsSelfRef'].n3()} {_bool_literal(is_self_ref)} .",
        ]


def _project_constraints_in_subtree(container: Any, action_iri: rdflib.URIRef, root: str, action_key: str, lines: list[str]) -> None:
    """Find timing-group-roled elements recursively in *container* and project constraints."""
    # Find all descendants whose semanticId is a timing-group role
    timing_groups: list[tuple[Any, rdflib.URIRef]] = []
    _collect_timing_groups(container, timing_groups)

    # Collect all PlanningTerms within the action so we can match them
    # A PlanningTerm descendant of a timing-group is the actual constraint.
    # We iterate over timing groups and find terms inside each group's subtree.
    for group, role in timing_groups:
        group_id = getattr(group, "idShort", "")
        terms = _find_descendants(group, role=ROLE_PLANNING_TERM)
        for term in terms:
            fluent_ref = _find_descendant(term, role=ROLE_FLUENT_REFERENCE)
            ref = _reference(fluent_ref) if fluent_ref is not None else None
            if ref is None:
                continue  # nested/logical terms are not projected
            term_id = getattr(term, "idShort", "")
            # Deterministic path for IRI hashing: root|actionKey|group_idShort|term_idShort
            term_key = f"{root}|{action_key}|{group_id}|{term_id}"
            constraint_iri = _sha256_iri("urn:kg:apex:constraint:", term_key)
            predicate_sid = _last_key_value(ref)

            lines += [
                f"{action_iri.n3()} {role.n3()} {constraint_iri.n3()} .",
                f"{constraint_iri.n3()} a {APEX['ProjectedConstraint'].n3()} .",
                f"{constraint_iri.n3()} {APEX['sourceSemanticId'].n3()} {rdflib.Literal(predicate_sid).n3()} .",
                f"{constraint_iri.n3()} {APEX['constraintPath'].n3()} {rdflib.Literal(term_key).n3()} .",
            ]

            # Find ActionParameter children of this term for constraint args
            term_params = _find_descendants(term, role=ROLE_ACTION_PARAMETER)
            for arg_pos, arg in enumerate(term_params):
                arg_ref = _reference(arg)
                if arg_ref is None:
                    continue
                carg_iri = _sha256_iri("urn:kg:apex:carg:", f"{term_key}|{arg_pos}")
                action_param_idx = _last_key_value(arg_ref)
                lines += [
                    f"{constraint_iri.n3()} {APEX['constraintArg'].n3()} {carg_iri.n3()} .",
                    f"{carg_iri.n3()} a {APEX['ConstraintArg'].n3()} .",
                    f"{carg_iri.n3()} {APEX['constraintArgPosition'].n3()} {rdflib.Literal(arg_pos, datatype=XSD.nonNegativeInteger).n3()} .",
                    f"{carg_iri.n3()} {APEX['constraintArgActionParamIndex'].n3()} {rdflib.Literal(int(action_param_idx), datatype=XSD.nonNegativeInteger).n3()} .",
                ]


def _collect_timing_groups(container: Any, results: list[tuple[Any, rdflib.URIRef]]) -> None:
    """Recursively collect elements whose semanticId is a timing-group role."""
    for child in _children(container):
        sid = _own_semantic_id(child)
        role = _TIMING_GROUP_ROLE.get(rdflib.URIRef(sid)) if sid else None
        if role is not None:
            results.append((child, role))
        _collect_timing_groups(child, results)

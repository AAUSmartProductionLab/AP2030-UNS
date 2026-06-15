"""Tests for the semantic-ID-driven AI-Planning projector (conversion/aiplanning.py).

Covers: drift between the projector's role IRIs and the canonical ontology, the shape
of the projected apex:Action graph, idempotent re-projection, and robustness to action
keys that contain dots (which the retired path-regex rule silently mis-parsed)."""

from __future__ import annotations

from pathlib import Path

import rdflib

from conversion import parse_event, submodel_iri
import conversion.aiplanning as aip

APEX = rdflib.Namespace("https://w3id.org/2026/apex/")
RDFS = rdflib.RDFS
ONTOLOGY = Path(__file__).resolve().parents[1] / "Ontology" / "APEX" / "apex-aas-planning-roles.ttl"


# ── fixture authoring ─────────────────────────────────────────────────────────

def _sid(value, *supp):
    d = {"semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": value}]}}
    if supp:
        d["supplementalSemanticIds"] = [
            {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": s}]} for s in supp
        ]
    return d


def _smc(id_short, role, *children, supp=()):
    return {"modelType": "SubmodelElementCollection", "idShort": id_short, **_sid(role, *supp), "value": list(children)}


def _sml(id_short, role, *children):
    return {"modelType": "SubmodelElementList", "idShort": id_short, "typeValueListElement": "ReferenceElement",
            **_sid(role), "value": list(children)}


def _ref(id_short, role, ref_type, keys):
    d = {"modelType": "ReferenceElement", "idShort": id_short,
         "value": {"type": ref_type, "keys": [{"type": t, "value": v} for t, v in keys]}}
    if role:
        d.update(_sid(role))
    return d


def _action(name):
    A = str(APEX)
    return _smc(name, A + "SkillExecutionModel",
        _ref("SkillReference", A + "SkillReference", "ModelReference",
             [("AssetAdministrationShell", "urn:aas:ima"), ("Submodel", "urn:sm:skills"),
              ("SubmodelElementCollection", name + "Skill")]),
        _sml("Parameters", A + "ParameterList",
             _ref(None, A + "ActionParameter", "ModelReference", [("AssetAdministrationShell", "urn:aas:ima")]),
             _ref(None, A + "ActionParameter", "ExternalReference", [("GlobalReference", "urn:type:Station")])),
        _smc("Conditions", A + "ConditionList",
             _smc("PreConditions", A + "PreconditionGroup",
                  _smc("term_1", A + "PlanningTerm",
                       _ref("FluentReference", A + "FluentReference", "ModelReference",
                            [("Submodel", "urn:sm:AIPlanning"), ("SubmodelElementCollection", "Operational")]),
                       _sml("Parameters", A + "ParameterList",
                            _ref(None, A + "ActionParameter", "ModelReference", [("ReferenceElement", "0")])),
                       supp=("urn:p:Operational",)))),
        _smc("Effects", A + "EffectList",
             _smc("EndEffects", A + "EffectGroup",
                  _smc("term_1", A + "PlanningTerm",
                       _ref("FluentReference", A + "FluentReference", "ModelReference",
                            [("Submodel", "urn:sm:AIPlanning"), ("SubmodelElementCollection", "On")]),
                       _sml("Parameters", A + "ParameterList",
                            _ref(None, A + "ActionParameter", "ModelReference", [("ReferenceElement", "0")]),
                            _ref(None, A + "ActionParameter", "ModelReference", [("ReferenceElement", "1")])),
                       supp=("urn:p:On",)))))


def _aiplanning_submodel(sm_id, *action_names):
    A = str(APEX)
    return {"id": sm_id, **_sid(A + "AIPlanningSubmodel"),
            "submodelElements": [_smc("Domain", A + "PlanningDomainSection",
                                      _smc("Actions", A + "ActionCollection", *[_action(n) for n in action_names]))]}


def _project(sm_id, *action_names, is_update=False):
    ev = parse_event({"type": "SM_CREATED", "id": sm_id, "submodel": _aiplanning_submodel(sm_id, *action_names)},
                     "submodel-events")
    sm_node = submodel_iri("", sm_id, id_strategy="identity")
    g = rdflib.Graph()
    for stmt in aip.aiplanning_action_statements(ev.submodel, sm_node, None, is_update=is_update):
        g.update(stmt)
    return g, sm_node


# ── drift: projector role IRIs must be declared in the canonical ontology ──────

def test_projector_role_iris_are_declared_in_ontology():
    g = rdflib.Graph()
    g.parse(ONTOLOGY, format="turtle")
    declared = set(g.subjects(rdflib.RDF.type, rdflib.OWL.Class))

    used = {v for k, v in vars(aip).items() if k.startswith("ROLE_")}
    used |= set(aip._EXECUTION_MODEL_KIND.keys())
    used |= set(aip._TIMING_GROUP_ROLE.keys())

    missing = sorted(str(u) for u in used if u not in declared)
    assert not missing, f"role IRIs used by the projector but not declared in {ONTOLOGY.name}: {missing}"


# ── projected graph shape ─────────────────────────────────────────────────────

def test_projected_action_graph_shape():
    sm_id = "urn:sm:imaAAS:AIPlanning"
    g, sm_node = _project(sm_id, "Loading")
    loading = aip._sha256_iri("urn:kg:apex:action:", f"{sm_node}|Loading")

    assert (loading, rdflib.RDF.type, APEX.Action) in g
    assert (loading, APEX.sourceSemanticId, rdflib.Literal(str(APEX.SkillExecutionModel))) in g
    assert (loading, RDFS.label, rdflib.Literal("Loading")) in g
    assert (loading, APEX.projectedFromSubmodel, sm_node) in g
    assert (loading, APEX.skillReferenceKey, rdflib.Literal("LoadingSkill")) in g

    # Parameters: [0] self-ref to the AAS, [1] external type ref.
    params = {int(g.value(p, APEX.parameterIndex)): p for p in g.objects(loading, APEX.hasParameter)}
    assert g.value(params[0], APEX.parameterIsSelfRef) == rdflib.Literal(True)
    assert g.value(params[0], APEX.parameterTypeRef) == rdflib.Literal("urn:aas:ima")
    assert g.value(params[1], APEX.parameterIsSelfRef) == rdflib.Literal(False)
    assert g.value(params[1], APEX.parameterTypeRef) == rdflib.Literal("urn:type:Station")

    # Precondition: Operational(p0); End effect: On(p0, p1).
    pre = list(g.objects(loading, APEX.hasPrecondition))
    assert len(pre) == 1
    assert g.value(pre[0], APEX.sourceSemanticId) == rdflib.Literal("Operational")
    pre_args = {int(g.value(a, APEX.constraintArgPosition)): int(g.value(a, APEX.constraintArgActionParamIndex))
                for a in g.objects(pre[0], APEX.constraintArg)}
    assert pre_args == {0: 0}

    eff = list(g.objects(loading, APEX.hasEffect))
    assert len(eff) == 1
    assert g.value(eff[0], APEX.sourceSemanticId) == rdflib.Literal("On")
    eff_args = {int(g.value(a, APEX.constraintArgPosition)): int(g.value(a, APEX.constraintArgActionParamIndex))
                for a in g.objects(eff[0], APEX.constraintArg)}
    assert eff_args == {0: 0, 1: 1}


def test_non_aiplanning_submodel_yields_nothing():
    ev = parse_event({"type": "SM_CREATED", "id": "urn:sm:plain",
                      "submodel": {"id": "urn:sm:plain", "submodelElements": []}}, "submodel-events")
    sm_node = submodel_iri("", "urn:sm:plain", id_strategy="identity")
    assert aip.aiplanning_action_statements(ev.submodel, sm_node, None, is_update=False) == []


# ── idempotency ───────────────────────────────────────────────────────────────

def test_reprojection_on_update_is_idempotent():
    from rdflib.compare import to_isomorphic
    sm_id = "urn:sm:idem:AIPlanning"
    g_create, sm_node = _project(sm_id, "Loading", "Occupy")

    # Replay create then an update (delete prior + reinsert) into the same graph.
    ev = parse_event({"type": "SM_UPDATED", "id": sm_id, "submodel": _aiplanning_submodel(sm_id, "Loading", "Occupy")},
                     "submodel-events")
    for stmt in aip.aiplanning_action_statements(ev.submodel, sm_node, None, is_update=True):
        g_create.update(stmt)

    g_fresh, _ = _project(sm_id, "Loading", "Occupy")
    assert to_isomorphic(g_create) == to_isomorphic(g_fresh)


# ── robustness: recognition is by semantic ID, not idShort path convention ─────

def test_nonstandard_idshorts_still_project_via_semantic_ids():
    """The retired rule anchored on literal idShort paths ('Domain.Actions...',
    'PreConditions'). The projector keys on role semantic IDs, so a submodel whose
    structural idShorts are renamed still projects correctly."""
    A = str(APEX)
    sm_id = "urn:sm:weird:AIPlanning"
    submodel = {"id": sm_id, **_sid(A + "AIPlanningSubmodel"), "submodelElements": [
        _smc("PlanningRoot", A + "PlanningDomainSection",            # not 'Domain'
             _smc("SkillSet", A + "ActionCollection",                # not 'Actions'
                  _smc("Loading", A + "SkillExecutionModel",
                       _smc("Pre", A + "ConditionList",              # not 'Conditions'
                            _smc("Must", A + "PreconditionGroup",    # not 'PreConditions'
                                 _smc("t0", A + "PlanningTerm",
                                      _ref("FluentReference", A + "FluentReference", "ModelReference",
                                           [("SubmodelElementCollection", "Operational")])))))))]}
    ev = parse_event({"type": "SM_CREATED", "id": sm_id, "submodel": submodel}, "submodel-events")
    sm_node = submodel_iri("", sm_id, id_strategy="identity")
    g = rdflib.Graph()
    for stmt in aip.aiplanning_action_statements(ev.submodel, sm_node, None, is_update=False):
        g.update(stmt)

    action = aip._sha256_iri("urn:kg:apex:action:", f"{sm_node}|Loading")
    assert (action, rdflib.RDF.type, APEX.Action) in g
    pre = list(g.objects(action, APEX.hasPrecondition))
    assert len(pre) == 1
    assert g.value(pre[0], APEX.sourceSemanticId) == rdflib.Literal("Operational")

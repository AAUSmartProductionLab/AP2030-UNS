"""Guardrail: under id_strategy='identity', the two IRI-construction paths must agree.

kg-bridge builds SubmodelElement IRIs in two places that MUST produce byte-identical
IRIs, or the predicate-view join (`?sm aas:Submodel/submodelElements ?node .
?node apex:smElementValue ...`) silently breaks:

  1. py_aas_rdf `to_rdf()`            → emits aas:Submodel/submodelElements <SME_IRI>
  2. kg-bridge iri.submodel_element_iri → the node projection.py annotates with apex:*

This test pins that invariant for the identity strategy (base_uri="").
"""

from __future__ import annotations

import rdflib

from conversion.iri import submodel_element_iri, submodel_iri
from py_aas_rdf.models.submodel import Submodel
from py_aas_rdf.models.submodel_element_collection import SubmodelElementCollection
from py_aas_rdf.models.submodel_element_list import AasSubmodelElements, SubmodelElementList
from py_aas_rdf.models.property import Property

AAS = rdflib.Namespace("https://admin-shell.io/aas/3/1/")
_CHILD_PREDICATES = (
    AAS["Submodel/submodelElements"],
    AAS["SubmodelElementCollection/value"],
    AAS["SubmodelElementList/value"],
)


def _to_rdf_sme_iris(submodel: Submodel) -> set[str]:
    graph, _ = submodel.to_rdf(base_uri="", id_strategy="identity")
    return {
        str(obj)
        for _subject, predicate, obj in graph
        if predicate in _CHILD_PREDICATES
    }


def test_identity_submodel_root_iri_matches():
    sm_id = "https://smartproductionlab.aau.dk/submodels/instances/imaAAS/AIPlanning"
    submodel = Submodel(id=sm_id, idShort="AIPlanning", submodelElements=[])
    graph, node = submodel.to_rdf(base_uri="", id_strategy="identity")

    # Identity uses the id verbatim — no percent-encoding, no urn prefix.
    assert str(node) == sm_id
    assert str(submodel_iri("", sm_id, id_strategy="identity")) == sm_id


def test_identity_nested_collection_iris_match_iri_helper():
    sm_id = "https://smartproductionlab.aau.dk/submodels/instances/imaAAS/AIPlanning"
    leaf = Property(idShort="State", valueType="xs:string", value="Execute")
    dispensing = SubmodelElementCollection(idShort="Dispensing", value=[leaf])
    actions = SubmodelElementCollection(idShort="Actions", value=[dispensing])
    domain = SubmodelElementCollection(idShort="Domain", value=[actions])
    submodel = Submodel(id=sm_id, idShort="AIPlanning", submodelElements=[domain])

    to_rdf_iris = _to_rdf_sme_iris(submodel)

    for path in (
        "Domain",
        "Domain.Actions",
        "Domain.Actions.Dispensing",
        "Domain.Actions.Dispensing.State",
    ):
        helper_iri = str(submodel_element_iri("", sm_id, path, id_strategy="identity"))
        assert helper_iri in to_rdf_iris, f"{path} → {helper_iri} not produced by to_rdf"

    # Readable, no percent-encoded slashes in the path portion.
    assert (
        f"{sm_id}/submodel-elements/Domain.Actions.Dispensing.State" in to_rdf_iris
    )


def test_identity_list_index_iris_match_iri_helper():
    sm_id = "https://test/sm/X"
    p0 = Property(idShort="p0", valueType="xs:string", value="a")
    parameters = SubmodelElementList(
        idShort="Parameters",
        typeValueListElement=AasSubmodelElements.Property,
        value=[p0],
    )
    dispensing = SubmodelElementCollection(idShort="Dispensing", value=[parameters])
    submodel = Submodel(id=sm_id, idShort="AIPlanning", submodelElements=[dispensing])

    to_rdf_iris = _to_rdf_sme_iris(submodel)

    # List indices are escaped to %5B/%5D in BOTH paths (valid IRI chars).
    helper_iri = str(
        submodel_element_iri("", sm_id, "Dispensing.Parameters[0].p0", id_strategy="identity")
    )
    assert helper_iri in to_rdf_iris
    assert helper_iri == f"{sm_id}/submodel-elements/Dispensing.Parameters%5B0%5D.p0"

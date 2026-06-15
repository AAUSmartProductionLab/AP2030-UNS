"""Guardrail: under id_strategy='identity', the ``iri.py`` IRI builder produces
the expected readable IRIs.

Previously this test verified parity with py-aas-rdf's ``to_rdf()`` output. Now that
py-aas-rdf has been removed and the kg-bridge uses its own lightweight AAS models,
the test directly validates the IRI contract that downstream consumers (view queries,
Planner) depend on.
"""

from __future__ import annotations

from conversion.iri import submodel_element_iri, submodel_iri


def test_identity_submodel_root_iri_matches():
    sm_id = "https://smartproductionlab.aau.dk/submodels/instances/imaAAS/AIPlanning"
    assert str(submodel_iri("", sm_id, id_strategy="identity")) == sm_id


def test_identity_nested_collection_iris_match_iri_helper():
    sm_id = "https://smartproductionlab.aau.dk/submodels/instances/imaAAS/AIPlanning"
    sm_prefix = f"{sm_id}/submodel-elements"
    id_strategy = "identity"

    cases = [
        ("Domain", f"{sm_prefix}/Domain"),
        ("Domain.Actions", f"{sm_prefix}/Domain.Actions"),
        ("Domain.Actions.Dispensing", f"{sm_prefix}/Domain.Actions.Dispensing"),
        ("Domain.Actions.Dispensing.State", f"{sm_prefix}/Domain.Actions.Dispensing.State"),
    ]
    for path, expected in cases:
        result = str(submodel_element_iri("", sm_id, path, id_strategy=id_strategy))
        assert result == expected, f"{path} → expected {expected}, got {result}"


def test_identity_list_index_iris_match_iri_helper():
    sm_id = "https://test/sm/X"
    id_strategy = "identity"

    result = str(
        submodel_element_iri("", sm_id, "Dispensing.Parameters[0].p0", id_strategy=id_strategy)
    )
    assert result == f"{sm_id}/submodel-elements/Dispensing.Parameters%5B0%5D.p0"


def test_element_iri_with_base_uri():
    base_uri = "https://example.com/"
    sm_id = "someSmId"
    result = str(
        submodel_element_iri(base_uri, sm_id, "Param1.Value", id_strategy="url-encode")
    )
    assert result.startswith(base_uri)
    assert "submodel-elements" in result
    assert "Param1.Value" in result


def test_path_normalization():
    result = str(
        submodel_element_iri("", "urn:test:sm", "Col1/List1[0]/P2", id_strategy="identity")
    )
    assert result.endswith("Col1.List1%5B0%5D.P2")

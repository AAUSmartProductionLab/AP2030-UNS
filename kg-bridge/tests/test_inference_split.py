from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_dynamic_rules_are_not_materialized():
    materialization_dir = _repo_root() / "kg-bridge" / "sparql" / "materialization"
    dynamic_rule_names = {
        "100-resource-at.rq",
        "110-product-at.rq",
        "120-occupied.rq",
        "130-operational.rq",
        "140-in-range.rq",
    }

    existing = {path.name for path in materialization_dir.glob("*.rq")}
    assert dynamic_rule_names.isdisjoint(existing)


def test_dynamic_views_exist_and_are_construct_only():
    views_dir = _repo_root() / "kg-bridge" / "sparql" / "views"
    expected_views = {
        "resource-at.rq",
        "product-at.rq",
        "occupied.rq",
        "operational.rq",
        "in-range.rq",
    }

    existing = {path.name for path in views_dir.glob("*.rq")}
    assert expected_views.issubset(existing)
    assert "operational-stoppering-station.rq" not in existing

    for name in expected_views:
        query = (views_dir / name).read_text(encoding="utf-8")
        upper = query.upper()
        assert "CONSTRUCT" in upper
        assert "FROM <URN:KG:TBOX>" in upper
        assert "FROM <URN:KG:ABOX>" in upper
        assert "INSERT" not in upper
        assert "DELETE" not in upper
        assert "WITH" not in upper


def test_dynamic_views_use_semantic_id_bindings():
    views_dir = _repo_root() / "kg-bridge" / "sparql" / "views"
    expected_views = {
        "resource-at.rq",
        "product-at.rq",
        "occupied.rq",
        "operational.rq",
        "in-range.rq",
    }

    for name in expected_views:
        query = (views_dir / name).read_text(encoding="utf-8")
        assert "apex:smElementSemanticId" in query
        assert "(location|position|station|cell)" not in query
        assert "(occupied|isoccupied|busy)" not in query
        assert "(operational|enabled|state)" not in query
        assert "(positionx|coordx|x$|\\.x$)" not in query
        assert "(positiony|coordy|y$|\\.y$)" not in query
        assert "(station|cell|line|module|system)" not in query

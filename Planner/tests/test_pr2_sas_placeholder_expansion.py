"""Tests for PR2 SAS-mapping ``<none of those>`` expansion.

The Fast-Downward translator (used by PR2) appends a synthetic
``<none of those>`` slot to every mutex group of size >= 2 so that every
SAS variable always has *some* value. For groups of size 2 we collapse
the slot into ``!other_atom`` (legacy behaviour). For groups of size
>= 3 we expand the slot into the conjunction of negated sibling atoms
so that downstream consumers (BT builder, policy graph, simulator)
never see the raw placeholder string.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from unified_planning.engines.up_pr2.engine import (
    _parse_policy_file,
    _parse_sas_mapping,
)


def _write(tmp_path: Path, name: str, body: str) -> str:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body).lstrip("\n"))
    return str(p)


def test_two_value_group_collapses_to_negation(tmp_path: Path) -> None:
    sas_path = _write(
        tmp_path,
        "output.sas",
        """
        begin_metric
        0
        end_metric
        begin_variable
        var0
        -1
        2
        Atom finished(p1)
        <none of those>
        end_variable
        begin_state
        end_state
        """,
    )

    mapping, expansion = _parse_sas_mapping(sas_path)

    assert mapping["var0:0"] == "finished(p1)"
    assert mapping["var0:1"] == "!finished(p1)"
    assert expansion == {}


def test_multi_value_group_expands_placeholder(tmp_path: Path) -> None:
    sas_path = _write(
        tmp_path,
        "output.sas",
        """
        begin_metric
        0
        end_metric
        begin_variable
        var0
        -1
        4
        Atom at(s1, l1)
        Atom at(s1, l2)
        Atom at(s1, l3)
        <none of those>
        end_variable
        begin_state
        end_state
        """,
    )

    mapping, expansion = _parse_sas_mapping(sas_path)

    sentinel = "<none of those>@var0"
    assert mapping["var0:0"] == "at(s1, l1)"
    assert mapping["var0:3"] == sentinel
    assert expansion[sentinel] == frozenset(
        {"not(at(s1, l1))", "not(at(s1, l2))", "not(at(s1, l3))"}
    )


def test_negated_atom_in_group_negates_back_to_positive(tmp_path: Path) -> None:
    sas_path = _write(
        tmp_path,
        "output.sas",
        """
        begin_metric
        0
        end_metric
        begin_variable
        var0
        -1
        3
        NegatedAtom blocked(s1)
        Atom busy(s1)
        <none of those>
        end_variable
        begin_state
        end_state
        """,
    )

    _, expansion = _parse_sas_mapping(sas_path)
    sentinel = "<none of those>@var0"
    # NegatedAtom blocked(s1) is stored as ``not(blocked(s1))``;
    # negating it back yields the bare positive ``blocked(s1)``.
    assert expansion[sentinel] == frozenset({"blocked(s1)", "not(busy(s1))"})


def test_policy_file_inlines_expansion(tmp_path: Path) -> None:
    sas_path = _write(
        tmp_path,
        "output.sas",
        """
        begin_metric
        0
        end_metric
        begin_variable
        var0
        -1
        3
        Atom at(s1, l1)
        Atom at(s1, l2)
        <none of those>
        end_variable
        begin_variable
        var1
        -1
        2
        Atom finished(p1)
        <none of those>
        end_variable
        begin_state
        end_state
        """,
    )
    mapping, expansion = _parse_sas_mapping(sas_path)

    policy_path = _write(
        tmp_path,
        "policy.out",
        """
        If holds: var0:2 var1:0
        Execute: move s1 home
        """,
    )

    entries = _parse_policy_file(policy_path, mapping, expansion)
    assert len(entries) == 1
    literals, action_text, action_name, action_args = entries[0]
    # Placeholder slot var0:2 must have been expanded to negations of its
    # sibling atoms; the 2-value collapse for var1 stays as-is.
    assert literals == frozenset(
        {"not(at(s1, l1))", "not(at(s1, l2))", "finished(p1)"}
    )
    assert action_name == "move"
    assert action_args == ("s1", "home")
    assert action_text == "move s1 home"


def test_policy_file_without_expansion_arg_is_back_compat(tmp_path: Path) -> None:
    """Calling ``_parse_policy_file`` without the optional expansion map
    must not crash; placeholder sentinels would simply pass through. This
    keeps the legacy two-argument signature usable for external callers.
    """
    sas_path = _write(
        tmp_path,
        "output.sas",
        """
        begin_metric
        0
        end_metric
        begin_variable
        var0
        -1
        2
        Atom finished(p1)
        <none of those>
        end_variable
        begin_state
        end_state
        """,
    )
    mapping, _ = _parse_sas_mapping(sas_path)

    policy_path = _write(
        tmp_path,
        "policy.out",
        """
        If holds: var0:0
        Execute: complete p1
        """,
    )

    entries = _parse_policy_file(policy_path, mapping)
    assert entries[0][0] == frozenset({"finished(p1)"})

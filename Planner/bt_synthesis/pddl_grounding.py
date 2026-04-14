# pyright: reportMissingImports=false

"""Shared fondparser grounding helpers for BT synthesis tooling."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PR2_SCRIPTS_DIR = (
    _REPO_ROOT
    / "unified-planning"
    / "unified_planning"
    / "engines"
    / "up_pr2"
    / "pr2"
    / "prp-scripts"
)

if str(_PR2_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_PR2_SCRIPTS_DIR))

from fondparser.formula import And, Formula, Not, Oneof, Or, Primitive, When
from fondparser.grounder import GroundProblem, Operator
from normalizer import flatten as flatten_oneof


def ground_pddl(domain_pddl: str, problem_pddl: str) -> GroundProblem:
    """Ground raw domain/problem PDDL text into a fondparser GroundProblem."""
    tmpdir = tempfile.mkdtemp(prefix="pddl_ground_")
    domain_path = Path(tmpdir) / "domain.pddl"
    problem_path = Path(tmpdir) / "problem.pddl"
    try:
        domain_path.write_text(domain_pddl)
        problem_path.write_text(problem_pddl)
        return GroundProblem(str(domain_path), str(problem_path))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

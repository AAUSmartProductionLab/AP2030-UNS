# pyright: reportMissingImports=false

"""
Shared PDDL grounding facade for the PR2 BT pipeline.

Wraps ``fondparser.grounder.GroundProblem`` behind a single function
that accepts raw PDDL text and returns the grounded problem, eliminating
the temp-file + sys.path boilerplate previously duplicated in
``bt_policy.causal`` and ``bt_policy.simulator``.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

# fondparser lives in pr2/prp-scripts/ — add it once for the whole pipeline.
_SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pr2", "prp-scripts")
_SCRIPT_DIR = os.path.normpath(_SCRIPT_DIR)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from fondparser.grounder import GroundProblem, Operator
from fondparser.formula import (
    And,
    Not,
    Oneof,
    Or,
    Primitive,
    When,
    Formula,
)
from normalizer import flatten as flatten_oneof


def ground_pddl(domain_pddl: str, problem_pddl: str) -> GroundProblem:
    """Ground a PDDL domain/problem and return the ``GroundProblem``.

    Writes the PDDL text to temporary files (required by fondparser),
    invokes the grounder, and cleans up afterwards.

    Parameters
    ----------
    domain_pddl : str
        Raw PDDL text of the domain.
    problem_pddl : str
        Raw PDDL text of the problem.

    Returns
    -------
    GroundProblem
        The grounded problem with operators, fluents, init, and goal.
    """
    tmpdir = tempfile.mkdtemp(prefix="pddl_ground_")
    dom_path = os.path.join(tmpdir, "domain.pddl")
    prob_path = os.path.join(tmpdir, "problem.pddl")
    try:
        with open(dom_path, "w") as f:
            f.write(domain_pddl)
        with open(prob_path, "w") as f:
            f.write(problem_pddl)
        return GroundProblem(dom_path, prob_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

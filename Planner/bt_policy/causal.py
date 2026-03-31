"""
Causal analysis of FOND PDDL actions for goal-grouped BT construction.

Uses ``fondparser.grounder.GroundProblem`` to ground the domain/problem and
extract action effects, preconditions, and achiever mappings.  These are
filtered to only include actions that appear in a PR2 policy, so the
resulting data describes *policy-relevant* causal structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Dict,
    FrozenSet,
    List,
    Optional,
    Set,
    Tuple,
)

from .pddl_grounding import (
    Formula,
    GroundProblem,
    Not,
    Oneof,
    Operator,
    Or,
    Primitive,
    When,
    And,
    flatten_oneof as _flatten_oneof,
    ground_pddl,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Data structures
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class GroundedAction:
    """A single grounded PDDL action with extracted causal information."""

    name: str
    """PR2-style name, e.g. ``"move-car l-1-1 l-2-1"``."""

    preconditions: FrozenSet[str]
    """Positive fluent literals that must hold (from PDDL precondition)."""

    neg_preconditions: FrozenSet[str]
    """Negated fluent literals that must hold (from PDDL precondition)."""

    outcomes: List[Tuple[FrozenSet[str], FrozenSet[str]]]
    """List of ``(add_set, del_set)`` — one per ``Oneof`` branch.
    Deterministic actions have exactly one outcome."""

    @property
    def oneof_count(self) -> int:
        return len(self.outcomes)

    @property
    def all_adds(self) -> FrozenSet[str]:
        """Union of add-effects across all outcomes."""
        return frozenset().union(*(a for a, _ in self.outcomes))

    @property
    def all_dels(self) -> FrozenSet[str]:
        """Union of delete-effects across all outcomes."""
        return frozenset().union(*(d for _, d in self.outcomes))

    @property
    def certain_dels(self) -> FrozenSet[str]:
        """Intersection of delete-effects across all outcomes.

        A fluent in *certain_dels* is deleted by **every** possible
        outcome of the action, so it is expected to become false during
        execution.  These are "trigger" preconditions rather than
        "safety/hold" preconditions.
        """
        if not self.outcomes:
            return frozenset()
        result = self.outcomes[0][1]  # dels of first outcome
        for _, d in self.outcomes[1:]:
            result = result & d
        return result


@dataclass
class CausalInfo:
    """Complete causal analysis of a grounded FOND domain, filtered to policy actions."""

    actions: Dict[str, GroundedAction]
    """Mapping from PR2 action name to grounded action info."""

    achievers: Dict[str, List[str]]
    """Fluent → list of PR2 action names that ADD this fluent (in some outcome)."""

    deleters: Dict[str, List[str]]
    """Fluent → list of PR2 action names that DELETE this fluent (in some outcome)."""

    goal_fluents: FrozenSet[str]
    """Goal condition fluents (positive literals)."""

    goal_neg_fluents: FrozenSet[str]
    """Goal condition negated fluents."""

    static_fluents: FrozenSet[str]
    """Fluents that are never added or deleted by any policy action."""

    all_fluents: FrozenSet[str]
    """All ground fluents in the problem."""


# ═══════════════════════════════════════════════════════════════════════════
#  Fluent string normalization
# ═══════════════════════════════════════════════════════════════════════════


def _fondparser_predicate_to_fluent(predicate) -> str:
    """Convert a fondparser ``Predicate`` to the PR2 fluent string format.

    fondparser:  ``vehicle-at(l-1-1 l-1-2)``  (space-separated args)
    PR2 (SAS):   ``vehicle-at(l-1-1, l-1-2)`` (comma-space-separated args)

    We normalize to the PR2 comma-separated **lowercase** format since
    that is what ``PolicyRule.condition`` and FSAP conditions use.
    """
    name = predicate.name
    if predicate.ground_args is not None:
        args = predicate.ground_args
    elif predicate.args is not None:
        args = predicate.args
    else:
        args = []

    if not args:
        return f"{name}()".lower()

    arg_strs = [str(a[0]) for a in args]
    if len(arg_strs) == 1:
        return f"{name}({arg_strs[0]})".lower()
    return f"{name}({', '.join(arg_strs)})".lower()


def _fondparser_op_to_pr2_name(op: Operator) -> str:
    """Convert fondparser operator name to PR2-style action name.

    fondparser:  ``move-car_l-1-1_l-2-1``
    PR2:         ``move-car l-1-1 l-2-1``
    """
    # The operator has parameters as [(obj, type), ...]
    base_name = op.name
    # fondparser builds: action.name + "_" + "_".join(assignments)
    # The safe approach: use the operator's stored parameters
    if op.parameters:
        action_name_part = base_name
        # Strip the grounded suffix to get base action name
        for param_name, _ in op.parameters:
            suffix = "_" + param_name
            if action_name_part.endswith(suffix):
                action_name_part = action_name_part[: -len(suffix)]
            elif "_" in action_name_part:
                # Might be embedded — try splitting from the right
                pass

        # Reconstruct using parameter values
        arg_strs = [p[0] for p in op.parameters]
        base = base_name
        # Remove trailing _arg1_arg2_... to get the operator schema name
        for arg in reversed(arg_strs):
            if base.endswith("_" + arg):
                base = base[: -(len(arg) + 1)]
        return base + " " + " ".join(arg_strs)
    else:
        # No parameters — action name is the operator name
        # Strip trailing underscore if present
        if base_name.endswith("_"):
            return base_name[:-1]
        return base_name


# ═══════════════════════════════════════════════════════════════════════════
#  Effect extraction from fondparser formulas
# ═══════════════════════════════════════════════════════════════════════════


def _extract_literals(formula: Formula) -> Tuple[Set[str], Set[str]]:
    """Extract positive and negative literals from a (non-Oneof) formula.

    Returns ``(add_set, del_set)`` where ``add_set`` contains fluents
    that are made true and ``del_set`` contains fluents made false.
    """
    adds: Set[str] = set()
    dels: Set[str] = set()

    if isinstance(formula, Primitive):
        adds.add(_fondparser_predicate_to_fluent(formula.predicate))
    elif isinstance(formula, Not):
        # Not(Primitive(...))
        inner = formula.args[0]
        if isinstance(inner, Primitive):
            dels.add(_fondparser_predicate_to_fluent(inner.predicate))
    elif isinstance(formula, And):
        for arg in formula.args:
            a, d = _extract_literals(arg)
            adds |= a
            dels |= d
    elif isinstance(formula, When):
        # Conditional effects — include the result effects
        # (conditional effects are rare in FOND benchmarks but handle them)
        a, d = _extract_literals(formula.result)
        adds |= a
        dels |= d
    # Ignore other formula types (Or, Forall, etc.) — shouldn't appear in effects

    return adds, dels


def _extract_preconditions(formula: Optional[Formula]) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """Extract positive and negative precondition literals.

    Returns ``(pos_preconds, neg_preconds)``.
    """
    pos: Set[str] = set()
    neg: Set[str] = set()

    if formula is None:
        return frozenset(), frozenset()

    if isinstance(formula, Primitive):
        pos.add(_fondparser_predicate_to_fluent(formula.predicate))
    elif isinstance(formula, Not):
        inner = formula.args[0]
        if isinstance(inner, Primitive):
            neg.add(_fondparser_predicate_to_fluent(inner.predicate))
    elif isinstance(formula, And):
        for arg in formula.args:
            p, n = _extract_preconditions(arg)
            pos |= p
            neg |= n
    elif isinstance(formula, Or):
        # Disjunctive preconditions — rare, but extract all atoms
        for arg in formula.args:
            p, n = _extract_preconditions(arg)
            pos |= p
            neg |= n

    return frozenset(pos), frozenset(neg)


def _extract_outcomes(op: Operator) -> List[Tuple[FrozenSet[str], FrozenSet[str]]]:
    """Extract ``(add_set, del_set)`` for each deterministic outcome.

    Uses ``normalizer.flatten()`` to decompose ``Oneof`` effects into
    individual branches.
    """
    if op.effect is None:
        return [(frozenset(), frozenset())]

    branches = _flatten_oneof(op)
    outcomes = []
    for branch in branches:
        adds, dels = _extract_literals(branch)
        outcomes.append((frozenset(adds), frozenset(dels)))

    # Deduplicate identical outcomes
    seen = set()
    unique = []
    for o in outcomes:
        key = (o[0], o[1])
        if key not in seen:
            seen.add(key)
            unique.append(o)

    return unique if unique else [(frozenset(), frozenset())]


def _extract_goal(goal_formula: Formula) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """Extract goal fluents from the ground problem's goal formula."""
    return _extract_preconditions(goal_formula)


# ═══════════════════════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════════════════════


def build_causal_info(
    domain_pddl: str,
    problem_pddl: str,
    policy_actions: Set[str],
) -> CausalInfo:
    """
    Ground the PDDL domain/problem and build causal analysis.

    Parameters
    ----------
    domain_pddl : str
        Raw PDDL text of the domain.
    problem_pddl : str
        Raw PDDL text of the problem.
    policy_actions : set of str
        Set of PR2-style grounded action names from the policy
        (e.g. ``{"move-car l-1-1 l-2-1", "changetire l-2-1"}``).
        Only these actions will be included in the causal analysis.

    Returns
    -------
    CausalInfo
        Complete causal information filtered to policy-relevant actions.
    """
    problem = ground_pddl(domain_pddl, problem_pddl)

    # Build name mapping: fondparser op → PR2 action name
    op_map: Dict[str, Operator] = {}
    for op in problem.operators:
        pr2_name = _fondparser_op_to_pr2_name(op)
        # Also try lowercase since fondparser may differ in case
        pr2_name_lower = pr2_name.lower()
        if pr2_name in policy_actions:
            op_map[pr2_name] = op
        elif pr2_name_lower in policy_actions:
            op_map[pr2_name_lower] = op
        else:
            # Try matching with lowercase policy action set
            policy_lower = {a.lower() for a in policy_actions}
            if pr2_name_lower in policy_lower:
                # Find the original-case policy action
                for pa in policy_actions:
                    if pa.lower() == pr2_name_lower:
                        op_map[pa] = op
                        break

    # Extract grounded action info
    actions: Dict[str, GroundedAction] = {}
    for pr2_name, op in op_map.items():
        pos_pre, neg_pre = _extract_preconditions(op.precondition)
        outcomes = _extract_outcomes(op)
        actions[pr2_name] = GroundedAction(
            name=pr2_name,
            preconditions=pos_pre,
            neg_preconditions=neg_pre,
            outcomes=outcomes,
        )

    # Build achiever/deleter maps
    achievers: Dict[str, List[str]] = {}
    deleters: Dict[str, List[str]] = {}
    all_adds: Set[str] = set()
    all_dels: Set[str] = set()

    for pr2_name, ga in actions.items():
        for fluent in ga.all_adds:
            achievers.setdefault(fluent, []).append(pr2_name)
            all_adds.add(fluent)
        for fluent in ga.all_dels:
            deleters.setdefault(fluent, []).append(pr2_name)
            all_dels.add(fluent)

    # Collect all fluents
    all_fluent_strs: Set[str] = set()
    for f in problem.fluents:
        all_fluent_strs.add(_fondparser_predicate_to_fluent(f))

    # Static fluents: never added or deleted by any policy action
    modified_fluents = all_adds | all_dels
    static = frozenset(all_fluent_strs - modified_fluents)

    # Goal
    goal_pos, goal_neg = _extract_goal(problem.goal)

    return CausalInfo(
        actions=actions,
        achievers=achievers,
        deleters=deleters,
        goal_fluents=goal_pos,
        goal_neg_fluents=goal_neg,
        static_fluents=static,
        all_fluents=frozenset(all_fluent_strs),
    )



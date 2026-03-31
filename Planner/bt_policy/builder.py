"""
Policy → reactive Behavior Tree construction.

Converts a PR2 planner result (policy rules + FSAPs) into a compact
reactive Behavior Tree.  The tree is structured by **distance to goal**,
mirroring the progression visible in the policy graph.

Key features
------------
1. **Goal-distance ordering** — branches ordered closest-to-goal first.
2. **Structural fallback detection** — complementary-literal pairs
   rendered as try/recover fallbacks.
3. **Condition hoisting** — shared conditions across rules at the same
   distance are gated to minimise total condition count.

Public API
----------
- ``policy_to_bt(result)`` — main entry point.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Dict,
    FrozenSet,
    List,
    Optional,
    Set,
    Tuple,
)

if TYPE_CHECKING:
    from pr2_bridge.adapter import FSAP, PR2Result, PolicyRule

from bt_policy.causal import CausalInfo, build_causal_info
from bt_policy.nodes import (
    BTNode,
    BehaviorTree,
    ActionNode,
    ConditionNode,
    FailureLeaf,
    ForbiddenActionNode,
    Inverter,
    ReactiveSelector,
    ReactiveSequence,
    SuccessLeaf,
    readable_action_id,
    sanitize_bt_id,
)
from bt_policy.optimizer import deduplicate_subtrees, parameterize_subtrees
from bt_policy.literals import parse_predicate, strip_negation


# ===================================================================
#  Small helpers
# ===================================================================

_FACTOR_MAX_DEPTH = 20  # Safety limit for recursive factoring.


def _build_postcond_check(
    fluents: FrozenSet[str],
    name: str = "PostCond",
) -> Optional[BTNode]:
    """Build a condition check from a set of fluents.

    Returns ``None`` when *fluents* is empty, a single ``ConditionNode``
    for one fluent, or a ``ReactiveSequence`` of conditions for several.

    This is the shared helper used by both the goal-branch and
    phase post-condition gates.
    """
    if not fluents:
        return None
    ordered = sorted(fluents)
    if len(ordered) == 1:
        return ConditionNode(ordered[0])
    return ReactiveSequence(name, [ConditionNode(f) for f in ordered])


def _wrap_with_postcond_gate(
    subtree: BTNode,
    postcond_fluents: FrozenSet[str],
    gate_name: str,
) -> BTNode:
    """Wrap *subtree* in a fallback that short-circuits when *postcond_fluents* hold.

    Structure::

        ReactiveFallback(gate_name)
        ├── <postcond check>   ← SUCCESS → phase done, skip subtree
        └── subtree            ← postcond FAILURE → execute as before

    Returns *subtree* unchanged when no post-conditions are available.
    """
    postcond = _build_postcond_check(postcond_fluents, f"{gate_name}_PostCond")
    if postcond is None:
        return subtree
    gated = ReactiveSelector(gate_name, [postcond, subtree])
    gated.is_rule_leaf = True
    return gated


def _condition_and(name: str, fluents: Set[str]) -> BTNode:
    """Build a reactive AND-check (sequence of conditions) for *fluents*."""
    ordered = sorted(fluents)
    if not ordered:
        return SuccessLeaf()
    if len(ordered) == 1:
        return ConditionNode(ordered[0])
    return ReactiveSequence(name, [ConditionNode(f) for f in ordered])


def _condition_nodes(fluents: FrozenSet[str]) -> List[ConditionNode]:
    """Sorted list of ConditionNode for a set of fluents."""
    return [ConditionNode(f) for f in sorted(fluents)]


def _gated_sequence(name: str, gates: List[BTNode], inner: BTNode) -> ReactiveSequence:
    """Sequence of gate conditions followed by an inner node.

    If *inner* is a non-rule-leaf ReactiveSequence its children are
    inlined to avoid unnecessary nesting.
    """
    if isinstance(inner, ReactiveSequence) and not inner.is_rule_leaf:
        return ReactiveSequence(name, gates + list(inner.children))
    return ReactiveSequence(name, gates + [inner])


# ===================================================================
#  FSAP guard construction
# ===================================================================


def _build_factored_fsap_or(
    condition_sets: List[FrozenSet[str]],
    base_name: str,
    depth: int = 0,
) -> BTNode:
    """Recursively build a compact OR of AND-condition sets.

    1. **Hoist** conditions shared by *all* sets into a gate.
    2. **Binary split** on the most-frequent fluent.
    3. **Complement elision** when no neutral sets exist.
    """
    if not condition_sets:
        return FailureLeaf("NoFSAPs")
    if len(condition_sets) == 1:
        return _condition_and(base_name, set(condition_sets[0]))
    if depth >= _FACTOR_MAX_DEPTH:
        return ReactiveSelector(
            base_name,
            [_condition_and(f"{base_name}_{i}", set(cs))
             for i, cs in enumerate(condition_sets)],
        )

    # Step 1: hoist conditions shared by ALL sets.
    common: Set[str] = set(condition_sets[0])
    for cs in condition_sets[1:]:
        common &= cs

    if common:
        common_fs = frozenset(common)
        reduced = list(dict.fromkeys(cs - common_fs for cs in condition_sets))
        if frozenset() in reduced:
            return _condition_and(base_name, common)
        inner = _build_factored_fsap_or(reduced, f"{base_name}_inner", depth + 1)
        gates = [ConditionNode(f) for f in sorted(common)]
        return _gated_sequence(f"{base_name}_gate", gates, inner)

    # Step 2: binary split on most-frequent fluent.
    base_count: Counter[str] = Counter()
    has_pos: Set[str] = set()
    has_neg: Set[str] = set()
    for cs in condition_sets:
        seen_bases: Set[str] = set()
        for lit in cs:
            base, neg = strip_negation(lit)
            seen_bases.add(base)
            (has_neg if neg else has_pos).add(base)
        base_count.update(seen_bases)

    candidates = [(b, c) for b, c in base_count.items() if c >= 2]
    if not candidates:
        return ReactiveSelector(
            base_name,
            [_condition_and(f"{base_name}_{i}", set(cs))
             for i, cs in enumerate(condition_sets)],
        )

    def _fsap_sort_key(item: Tuple[str, int]) -> Tuple[int, int, str]:
        b, c = item
        both = 1 if (b in has_pos and b in has_neg) else 0
        return (-c, -both, b)

    candidates.sort(key=_fsap_sort_key)
    best_base = candidates[0][0]
    pos_lit = best_base
    neg_lit = f"not({best_base})"

    pos_sets = list(dict.fromkeys(
        cs - {pos_lit} for cs in condition_sets if pos_lit in cs
    ))
    neg_sets = list(dict.fromkeys(
        cs - {neg_lit} for cs in condition_sets if neg_lit in cs
    ))
    neutral = list(dict.fromkeys(
        cs for cs in condition_sets if pos_lit not in cs and neg_lit not in cs
    ))

    elide_neg = (not neutral) and pos_sets and neg_sets
    children: List[BTNode] = []

    if neutral:
        children.append(
            _build_factored_fsap_or(neutral, f"{base_name}_neutral", depth + 1)
        )
    if pos_sets:
        pos_inner = _build_factored_fsap_or(
            pos_sets, f"{base_name}_pos", depth + 1,
        )
        children.append(
            _gated_sequence(
                f"{base_name}_if_{sanitize_bt_id(best_base)}",
                [ConditionNode(pos_lit)], pos_inner,
            )
        )
    if neg_sets:
        neg_inner = _build_factored_fsap_or(
            neg_sets, f"{base_name}_neg", depth + 1,
        )
        if elide_neg:
            children.append(neg_inner)
        else:
            children.append(
                _gated_sequence(
                    f"{base_name}_ifnot_{sanitize_bt_id(best_base)}",
                    [ConditionNode(neg_lit)], neg_inner,
                )
            )

    return children[0] if len(children) == 1 else ReactiveSelector(base_name, children)


def _build_fsap_guard(
    action: str,
    fsaps: List["FSAP"],
    context: FrozenSet[str] = frozenset(),
) -> Optional[BTNode]:
    """Build a guard that succeeds iff no FSAP condition is active.

    Returns ``Inverter(<factored-OR>)`` or ``None`` when no FSAPs apply.
    """
    # In-policy FSAPs (same action as rule).
    matches = [f for f in fsaps if f.action == action]
    seen: Set[FrozenSet[str]] = set()
    unique_residuals: List[FrozenSet[str]] = []
    for fsap in matches:
        residual = frozenset(fsap.condition) - context
        if residual not in seen:
            seen.add(residual)
            unique_residuals.append(residual)
    unique_residuals = [r for r in unique_residuals if r]

    # Orphan FSAPs (forbid actions not used by any policy rule).
    orphan_branches: List[BTNode] = []
    seen_orphan_keys: Set[Tuple[str, FrozenSet[str]]] = set()
    for fsap in fsaps:
        if fsap.action == action:
            continue
        fsap_conds = frozenset(fsap.condition)
        residual = fsap_conds - context
        if residual:
            continue
        orphan_key = (fsap.action, residual)
        if orphan_key in seen_orphan_keys:
            continue
        seen_orphan_keys.add(orphan_key)
        orphan_branches.append(ForbiddenActionNode(fsap.action))

    if not unique_residuals and not orphan_branches:
        return None

    safe_action = action.replace(" ", "_")
    all_branches: List[BTNode] = []

    if unique_residuals:
        any_fsap = _build_factored_fsap_or(
            unique_residuals, f"FSAP_{safe_action}",
        )
        all_branches.append(any_fsap)
    all_branches.extend(orphan_branches)

    if len(all_branches) == 1:
        combined = all_branches[0]
    else:
        combined = ReactiveSelector(f"AnyFSAP_{safe_action}", all_branches)
    return Inverter(combined)


def _strip_conditions(
    rules: List["PolicyRule"],
    to_remove: FrozenSet[str],
) -> List["PolicyRule"]:
    """Return new PolicyRule list with specified literals removed."""
    from pr2_bridge.adapter import PolicyRule

    return [
        PolicyRule(
            condition=frozenset(c for c in rule.condition if c not in to_remove),
            action=rule.action,
            action_name=rule.action_name,
            action_args=rule.action_args,
        )
        for rule in rules
    ]


# ===================================================================
#  Distance-to-goal computation via policy graph BFS
# ===================================================================


def _compute_rule_distances(
    rules: List["PolicyRule"],
    causal: CausalInfo,
) -> _DistanceResult:
    """Compute goal-distance for each policy rule via reverse BFS.

    Returns a ``_DistanceResult`` containing rule distances **and** the
    policy graph structure needed for post-condition derivation.
    """
    state_index: Dict[FrozenSet[str], int] = {}
    state_list: List[FrozenSet[str]] = []
    state_rules: Dict[int, List[int]] = defaultdict(list)

    for ridx, rule in enumerate(rules):
        sig = frozenset(str(l).strip().lower() for l in rule.condition)
        if sig not in state_index:
            state_index[sig] = len(state_list)
            state_list.append(sig)
        state_rules[state_index[sig]].append(ridx)

    n_states = len(state_list)

    # Split state literals into positive/negative.
    state_pos: List[FrozenSet[str]] = []
    state_neg: List[FrozenSet[str]] = []
    for sig in state_list:
        pos: Set[str] = set()
        neg: Set[str] = set()
        for lit in sig:
            if lit.startswith("not(") and lit.endswith(")"):
                neg.add(lit[4:-1])
            else:
                pos.add(lit)
        state_pos.append(frozenset(pos))
        state_neg.append(frozenset(neg))

    # Virtual goal node.
    goal_node = n_states

    forward: Dict[int, List[int]] = defaultdict(list)
    reverse: Dict[int, List[int]] = defaultdict(list)

    # Goal rules → goal node.
    goal_rule_indices = [i for i, r in enumerate(rules) if r.action_name == "goal"]
    for ridx in goal_rule_indices:
        sig = frozenset(str(l).strip().lower() for l in rules[ridx].condition)
        sid = state_index[sig]
        forward[sid].append(goal_node)
        reverse[goal_node].append(sid)

    # Non-goal rules → simulate action outcomes.
    for ridx, rule in enumerate(rules):
        if rule.action_name == "goal":
            continue

        sig = frozenset(str(l).strip().lower() for l in rule.condition)
        src = state_index[sig]
        action_key = rule.action.lower()

        ga = causal.actions.get(rule.action) or causal.actions.get(action_key)
        if ga is None:
            for k, v in causal.actions.items():
                if k.lower() == action_key:
                    ga = v
                    break
        if ga is None:
            continue

        src_p = set(state_pos[src])
        src_n = set(state_neg[src])

        for adds, dels in ga.outcomes:
            sim_p = set(src_p)
            sim_n = set(src_n)
            for f in dels:
                fl = f.lower()
                sim_p.discard(fl)
                sim_n.add(fl)
            for f in adds:
                fl = f.lower()
                sim_n.discard(fl)
                sim_p.add(fl)

            sim_p_fs = frozenset(sim_p)
            sim_n_fs = frozenset(sim_n)

            best_tgt = None
            best_score = -1
            for tgt_sid in range(n_states):
                tp = state_pos[tgt_sid]
                tn = state_neg[tgt_sid]
                if not tp.issubset(sim_p_fs):
                    continue
                if not tn.issubset(sim_n_fs):
                    continue
                score = len(tp) + len(tn)
                if score > best_score:
                    best_score = score
                    best_tgt = tgt_sid

            goal_pos_lower = {g.lower() for g in causal.goal_fluents}
            goal_neg_lower = {g.lower() for g in causal.goal_neg_fluents}
            if best_tgt is None:
                if goal_pos_lower.issubset(sim_p_fs) and goal_neg_lower.issubset(sim_n_fs):
                    forward[src].append(goal_node)
                    reverse[goal_node].append(src)
            else:
                forward[src].append(best_tgt)
                reverse[best_tgt].append(src)

    # BFS backwards from goal.
    distances: Dict[int, int] = {goal_node: 0}
    queue: deque = deque([goal_node])
    while queue:
        current = queue.popleft()
        for pred in reverse.get(current, []):
            if pred not in distances:
                distances[pred] = distances[current] + 1
                queue.append(pred)

    max_dist = max(distances.values()) if distances else 0
    rule_dist: Dict[int, int] = {}
    for ridx, rule in enumerate(rules):
        sig = frozenset(str(l).strip().lower() for l in rule.condition)
        sid = state_index.get(sig)
        if sid is not None and sid in distances:
            rule_dist[ridx] = distances[sid]
        else:
            rule_dist[ridx] = max_dist + 1

    return _DistanceResult(
        rule_dist=rule_dist,
        forward=dict(forward),
        state_index=dict(state_index),
        state_list=state_list,
        state_rules=dict(state_rules),
        goal_node=goal_node,
    )


# ===================================================================
#  Post-condition derivation from the policy graph
# ===================================================================


def _compute_phase_postconditions(
    dist_result: _DistanceResult,
    rules: List["PolicyRule"],
    causal: CausalInfo,
) -> Dict[int, FrozenSet[str]]:
    """Derive per-phase post-conditions from the policy graph.

    For each distance group D the post-condition is the set of fluents
    that:

    1. are **shared** preconditions across *all* rules at distance
       D - 1 (the next-closer phase), or are **goal fluents** when
       D = 1, **and**
    2. are **add-effects** of at least one action in the current phase.

    Using the *intersection* of successor-rule preconditions (rather
    than the union) ensures that only universally-required fluents
    are checked.  Complementary pairs like ``closed(d)``/``open(d)``
    representing alternative scenarios are naturally excluded.
    """
    rd = dist_result.rule_dist

    # Build distance -> set of rule indices.
    dist_to_rules: Dict[int, List[int]] = defaultdict(list)
    for ridx, d in rd.items():
        dist_to_rules[d].append(ridx)

    # Collect the *common* (intersection) preconditions of rules at
    # each distance -- what ANY successor path requires.
    dist_common_preconds: Dict[int, FrozenSet[str]] = {}
    for d, ridxs in dist_to_rules.items():
        cond_sets = [
            frozenset(str(lit).strip().lower() for lit in rules[ridx].condition)
            for ridx in ridxs
        ]
        common = cond_sets[0]
        for cs in cond_sets[1:]:
            common = common & cs
        dist_common_preconds[d] = common

    # Goal fluents serve as the target for the closest-to-goal phase.
    goal_target: FrozenSet[str] = frozenset()
    goal_pos = frozenset(f.lower() for f in causal.goal_fluents)
    goal_neg = frozenset(f"not({f.lower()})" for f in causal.goal_neg_fluents)
    goal_target = goal_pos | goal_neg

    phase_postconds: Dict[int, FrozenSet[str]] = {}
    for d, ridxs in dist_to_rules.items():
        # What the successor phase(s) need.
        if d <= 1:
            # Closest to goal -- successor is the goal itself.
            target_fluents = goal_target
        else:
            # Common preconditions of rules at distance d-1.
            target_fluents = dist_common_preconds.get(d - 1, frozenset())

        if not target_fluents:
            continue

        # What does this phase produce?
        phase_adds: Set[str] = set()
        for ridx in ridxs:
            action = rules[ridx].action
            ga = _lookup_action(action, causal)
            if ga is not None:
                for a in ga.all_adds:
                    phase_adds.add(a.lower())

        # Post-condition = intersection of target and production.
        postcond = frozenset(
            f for f in target_fluents if f in phase_adds
        )
        if postcond:
            phase_postconds[d] = postcond

    return phase_postconds


def _compute_action_postconditions(
    action: str,
    causal: Optional[CausalInfo],
    phase_postcond: FrozenSet[str],
) -> FrozenSet[str]:
    """Derive action-level post-conditions filtered to phase-relevant effects.

    Returns the subset of *phase_postcond* fluents that are add-effects
    of *action*.  Returns an empty frozenset when causal info is
    unavailable or no relevant effects exist.
    """
    if not causal or not phase_postcond:
        return frozenset()
    ga = _lookup_action(action, causal)
    if ga is None:
        return frozenset()
    action_adds = {a.lower() for a in ga.all_adds}
    return frozenset(f for f in phase_postcond if f in action_adds)


def _compute_recovery_postconditions(
    recovery_action: str,
    primary_action: str,
    causal: Optional[CausalInfo],
) -> FrozenSet[str]:
    """Derive post-conditions for a recovery action in a fallback pair.

    The recovery action's purpose is to re-establish a precondition of
    the primary action (e.g. ``climb`` achieves ``up()`` which is a
    precondition of ``walk-on-beam``).  The post-condition is the
    intersection of the recovery's add-effects and the primary's
    preconditions.
    """
    if not causal:
        return frozenset()
    ga_recovery = _lookup_action(recovery_action, causal)
    ga_primary = _lookup_action(primary_action, causal)
    if ga_recovery is None or ga_primary is None:
        return frozenset()
    recovery_adds = {a.lower() for a in ga_recovery.all_adds}
    primary_preconds = {p.lower() for p in ga_primary.preconditions}
    return frozenset(f for f in primary_preconds if f in recovery_adds)


def _lookup_action(
    action: str,
    causal: CausalInfo,
) -> Optional["GroundedAction"]:
    """Case-insensitive lookup of a grounded action in causal info."""
    from bt_policy.causal import GroundedAction
    ga = causal.actions.get(action)
    if ga is not None:
        return ga
    action_lower = action.lower()
    ga = causal.actions.get(action_lower)
    if ga is not None:
        return ga
    for k, v in causal.actions.items():
        if k.lower() == action_lower:
            return v
    return None


# ===================================================================
#  Complementary-pair (fallback) detection
# ===================================================================


@dataclass
class _FallbackGroup:
    """A pair of rules differing by exactly one complementary literal."""
    shared: FrozenSet[str]
    pos_literal: str
    pos_rule: "PolicyRule"
    neg_rule: "PolicyRule"


@dataclass
class _DistanceGroupItems:
    """Items in a distance group: pre-identified pairs + remaining singles."""
    pairs: List[_FallbackGroup] = field(default_factory=list)
    singles: List["PolicyRule"] = field(default_factory=list)


@dataclass
class _DistanceResult:
    """Full result of distance computation, including the policy graph."""
    rule_dist: Dict[int, int]
    """Rule index → distance-to-goal."""
    forward: Dict[int, List[int]]
    """State-id → list of successor state-ids (closer to goal)."""
    state_index: Dict[FrozenSet[str], int]
    """Literal signature → state-id."""
    state_list: List[FrozenSet[str]]
    """State-id → literal signature."""
    state_rules: Dict[int, List[int]]
    """State-id → list of rule indices active in that state."""
    goal_node: int
    """Virtual goal node id."""


def _find_complementary_pairs(
    rules: List["PolicyRule"],
) -> Tuple[List[Tuple[_FallbackGroup, int, int]], List[Tuple["PolicyRule", int]]]:
    """Detect rules differing by exactly one complementary literal pair."""
    used: Set[int] = set()
    pairs: List[Tuple[_FallbackGroup, int, int]] = []

    for i in range(len(rules)):
        if i in used:
            continue
        for j in range(i + 1, len(rules)):
            if j in used:
                continue
            ci = rules[i].condition
            cj = rules[j].condition
            diff_i = ci - cj
            diff_j = cj - ci

            if len(diff_i) != 1 or len(diff_j) != 1:
                continue

            lit_i = next(iter(diff_i))
            lit_j = next(iter(diff_j))
            base_i, neg_i = strip_negation(lit_i)
            base_j, neg_j = strip_negation(lit_j)

            if base_i != base_j or neg_i == neg_j:
                continue

            shared = ci & cj
            if neg_i:
                pos_rule, neg_rule = rules[j], rules[i]
                pos_literal = lit_j
                idx_pos, idx_neg = j, i
            else:
                pos_rule, neg_rule = rules[i], rules[j]
                pos_literal = lit_i
                idx_pos, idx_neg = i, j

            pairs.append((_FallbackGroup(
                shared=shared,
                pos_literal=pos_literal,
                pos_rule=pos_rule,
                neg_rule=neg_rule,
            ), idx_pos, idx_neg))
            used.add(i)
            used.add(j)
            break

    remaining = [(r, idx) for idx, r in enumerate(rules) if idx not in used]
    return pairs, remaining


# ===================================================================
#  Mutex-family detection
# ===================================================================


def _find_mutex_family_rules(
    rules: List["PolicyRule"],
) -> Optional[Tuple[str, int, Dict[str, List["PolicyRule"]]]]:
    """Detect mutually-exclusive predicate family for multi-way dispatch."""
    lit_to_idxs: Dict[str, List[int]] = defaultdict(list)
    for idx, r in enumerate(rules):
        for lit in r.condition:
            _base, neg = strip_negation(lit)
            if not neg:
                lit_to_idxs[lit].append(idx)

    pred_groups: Dict[Tuple[str, int], List[Tuple[str, List[str]]]] = defaultdict(list)
    for lit in lit_to_idxs:
        parsed = parse_predicate(lit)
        if parsed:
            pname, args = parsed
            pred_groups[(pname, len(args))].append((lit, args))

    best = None
    for (_pname, arity), members in pred_groups.items():
        if len(members) < 2:
            continue
        for vary_pos in range(arity):
            fixed = None
            ok = True
            for _lit, args in members:
                key = tuple(a for i, a in enumerate(args) if i != vary_pos)
                if fixed is None:
                    fixed = key
                elif key != fixed:
                    ok = False
                    break
            if not ok or fixed is None:
                continue

            family_key = (
                f"{_pname}({', '.join('*' if i == vary_pos else a for i, a in enumerate(members[0][1]))})"
            )

            dispatch: Dict[str, List["PolicyRule"]] = defaultdict(list)
            covered_idxs: Set[int] = set()
            for lit, _args in members:
                for widx in lit_to_idxs[lit]:
                    dispatch[lit].append(rules[widx])
                    covered_idxs.add(widx)

            if len(dispatch) < 2:
                continue

            rule_family_count = [0] * len(rules)
            for lit, _args in members:
                for widx in lit_to_idxs[lit]:
                    rule_family_count[widx] += 1
            if any(c > 1 for c in rule_family_count):
                continue

            coverage = len(covered_idxs)
            family_size = len(dispatch)

            if best is None or (
                coverage > best[3]
                or (coverage == best[3] and family_size > best[4])
            ):
                best = (family_key, vary_pos, dict(dispatch), coverage, family_size)

    if best is None:
        return None
    fkey, vary_pos, dispatch, coverage, _fs = best
    if coverage < 3 or len(dispatch) < 2:
        return None
    return fkey, vary_pos, dispatch


# ===================================================================
#  Tree construction helpers
# ===================================================================


def _hoist_common(
    rules: List["PolicyRule"],
) -> Tuple[FrozenSet[str], List["PolicyRule"]]:
    """Extract conditions shared by ALL rules and return reduced rules."""
    if not rules:
        return frozenset(), []

    common = set(rules[0].condition)
    for r in rules[1:]:
        common &= r.condition
    if not common:
        return frozenset(), rules

    from pr2_bridge.adapter import PolicyRule
    common_fs = frozenset(common)
    reduced = [
        PolicyRule(
            condition=frozenset(r.condition - common_fs),
            action=r.action,
            action_name=r.action_name,
            action_args=r.action_args,
        )
        for r in rules
    ]
    return common_fs, reduced


def _build_goal_branch(goal_rules: List["PolicyRule"]) -> Optional[BTNode]:
    """Build the goal-check branch from all ``goal`` policy rules.

    Uses the shared ``_build_postcond_check`` helper -- the goal branch
    is semantically the post-condition gate for the entire plan
    (distance-0 check).
    """
    if not goal_rules:
        return None

    all_conds: List[BTNode] = []
    for rule in goal_rules:
        cond = _build_postcond_check(frozenset(rule.condition), "GoalCond")
        if cond is not None:
            all_conds.append(cond)

    if not all_conds:
        return None

    goal_ok = all_conds[0] if len(all_conds) == 1 else ReactiveSelector("GoalCheck", all_conds)
    return ReactiveSequence("GoalBranch", [goal_ok, SuccessLeaf()])


def _build_action_leaf(
    rule: "PolicyRule",
    fsaps: List["FSAP"],
    context: FrozenSet[str],
    causal: Optional[CausalInfo] = None,
    phase_postcond: FrozenSet[str] = frozenset(),
) -> BTNode:
    """Build a leaf node for a single action rule."""
    children: List[BTNode] = _condition_nodes(rule.condition)

    full_context = context | rule.condition
    guard = _build_fsap_guard(rule.action, fsaps, context=full_context)
    if guard is not None:
        children.append(guard)

    children.append(ActionNode(rule.action))

    action_id = readable_action_id(rule.action)
    node = ReactiveSequence(action_id, children, is_rule_leaf=True)

    # Wrap with action-level post-condition gate.
    # Skip when the action postcond is identical to the phase postcond —
    # the group-level gate already covers it and avoids double-wrapping.
    action_postcond = _compute_action_postconditions(
        rule.action, causal, phase_postcond,
    )
    if action_postcond and action_postcond != phase_postcond:
        node = _wrap_with_postcond_gate(node, action_postcond, f"{action_id}_Done")
    return node


def _build_fallback_branch(
    group: _FallbackGroup,
    fsaps: List["FSAP"],
    context: FrozenSet[str],
    causal: Optional[CausalInfo] = None,
    phase_postcond: FrozenSet[str] = frozenset(),
) -> BTNode:
    """Build a try/recover fallback from a complementary-pair group."""
    shared_ctx = context | group.shared

    # Positive branch.
    pos_remaining = group.pos_rule.condition - group.shared - {group.pos_literal}
    pos_children: List[BTNode] = [ConditionNode(group.pos_literal)]
    pos_children.extend(_condition_nodes(pos_remaining))
    pos_ctx = shared_ctx | {group.pos_literal} | pos_remaining
    pos_guard = _build_fsap_guard(group.pos_rule.action, fsaps, context=pos_ctx)
    if pos_guard is not None:
        pos_children.append(pos_guard)
    pos_children.append(ActionNode(group.pos_rule.action))
    pos_id = readable_action_id(group.pos_rule.action)
    pos_branch = ReactiveSequence(pos_id, pos_children, is_rule_leaf=True)

    # Negative branch (complement elision — no neg gate needed).
    neg_literal = f"not({group.pos_literal})"
    neg_remaining = group.neg_rule.condition - group.shared - {neg_literal}
    neg_children: List[BTNode] = list(_condition_nodes(neg_remaining))
    neg_ctx = shared_ctx | {neg_literal} | neg_remaining
    neg_guard = _build_fsap_guard(group.neg_rule.action, fsaps, context=neg_ctx)
    if neg_guard is not None:
        neg_children.append(neg_guard)
    neg_children.append(ActionNode(group.neg_rule.action))
    neg_id = readable_action_id(group.neg_rule.action)
    neg_branch = ReactiveSequence(neg_id, neg_children, is_rule_leaf=True)

    # Recovery-branch post-condition: the recovery action's add-effects that
    # satisfy the primary action's preconditions (e.g. climb→up() enables
    # walk-on-beam).  This lets the fallback skip recovery when its purpose
    # is already fulfilled.
    neg_postcond = _compute_recovery_postconditions(
        group.neg_rule.action, group.pos_rule.action, causal,
    )
    if neg_postcond:
        neg_branch = _wrap_with_postcond_gate(
            neg_branch, neg_postcond, f"{neg_id}_Done",
        )

    fallback = ReactiveSelector(
        f"{pos_id}_OrFallback", [pos_branch, neg_branch],
    )

    if group.shared:
        shared_children = _condition_nodes(group.shared)
        shared_children.append(fallback)
        return ReactiveSequence(
            f"Exec_{pos_id}", shared_children, is_rule_leaf=True,
        )
    fallback.is_rule_leaf = True
    return fallback


def _build_merged_action_branch(
    rules: List["PolicyRule"],
    fsaps: List["FSAP"],
    context: FrozenSet[str],
    causal: Optional[CausalInfo] = None,
    phase_postcond: FrozenSet[str] = frozenset(),
) -> BTNode:
    """Build a branch for multiple rules sharing the same action."""
    assert len(rules) >= 2
    action = rules[0].action

    common, reduced = _hoist_common(rules)
    full_ctx = context | common

    action_id = readable_action_id(action)
    scenario_branches: List[BTNode] = []
    for idx, r in enumerate(reduced):
        if not r.condition:
            scenario_branches = []
            break
        ordered = sorted(r.condition)
        if len(ordered) == 1:
            scenario_branches.append(ConditionNode(ordered[0]))
        else:
            scenario_branches.append(
                ReactiveSequence(f"When_{action_id}_{idx}",
                                 [ConditionNode(f) for f in ordered])
            )

    children: List[BTNode] = _condition_nodes(common)

    if scenario_branches:
        if len(scenario_branches) == 1:
            children.append(scenario_branches[0])
        else:
            children.append(
                ReactiveSelector(f"Scenarios_{action_id}", scenario_branches)
            )

    guard = _build_fsap_guard(action, fsaps, context=full_ctx)
    if guard is not None:
        children.append(guard)

    children.append(ActionNode(action))

    node = ReactiveSequence(action_id, children, is_rule_leaf=True)

    # Wrap with action-level post-condition gate.
    # Skip when identical to phase postcond to avoid double-wrapping.
    action_postcond = _compute_action_postconditions(
        action, causal, phase_postcond,
    )
    if action_postcond and action_postcond != phase_postcond:
        node = _wrap_with_postcond_gate(node, action_postcond, f"{action_id}_Done")
    return node


# ===================================================================
#  Distance-group tree builder
# ===================================================================


def _build_group_subtree(
    items: _DistanceGroupItems,
    fsaps: List["FSAP"],
    context: FrozenSet[str],
    group_name: str,
    causal: Optional[CausalInfo] = None,
    phase_postcond: FrozenSet[str] = frozenset(),
) -> BTNode:
    """Build the subtree for a single distance group."""
    # Fast paths.
    if not items.pairs and len(items.singles) == 1:
        return _build_action_leaf(
            items.singles[0], fsaps, context, causal, phase_postcond,
        )
    if not items.pairs and not items.singles:
        return FailureLeaf("EmptyGroup")

    # ── Cross-item hoisting: conditions shared by ALL rules in this group ─
    # Collect every rule condition set (both pair members and singles).
    all_rule_conds: List[FrozenSet[str]] = []
    for pair in items.pairs:
        all_rule_conds.append(frozenset(pair.pos_rule.condition))
        all_rule_conds.append(frozenset(pair.neg_rule.condition))
    for s in items.singles:
        all_rule_conds.append(frozenset(s.condition))

    group_common: FrozenSet[str] = frozenset()
    if len(all_rule_conds) >= 2:
        group_common = all_rule_conds[0]
        for cs in all_rule_conds[1:]:
            group_common &= cs

    if group_common:
        from pr2_bridge.adapter import PolicyRule as _PR
        # Strip common conditions from pairs.
        new_pairs: List[_FallbackGroup] = []
        for pair in items.pairs:
            new_pos = _PR(
                condition=frozenset(pair.pos_rule.condition - group_common),
                action=pair.pos_rule.action,
                action_name=pair.pos_rule.action_name,
                action_args=pair.pos_rule.action_args,
            )
            new_neg = _PR(
                condition=frozenset(pair.neg_rule.condition - group_common),
                action=pair.neg_rule.action,
                action_name=pair.neg_rule.action_name,
                action_args=pair.neg_rule.action_args,
            )
            new_pairs.append(_FallbackGroup(
                shared=pair.shared - group_common,
                pos_literal=pair.pos_literal,
                pos_rule=new_pos,
                neg_rule=new_neg,
            ))
        # Strip common conditions from singles.
        new_singles = [
            _PR(
                condition=frozenset(s.condition - group_common),
                action=s.action,
                action_name=s.action_name,
                action_args=s.action_args,
            )
            for s in items.singles
        ]
        items = _DistanceGroupItems(pairs=new_pairs, singles=new_singles)
        context = context | group_common

    branches: List[BTNode] = []

    # Fallback branches from pre-identified pairs.
    for pair in items.pairs:
        branches.append(_build_fallback_branch(
            pair, fsaps, context, causal, phase_postcond,
        ))

    # Handle singles.
    if items.singles:
        singles = items.singles

        common_singles: FrozenSet[str] = frozenset()
        reduced_singles = singles
        if len(singles) > 1:
            common_singles, reduced_singles = _hoist_common(singles)

        singles_ctx = context | common_singles

        by_action: Dict[str, List["PolicyRule"]] = defaultdict(list)
        for r in reduced_singles:
            by_action[r.action].append(r)

        plain_singles: List["PolicyRule"] = []
        merged_groups: List[List["PolicyRule"]] = []
        for action, group_rules in sorted(by_action.items()):
            if len(group_rules) == 1:
                plain_singles.append(group_rules[0])
            else:
                merged_groups.append(group_rules)

        # Mutex family among plain singles.
        mutex_branch: Optional[BTNode] = None
        mutex_consumed: Set[str] = set()
        if len(plain_singles) >= 3:
            family = _find_mutex_family_rules(plain_singles)
            if family is not None:
                _fkey, _vary_pos, dispatch = family
                dispatch_children: List[BTNode] = []
                for lit in sorted(dispatch):
                    lit_rules = dispatch[lit]
                    from pr2_bridge.adapter import PolicyRule as PR
                    sub_rules = [
                        PR(
                            condition=frozenset(r.condition - {lit}),
                            action=r.action,
                            action_name=r.action_name,
                            action_args=r.action_args,
                        )
                        for r in lit_rules
                    ]
                    lit_ctx = singles_ctx | {lit}
                    sub_items = _DistanceGroupItems(singles=sub_rules)
                    inner = _build_group_subtree(
                        sub_items, fsaps, lit_ctx,
                        f"{group_name}_{readable_action_id(lit)}",
                        causal, phase_postcond,
                    )
                    branch = ReactiveSequence(
                        f"At_{readable_action_id(lit)}",
                        [ConditionNode(lit), inner]
                        if isinstance(inner, (ReactiveSelector, ReactiveSequence))
                        else [ConditionNode(lit)]
                        + (
                            [inner]
                            if not isinstance(inner, ReactiveSequence)
                            else list(inner.children)
                        ),
                    )
                    dispatch_children.append(branch)
                    for r in lit_rules:
                        mutex_consumed.add(r.action)

                if len(dispatch_children) >= 2:
                    mutex_branch = ReactiveSelector(
                        f"{group_name}_Dispatch", dispatch_children,
                    )

        plain_singles = [s for s in plain_singles if s.action not in mutex_consumed]

        singles_branches: List[BTNode] = []
        for mg in merged_groups:
            singles_branches.append(
                _build_merged_action_branch(
                    mg, fsaps, singles_ctx, causal, phase_postcond,
                )
            )
        if mutex_branch is not None:
            singles_branches.append(mutex_branch)
        for s in plain_singles:
            singles_branches.append(
                _build_action_leaf(s, fsaps, singles_ctx, causal, phase_postcond)
            )

        if singles_branches:
            if common_singles:
                inner_singles = (
                    singles_branches[0]
                    if len(singles_branches) == 1
                    else ReactiveSelector(
                        f"{group_name}_singles", singles_branches
                    )
                )
                gate = ReactiveSequence(
                    f"{group_name}_gate",
                    _condition_nodes(common_singles) + [inner_singles],
                )
                branches.append(gate)
            else:
                branches.extend(singles_branches)

    # Wrap.
    if not branches:
        return FailureLeaf("EmptyGroup")
    if len(branches) == 1:
        result = branches[0]
    else:
        result = ReactiveSelector(group_name, branches, is_rule_leaf=True)

    # If we hoisted group-common conditions, gate the entire subtree.
    if group_common:
        gate_children = _condition_nodes(group_common) + [result]
        result = ReactiveSequence(f"{group_name}_common", gate_children, is_rule_leaf=True)

    return result


# ===================================================================
#  Main entry point
# ===================================================================


def policy_to_bt(result: "PR2Result") -> BehaviorTree:
    """Convert a PR2 policy into a goal-distance-ordered reactive BT."""
    goal_rules = [r for r in result.policy if r.action_name == "goal"]
    action_rules = [r for r in result.policy if r.action_name != "goal"]

    # Causal analysis for goal-distance ordering.
    causal: Optional[CausalInfo] = None
    policy_action_names = {r.action for r in action_rules}

    if result.domain_pddl and result.problem_pddl:
        try:
            causal = build_causal_info(
                result.domain_pddl,
                result.problem_pddl,
                policy_action_names,
            )
        except Exception as e:
            import sys
            print(
                f"Warning: causal analysis failed ({e}), skipping distance ordering",
                file=sys.stderr,
            )
            causal = None

    # Goal branch.
    branches: List[BTNode] = []
    goal_branch = _build_goal_branch(goal_rules)
    if goal_branch is not None:
        branches.append(goal_branch)

    if not action_rules:
        if not branches:
            branches.append(FailureLeaf("EmptyPolicy"))
        root = ReactiveSelector("PolicyRoot", branches)
        return BehaviorTree(root)

    # Compute distances on ORIGINAL rules (before stripping).
    dist_result: Optional[_DistanceResult] = None
    if causal is not None:
        dist_result = _compute_rule_distances(action_rules, causal)
        rule_dist = dist_result.rule_dist
    else:
        rule_dist = {i: 0 for i in range(len(action_rules))}

    # Cross-distance hoisting.
    all_conditions_common: FrozenSet[str] = frozenset()
    if action_rules:
        all_conditions_common = frozenset(action_rules[0].condition)
        for r in action_rules[1:]:
            all_conditions_common &= r.condition

    outer_ctx = all_conditions_common

    hoisted_rules = (
        _strip_conditions(action_rules, all_conditions_common)
        if all_conditions_common
        else action_rules
    )

    # Find complementary pairs across all rules.
    pairs_indexed, remaining_indexed = _find_complementary_pairs(hoisted_rules)

    # Group pairs + singles by distance.
    dist_items: Dict[int, _DistanceGroupItems] = defaultdict(_DistanceGroupItems)

    for pair_group, idx_pos, idx_neg in pairs_indexed:
        pair_dist = min(rule_dist[idx_pos], rule_dist[idx_neg])
        dist_items[pair_dist].pairs.append(pair_group)

    for rule, idx in remaining_indexed:
        dist_items[rule_dist[idx]].singles.append(rule)

    sorted_distances = sorted(dist_items.keys())

    # Compute per-phase post-conditions from the policy graph.
    phase_postconds: Dict[int, FrozenSet[str]] = {}
    if dist_result is not None and causal is not None:
        phase_postconds = _compute_phase_postconditions(
            dist_result, action_rules, causal,
        )

    # Build per-distance subtrees.
    group_branches: List[BTNode] = []
    for dist in sorted_distances:
        items = dist_items[dist]
        if not items.pairs and not items.singles:
            continue
        if items.pairs and not items.singles:
            primary = items.pairs[0].pos_rule.action
            group_name = (
                readable_action_id(primary) + "_WithRecovery"
                if len(items.pairs) == 1
                else "Phase_" + readable_action_id(items.pairs[0].pos_rule.action)
            )
        elif items.singles and not items.pairs:
            if len(items.singles) == 1:
                group_name = readable_action_id(items.singles[0].action)
            else:
                group_name = "Phase_" + readable_action_id(items.singles[0].action)
        else:
            first = items.pairs[0].pos_rule.action if items.pairs else items.singles[0].action
            group_name = "Phase_" + readable_action_id(first)

        postcond = phase_postconds.get(dist, frozenset())
        subtree = _build_group_subtree(
            items, result.fsaps, outer_ctx, group_name, causal, postcond,
        )
        # Wrap with group-level post-condition gate.
        if postcond:
            subtree = _wrap_with_postcond_gate(
                subtree, postcond, f"{group_name}_Done",
            )
        group_branches.append(subtree)

    # Mark ALL Progression children for extraction as subtree definitions.
    for branch in group_branches:
        branch.is_rule_leaf = True

    # Assemble progression tree.
    if len(group_branches) == 1:
        progression = group_branches[0]
    else:
        progression = ReactiveSelector("Progression", group_branches)

    if all_conditions_common:
        gate_children = _condition_nodes(all_conditions_common)
        gate_children.append(progression)
        branches.append(ReactiveSequence("PolicyRules", gate_children))
    else:
        branches.append(progression)

    if not branches:
        branches.append(FailureLeaf("EmptyPolicy"))

    root = ReactiveSelector("PolicyRoot", branches)

    bt = BehaviorTree(root)
    parameterize_subtrees(bt)
    bt.root = deduplicate_subtrees(bt.root)
    return bt

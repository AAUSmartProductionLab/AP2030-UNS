from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Tuple


@dataclass(frozen=True)
class PolicyTransition:
    source: int
    target: int
    action: str
    transition_type: str
    outcome: int | str | None


@dataclass
class PolicyStateGraph:
    state_index: Dict[FrozenSet[str], int]
    state_signatures: List[FrozenSet[str]]
    state_actions: Dict[FrozenSet[str], Set[str]]
    state_parts: Dict[FrozenSet[str], Tuple[FrozenSet[str], FrozenSet[str]]]
    transitions: List[PolicyTransition]
    distances: Dict[int, int]
    goal_node_id: int
    unmapped_node_id: int
    initial_state_id: Optional[int]


def build_policy_state_graph(
    rules: List,
    get_action_outcomes: Callable[[str], Optional[List[Tuple[FrozenSet[str], FrozenSet[str]]]]],
    *,
    goal_positive: Optional[Set[str]] = None,
    goal_negative: Optional[Set[str]] = None,
    init_fluents: Optional[Set[str]] = None,
) -> PolicyStateGraph:
    """Build state signatures, transitions, and goal distances for a policy."""
    state_index: Dict[FrozenSet[str], int] = {}
    state_signatures: List[FrozenSet[str]] = []
    state_actions: Dict[FrozenSet[str], Set[str]] = {}
    state_parts: Dict[FrozenSet[str], Tuple[FrozenSet[str], FrozenSet[str]]] = {}

    for rule in rules:
        signature = _rule_signature(rule)
        if signature not in state_index:
            state_index[signature] = len(state_signatures)
            state_signatures.append(signature)
            state_actions[signature] = set()
            state_parts[signature] = _split_state_literals(signature)
        state_actions[signature].add(_rule_action_name(rule))

    goal_node_id = len(state_signatures)
    unmapped_node_id = goal_node_id + 1

    goal_pos = frozenset(s.lower() for s in (goal_positive or set()))
    goal_neg = frozenset(s.lower() for s in (goal_negative or set()))

    transitions: List[PolicyTransition] = []

    for signature in state_signatures:
        source_id = state_index[signature]
        source_positive, source_negative = state_parts[signature]

        for action in sorted(state_actions[signature]):
            action_key = action.strip().lower()
            if action_key == "goal" or "goal" in action_key:
                transitions.append(
                    PolicyTransition(
                        source=source_id,
                        target=goal_node_id,
                        action=action,
                        transition_type="goal",
                        outcome="goal",
                    )
                )
                continue

            outcomes = get_action_outcomes(action)
            if not outcomes:
                transitions.append(
                    PolicyTransition(
                        source=source_id,
                        target=unmapped_node_id,
                        action=action,
                        transition_type="unmapped",
                        outcome=None,
                    )
                )
                continue

            for outcome_idx, (adds, dels) in enumerate(outcomes):
                sim_positive, sim_negative = _apply_outcome(
                    source_positive,
                    source_negative,
                    adds,
                    dels,
                )

                best_target = None
                best_score = -1
                for candidate_signature in state_signatures:
                    cand_positive, cand_negative = state_parts[candidate_signature]
                    score = _state_match_score(
                        cand_positive,
                        cand_negative,
                        sim_positive,
                        sim_negative,
                    )
                    if score > best_score:
                        best_score = score
                        best_target = candidate_signature

                if best_target is not None and best_score >= 0:
                    transitions.append(
                        PolicyTransition(
                            source=source_id,
                            target=state_index[best_target],
                            action=action,
                            transition_type="transition",
                            outcome=outcome_idx,
                        )
                    )
                    continue

                if goal_pos and goal_pos.issubset(sim_positive) and goal_neg.issubset(sim_negative):
                    transitions.append(
                        PolicyTransition(
                            source=source_id,
                            target=goal_node_id,
                            action=action,
                            transition_type="goal",
                            outcome=outcome_idx,
                        )
                    )
                else:
                    transitions.append(
                        PolicyTransition(
                            source=source_id,
                            target=unmapped_node_id,
                            action=action,
                            transition_type="unmapped",
                            outcome=outcome_idx,
                        )
                    )

    reverse: Dict[int, List[int]] = defaultdict(list)
    for edge in transitions:
        reverse[edge.target].append(edge.source)

    distances: Dict[int, int] = {goal_node_id: 0}
    queue: deque[int] = deque([goal_node_id])
    while queue:
        current = queue.popleft()
        for predecessor in reverse.get(current, []):
            if predecessor not in distances:
                distances[predecessor] = distances[current] + 1
                queue.append(predecessor)

    initial_state_id: Optional[int] = None
    if state_signatures and init_fluents:
        init_positive = frozenset(x.lower() for x in init_fluents)

        # Prefer signatures that are actually applicable in the initial state,
        # i.e., all required positives hold and required negatives are absent.
        applicable_best_state = None
        applicable_best_specificity = -1
        for signature in state_signatures:
            cand_positive, cand_negative = state_parts[signature]
            if cand_positive.issubset(init_positive) and cand_negative.isdisjoint(init_positive):
                specificity = len(cand_positive) + len(cand_negative)
                if specificity > applicable_best_specificity:
                    applicable_best_specificity = specificity
                    applicable_best_state = signature

        if applicable_best_state is not None:
            initial_state_id = state_index[applicable_best_state]
        else:
            # Fallback: choose the closest partial state if no signature is
            # fully applicable in the initial fluent set.
            best_state = None
            best_score = float("-inf")
            for signature in state_signatures:
                cand_positive, cand_negative = state_parts[signature]
                score = _state_init_similarity_score(cand_positive, cand_negative, init_positive)
                if score > best_score:
                    best_score = score
                    best_state = signature
            if best_state is not None:
                initial_state_id = state_index[best_state]
    elif state_signatures:
        initial_state_id = 0

    return PolicyStateGraph(
        state_index=state_index,
        state_signatures=state_signatures,
        state_actions=state_actions,
        state_parts=state_parts,
        transitions=transitions,
        distances=distances,
        goal_node_id=goal_node_id,
        unmapped_node_id=unmapped_node_id,
        initial_state_id=initial_state_id,
    )


def compute_rule_distances(rules: List, graph: PolicyStateGraph) -> Dict[int, int]:
    max_dist = max(graph.distances.values()) if graph.distances else 0
    result: Dict[int, int] = {}

    for ridx, rule in enumerate(rules):
        signature = _rule_signature(rule)
        state_id = graph.state_index.get(signature)
        if state_id is not None and state_id in graph.distances:
            result[ridx] = graph.distances[state_id]
        else:
            result[ridx] = max_dist + 1

    return result


def _rule_signature(rule) -> FrozenSet[str]:
    return frozenset(_rule_condition_literals(rule))


def _rule_action_name(rule) -> str:
    """Return action name from a PolicyRule (handles both old raw-str and new object API)."""
    if hasattr(rule, "action_name"):
        args = getattr(rule, "action_args", ())
        if args:
            return f"{rule.action_name}({', '.join(str(a) for a in args)})"
        return rule.action_name
    return str(rule.action)


def _rule_condition_literals(rule) -> list:
    """Return condition as a list of normalised literal strings.

    Supports both the legacy API (iterable of string literals) and the new
    UP PolicyRule API where ``rule.condition`` is a ``{FNode: FNode}`` dict
    mapping fluent expressions to Boolean FNodes (true/false).
    """
    if hasattr(rule, "raw_condition_literals"):
        return [s.strip().lower() for s in rule.raw_condition_literals]
    cond = rule.condition
    if isinstance(cond, dict):
        result = []
        for fluent, value in cond.items():
            lit = str(fluent).strip().lower()
            if str(value) == "false":
                lit = f"not({lit})"
            result.append(lit)
        return result
    return [str(lit).strip().lower() for lit in cond]

def _split_state_literals(signature: FrozenSet[str]) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    positive: Set[str] = set()
    negative: Set[str] = set()
    for lit in signature:
        if lit.startswith("not(") and lit.endswith(")"):
            negative.add(lit[4:-1])
        else:
            positive.add(lit)
    return frozenset(positive), frozenset(negative)


def _state_init_similarity_score(
    candidate_positive: FrozenSet[str],
    candidate_negative: FrozenSet[str],
    init_positive: FrozenSet[str],
) -> float:
    pos_match = len(candidate_positive & init_positive)
    pos_missing = len(candidate_positive - init_positive)
    contradicted_negative = len(candidate_negative & init_positive)
    return (2.0 * pos_match) - (1.0 * pos_missing) - (2.5 * contradicted_negative)


def _apply_outcome(
    positive: FrozenSet[str],
    negative: FrozenSet[str],
    adds: FrozenSet[str],
    dels: FrozenSet[str],
) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    next_positive = set(positive)
    next_negative = set(negative)

    for fluent in dels:
        f = fluent.strip().lower()
        if not f:
            continue
        next_positive.discard(f)
        next_negative.add(f)

    for fluent in adds:
        f = fluent.strip().lower()
        if not f:
            continue
        next_negative.discard(f)
        next_positive.add(f)

    return frozenset(next_positive), frozenset(next_negative)


def _state_match_score(
    candidate_positive: FrozenSet[str],
    candidate_negative: FrozenSet[str],
    simulated_positive: FrozenSet[str],
    simulated_negative: FrozenSet[str],
) -> int:
    if not candidate_positive.issubset(simulated_positive):
        return -1
    if not candidate_negative.issubset(simulated_negative):
        return -1

    pos_hits = len(candidate_positive & simulated_positive)
    neg_hits = len(candidate_negative & simulated_negative)
    return pos_hits + neg_hits

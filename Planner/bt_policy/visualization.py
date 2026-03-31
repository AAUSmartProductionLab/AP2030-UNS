#!/usr/bin/env python3
"""
Generate interactive policy state-transition visualization for PR2 policies.

Aligned with PRP++ snapshot-viz conventions (Christian Muise):
- Nodes labelled as "action (distance-to-goal)"
- Colours: golden=goal, green=init, blue=strong-cyclic, red=undefined, gray=default
- Top-to-bottom directed flow layout
- Hover shows partial-state fluent list
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from string import Template
from typing import Dict, FrozenSet, List, Set, Tuple

from bt_policy.literals import normalize_literal, split_state_literals
from bt_policy.simulator import build_simulator
from pr2_bridge.adapter import PR2Result

# PRP-aligned colour scheme
_COLOR_GOAL = "#e8c100"       # Golden for goal nodes
_COLOR_INIT = "#067c00"       # Green for the initial state
_COLOR_SC = "#025ef2"         # Blue for strong-cyclic nodes
_COLOR_UNDEFINED = "#930000"  # Red for undefined / unmapped successor
_COLOR_DEFAULT = "#828282"    # Gray as default


def _state_init_similarity_score(
    candidate_positive: FrozenSet[str],
    candidate_negative: FrozenSet[str],
    init_positive: FrozenSet[str],
) -> float:
    """Soft score for choosing an initial policy node from init fluents."""
    pos_match = len(candidate_positive & init_positive)
    pos_missing = len(candidate_positive - init_positive)
    contradicted_negative = len(candidate_negative & init_positive)
    return (2.0 * pos_match) - (1.0 * pos_missing) - (2.5 * contradicted_negative)


def _make_state_name(actions: Set[str], distance: int = -1) -> str:
    """Create a PRP-style state label: 'action (distance)'.

    Follows the PRP++ snapshot-viz convention where each policy-state
    node is labeled by the action taken there and its distance to goal.
    """
    action_label = ", ".join(sorted(actions)) if actions else "noop"
    if distance == 0:
        return "Goal"
    if distance < 0:
        return action_label
    return f"{action_label} ({distance})"


def _apply_outcome(
    positive: FrozenSet[str],
    negative: FrozenSet[str],
    adds: FrozenSet[str],
    dels: FrozenSet[str],
) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """Apply one grounded action outcome to a state."""
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
    """Return match score if candidate state is satisfied, else -1."""
    if not candidate_positive.issubset(simulated_positive):
        return -1
    if not candidate_negative.issubset(simulated_negative):
        return -1

    pos_hits = len(candidate_positive & simulated_positive)
    neg_hits = len(candidate_negative & simulated_negative)
    return pos_hits + neg_hits


def policy_to_state_graph_data(result: PR2Result) -> Dict:
    """
    Convert a PR2 policy into an explicit state-transition graph.

    If PDDL context is available, transitions are derived from grounded action
    outcomes. If not, graph still includes policy-state nodes but no transitions.
    """
    nodes: List[Dict] = []
    links: List[Dict] = []

    # Build unique state signatures from policy rules.
    state_index: Dict[FrozenSet[str], int] = {}
    state_signatures: List[FrozenSet[str]] = []
    state_actions: Dict[FrozenSet[str], Set[str]] = {}
    state_parts: Dict[FrozenSet[str], Tuple[FrozenSet[str], FrozenSet[str]]] = {}

    for rule in result.policy:
        signature = frozenset(str(l).strip().lower() for l in rule.condition)
        if signature not in state_index:
            state_index[signature] = len(state_signatures)
            state_signatures.append(signature)
            state_actions[signature] = set()
            state_parts[signature] = split_state_literals(set(signature))
        state_actions[signature].add(rule.action)

    # Try to build grounded action table from domain/problem PDDL.
    action_table = {}
    goal_positive: FrozenSet[str] = frozenset()
    goal_negative: FrozenSet[str] = frozenset()
    init_fluents: Set[str] = set()

    if result.domain_pddl and result.problem_pddl:
        try:
            _, action_table, goal_positive, goal_negative, init_fluents = build_simulator(
                result.domain_pddl,
                result.problem_pddl,
            )
        except Exception:
            action_table = {}
            goal_positive = frozenset()
            goal_negative = frozenset()
            init_fluents = set()

    # Determine which policy node is the initial state (best match).
    initial_state_id = None
    if state_signatures and init_fluents:
        best_state = None
        best_score = float("-inf")
        init_positive = frozenset(x.lower() for x in init_fluents)
        for signature in state_signatures:
            cand_positive, cand_negative = state_parts[signature]
            score = _state_init_similarity_score(
                cand_positive,
                cand_negative,
                init_positive,
            )
            if score > best_score:
                best_score = score
                best_state = signature
        if best_state is not None:
            initial_state_id = state_index[best_state]
    elif state_signatures:
        # Fallback: if initial fluents are unavailable, pin the first policy state.
        initial_state_id = 0

    # Add policy-state nodes (names are placeholders; updated after edges).
    for signature in state_signatures:
        node_id = state_index[signature]
        positive, negative = state_parts[signature]
        all_conditions = sorted(signature)

        nodes.append(
            {
                "id": node_id,
                "name": "",  # filled in after distance computation
                "type": "state",
                "distance": -1,  # filled in after edges
                "is_sc": False,
                "num_conditions": len(signature),
                "num_positive": len(positive),
                "num_negative": len(negative),
                "conditions": all_conditions[:25],
                "actions": sorted(state_actions[signature]),
                "num_actions": len(state_actions[signature]),
                "is_initial": node_id == initial_state_id,
                "size": 8,
            }
        )

    # Terminal nodes — aligned with PRP naming.
    goal_node_id = len(nodes)
    nodes.append(
        {
            "id": goal_node_id,
            "name": "Goal",
            "type": "goal",
            "distance": 0,
            "is_sc": False,
            "num_conditions": len(goal_positive) + len(goal_negative),
            "num_positive": len(goal_positive),
            "num_negative": len(goal_negative),
            "conditions": [],
            "actions": [],
            "num_actions": 0,
            "is_initial": False,
            "size": 8,
        }
    )

    unmapped_node_id = goal_node_id + 1
    nodes.append(
        {
            "id": unmapped_node_id,
            "name": "undefined",
            "type": "unmapped",
            "distance": -1,
            "is_sc": False,
            "num_conditions": 0,
            "num_positive": 0,
            "num_negative": 0,
            "conditions": [],
            "actions": [],
            "num_actions": 0,
            "is_initial": False,
            "size": 8,
        }
    )

    # Build transitions directly from grounded outcomes.
    edge_map: Dict[Tuple[int, int, str], Dict] = {}
    total_outcomes = 0
    mapped_outcomes = 0

    for signature in state_signatures:
        source_id = state_index[signature]
        source_positive, source_negative = state_parts[signature]

        for action in sorted(state_actions[signature]):
            action_key = action.strip().lower()

            # Explicit goal action in policy.
            if action_key == "goal" or "goal" in action_key:
                key = (source_id, goal_node_id, action)
                edge = edge_map.get(key)
                if edge is None:
                    edge = {
                        "source": source_id,
                        "target": goal_node_id,
                        "action": action,
                        "type": "goal",
                        "outcomes": ["goal"],
                        "value": 2,
                    }
                    edge_map[key] = edge
                continue

            action_info = action_table.get(action_key)
            if action_info is None:
                # Unknown grounded action (e.g., missing PDDL context).
                key = (source_id, unmapped_node_id, action)
                edge = edge_map.get(key)
                if edge is None:
                    edge = {
                        "source": source_id,
                        "target": unmapped_node_id,
                        "action": action,
                        "type": "unmapped",
                        "outcomes": [],
                        "value": 1,
                    }
                    edge_map[key] = edge
                continue

            for outcome_idx, (adds, dels) in enumerate(action_info.outcomes):
                total_outcomes += 1
                simulated_positive, simulated_negative = _apply_outcome(
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
                        simulated_positive,
                        simulated_negative,
                    )
                    if score > best_score:
                        best_score = score
                        best_target = candidate_signature

                # Prefer policy-state target when matched.
                if best_target is not None and best_score >= 0:
                    target_id = state_index[best_target]
                    mapped_outcomes += 1
                    edge_type = "transition"
                else:
                    # If simulated state satisfies goal, target the goal node.
                    if goal_positive and goal_positive.issubset(simulated_positive) and goal_negative.isdisjoint(simulated_positive):
                        target_id = goal_node_id
                        edge_type = "goal"
                        mapped_outcomes += 1
                    else:
                        target_id = unmapped_node_id
                        edge_type = "unmapped"

                key = (source_id, target_id, action)
                edge = edge_map.get(key)
                if edge is None:
                    edge = {
                        "source": source_id,
                        "target": target_id,
                        "action": action,
                        "type": edge_type,
                        "outcomes": [outcome_idx],
                        "value": 1,
                    }
                    edge_map[key] = edge
                else:
                    edge["outcomes"].append(outcome_idx)
                    edge["value"] = min(edge["value"] + 0.5, 4)

    links = list(edge_map.values())

    # Drop optional terminal nodes if they are unused.
    linked_targets = {edge["target"] for edge in links}
    linked_sources = {edge["source"] for edge in links}
    used_nodes = linked_sources | linked_targets
    used_nodes.update(i for i in range(len(state_signatures)))

    if goal_node_id not in used_nodes:
        nodes = [node for node in nodes if node["id"] != goal_node_id]
        # Re-index unmapped node if goal node removed.
        if unmapped_node_id in used_nodes:
            for node in nodes:
                if node["id"] == unmapped_node_id:
                    node["id"] = goal_node_id
            for edge in links:
                if edge["source"] == unmapped_node_id:
                    edge["source"] = goal_node_id
                if edge["target"] == unmapped_node_id:
                    edge["target"] = goal_node_id
            unmapped_node_id = goal_node_id

    if unmapped_node_id not in {n["id"] for n in nodes if n["id"] in used_nodes}:
        nodes = [node for node in nodes if node["id"] != unmapped_node_id]

    # ── Compute goal distance (reverse BFS) and detect strong-cyclic nodes ──
    id_to_node = {n["id"]: n for n in nodes}

    # Build adjacency for BFS from goal and cycle detection.
    reverse_adj: Dict[int, List[int]] = {n["id"]: [] for n in nodes}
    forward_adj: Dict[int, List[int]] = {n["id"]: [] for n in nodes}
    for edge in links:
        src, tgt = edge["source"], edge["target"]
        if tgt in reverse_adj:
            reverse_adj[tgt].append(src)
        if src in forward_adj:
            forward_adj[src].append(tgt)

    # BFS from goal node backwards to assign distances.
    distances: Dict[int, int] = {goal_node_id: 0}
    bfs_queue: deque[int] = deque([goal_node_id])
    while bfs_queue:
        current = bfs_queue.popleft()
        for predecessor in reverse_adj.get(current, []):
            if predecessor not in distances:
                distances[predecessor] = distances[current] + 1
                bfs_queue.append(predecessor)

    # Detect strong-cyclic nodes: a node is SC if it can reach itself.
    sc_nodes: Set[int] = set()
    for nid in forward_adj:
        if nid == goal_node_id or nid == unmapped_node_id:
            continue
        visited: Set[int] = set()
        stack = list(forward_adj.get(nid, []))
        while stack:
            v = stack.pop()
            if v == nid:
                sc_nodes.add(nid)
                break
            if v in visited:
                continue
            visited.add(v)
            stack.extend(forward_adj.get(v, []))

    # Update node names and metadata using PRP conventions.
    for n in nodes:
        nid = n["id"]
        dist = distances.get(nid, -1)
        n["distance"] = dist
        n["is_sc"] = nid in sc_nodes
        if n["type"] == "state":
            n["name"] = _make_state_name(set(n["actions"]), dist)

    return {
        "nodes": nodes,
        "links": links,
        "stats": {
            "solved": result.is_solved,
            "strong_cyclic": result.is_strong_cyclic,
            "num_rules": len(result.policy),
            "num_fsaps": len(result.fsaps),
            "num_states": len(state_signatures),
            "num_transitions": len(links),
            "grounded_actions_found": len(action_table),
            "total_outcomes": total_outcomes,
            "mapped_outcomes": mapped_outcomes,
        },
    }


def create_force_graph_html(
    result: PR2Result,
    output_path: Path,
    domain_name: str = "Unknown",
    problem_name: str = "Unknown",
) -> None:
    """Create interactive HTML showing policy state-transition graph.

    Visual style aligned with PRP++ snapshot-viz by Christian Muise.
    """
    graph_data = policy_to_state_graph_data(result)

    solved_mark = "&#10003;" if graph_data["stats"]["solved"] else "&#10007;"
    sc_mark = "&#10003;" if graph_data["stats"]["strong_cyclic"] else "&#10007;"

    # Load HTML template and substitute values.
    _TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
    template_text = (_TEMPLATE_DIR / "policy_graph.html").read_text()
    html_content = Template(template_text).safe_substitute(
        problem_name=problem_name,
        domain_name=domain_name,
        solved_mark=solved_mark,
        sc_mark=sc_mark,
        num_states=graph_data["stats"]["num_states"],
        num_transitions=graph_data["stats"]["num_transitions"],
        mapped_outcomes=graph_data["stats"]["mapped_outcomes"],
        total_outcomes=graph_data["stats"]["total_outcomes"],
        color_goal=_COLOR_GOAL,
        color_init=_COLOR_INIT,
        color_sc=_COLOR_SC,
        color_undefined=_COLOR_UNDEFINED,
        color_default=_COLOR_DEFAULT,
        graph_data_json=json.dumps(graph_data),
    )

    output_path.write_text(html_content)
    print(f"Created PRP-style policy graph: {output_path}")

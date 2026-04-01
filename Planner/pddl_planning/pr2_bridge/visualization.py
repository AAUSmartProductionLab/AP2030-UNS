#!/usr/bin/env python3
"""Generate interactive policy state-transition visualization for PR2 policies."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from string import Template
from typing import Dict, List, Set, Tuple

from bt_synthesis.simulator import build_simulator
from .adapter import PR2Result
from .policy_graph import build_policy_state_graph

# PRP-aligned colour scheme
_COLOR_GOAL = "#e8c100"
_COLOR_INIT = "#067c00"
_COLOR_SC = "#025ef2"
_COLOR_UNDEFINED = "#930000"
_COLOR_DEFAULT = "#828282"


def _make_state_name(actions: Set[str], distance: int = -1) -> str:
    action_label = ", ".join(sorted(actions)) if actions else "noop"
    if distance == 0:
        return "Goal"
    if distance < 0:
        return action_label
    return f"{action_label} ({distance})"


def policy_to_state_graph_data(result: PR2Result) -> Dict:
    """Convert a PR2 policy into an explicit state-transition graph."""
    action_table = {}
    goal_positive = frozenset()
    goal_negative = frozenset()
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

    def get_action_outcomes(action: str):
        action_info = action_table.get(action.strip().lower())
        if action_info is None:
            return None
        return action_info.outcomes

    graph = build_policy_state_graph(
        result.policy,
        get_action_outcomes,
        goal_positive=set(goal_positive),
        goal_negative=set(goal_negative),
        init_fluents=set(init_fluents),
    )

    nodes: List[Dict] = []
    for signature in graph.state_signatures:
        node_id = graph.state_index[signature]
        positive, negative = graph.state_parts[signature]
        actions = sorted(graph.state_actions[signature])

        nodes.append(
            {
                "id": node_id,
                "name": "",
                "type": "state",
                "distance": -1,
                "is_sc": False,
                "num_conditions": len(signature),
                "num_positive": len(positive),
                "num_negative": len(negative),
                "conditions": sorted(signature)[:25],
                "actions": actions,
                "num_actions": len(actions),
                "is_initial": node_id == graph.initial_state_id,
                "size": 8,
            }
        )

    goal_node_id = graph.goal_node_id
    unmapped_node_id = graph.unmapped_node_id

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

    edge_map: Dict[Tuple[int, int, str], Dict] = {}
    total_outcomes = 0
    mapped_outcomes = 0

    for transition in graph.transitions:
        key = (transition.source, transition.target, transition.action)
        edge = edge_map.get(key)
        is_new_edge = edge is None
        if edge is None:
            edge = {
                "source": transition.source,
                "target": transition.target,
                "action": transition.action,
                "type": transition.transition_type,
                "outcomes": [],
                "value": 2 if transition.transition_type == "goal" and transition.outcome == "goal" else 1,
            }
            edge_map[key] = edge

        if isinstance(transition.outcome, int):
            edge["outcomes"].append(transition.outcome)
            total_outcomes += 1
            if transition.transition_type != "unmapped":
                mapped_outcomes += 1
            if not is_new_edge:
                edge["value"] = min(edge["value"] + 0.5, 4)
        elif transition.outcome == "goal" and "goal" not in edge["outcomes"]:
            edge["outcomes"].append("goal")

    links = list(edge_map.values())

    linked_targets = {edge["target"] for edge in links}
    linked_sources = {edge["source"] for edge in links}
    used_nodes = linked_sources | linked_targets
    used_nodes.update(i for i in range(len(graph.state_signatures)))

    if goal_node_id not in used_nodes:
        nodes = [node for node in nodes if node["id"] != goal_node_id]
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

    reverse_adj: Dict[int, List[int]] = {n["id"]: [] for n in nodes}
    forward_adj: Dict[int, List[int]] = {n["id"]: [] for n in nodes}
    for edge in links:
        source, target = edge["source"], edge["target"]
        if target in reverse_adj:
            reverse_adj[target].append(source)
        if source in forward_adj:
            forward_adj[source].append(target)

    distances: Dict[int, int] = dict(graph.distances)
    if goal_node_id not in distances and goal_node_id in reverse_adj:
        distances[goal_node_id] = 0
        bfs_queue: deque[int] = deque([goal_node_id])
        while bfs_queue:
            current = bfs_queue.popleft()
            for predecessor in reverse_adj.get(current, []):
                if predecessor not in distances:
                    distances[predecessor] = distances[current] + 1
                    bfs_queue.append(predecessor)

    sc_nodes: Set[int] = set()
    for node_id in forward_adj:
        if node_id == goal_node_id or node_id == unmapped_node_id:
            continue
        visited: Set[int] = set()
        stack = list(forward_adj.get(node_id, []))
        while stack:
            current = stack.pop()
            if current == node_id:
                sc_nodes.add(node_id)
                break
            if current in visited:
                continue
            visited.add(current)
            stack.extend(forward_adj.get(current, []))

    for node in nodes:
        node_id = node["id"]
        node["distance"] = distances.get(node_id, -1)
        node["is_sc"] = node_id in sc_nodes
        if node["type"] == "state":
            node["name"] = _make_state_name(set(node["actions"]), node["distance"])

    return {
        "nodes": nodes,
        "links": links,
        "stats": {
            "solved": result.is_solved,
            "strong_cyclic": result.is_strong_cyclic,
            "num_rules": len(result.policy),
            "num_fsaps": len(result.fsaps),
            "num_states": len(graph.state_signatures),
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
    """Create interactive HTML showing policy state-transition graph."""
    graph_data = policy_to_state_graph_data(result)

    solved_mark = "&#10003;" if graph_data["stats"]["solved"] else "&#10007;"
    sc_mark = "&#10003;" if graph_data["stats"]["strong_cyclic"] else "&#10007;"

    template_dir = Path(__file__).resolve().parents[2] / "templates"
    template_text = (template_dir / "policy_graph.html").read_text()
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

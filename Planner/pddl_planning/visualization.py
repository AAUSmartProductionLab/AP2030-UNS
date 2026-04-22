#!/usr/bin/env python3
"""Generate interactive policy state-transition visualization for policy plans."""

from __future__ import annotations

import json
from html import escape
from collections import deque
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from ..bt_synthesis.policy_graph import build_policy_state_graph
except ImportError:
    from bt_synthesis.policy_graph import build_policy_state_graph

# PRP-aligned colour scheme
_COLOR_GOAL = "#e8c100"
_COLOR_INIT = "#067c00"
_COLOR_SC = "#025ef2"
_COLOR_UNDEFINED = "#930000"
_COLOR_DEFAULT = "#828282"


def _node_color(node: Dict) -> str:
    if node.get("type") == "goal" or node.get("distance") == 0:
        return _COLOR_GOAL
    if node.get("is_initial"):
        return _COLOR_INIT
    if node.get("is_sc"):
        return _COLOR_SC
    if node.get("type") == "unmapped":
        return _COLOR_UNDEFINED
    return _COLOR_DEFAULT


def _build_static_svg_markup(graph_data: Dict, width: int = 1200, height: int = 800) -> str:
    """Build a static SVG snapshot so nodes are visible even if JS is blocked."""
    nodes = [dict(n) for n in graph_data.get("nodes", [])]
    links = list(graph_data.get("links", []))
    if not nodes:
        return ""

    max_dist = max(1, *[(n.get("distance", -1) if n.get("distance", -1) >= 0 else 0) for n in nodes])
    levels: Dict[int, List[Dict]] = {}
    for node in nodes:
        level = node.get("distance", -1)
        level = int(level) if isinstance(level, int) and level >= 0 else (max_dist + 1)
        levels.setdefault(level, []).append(node)

    v_pad = 70
    h_pad = 80
    by_id: Dict[int, Dict] = {}
    for level in sorted(levels.keys()):
        arr = levels[level]
        y = v_pad + ((max_dist + 1 - level) / (max_dist + 1)) * (height - 2 * v_pad)
        for idx, node in enumerate(arr):
            x = h_pad + ((idx + 1) / (len(arr) + 1)) * (width - 2 * h_pad)
            node["_x"] = x
            node["_y"] = y
            by_id[int(node["id"])] = node

    parts: List[str] = []
    parts.append('<g id="static-fallback-layer">')
    for link in links:
        source = by_id.get(int(link.get("source", -1)))
        target = by_id.get(int(link.get("target", -1)))
        if source is None or target is None:
            continue
        parts.append(
            '<line x1="{:.2f}" y1="{:.2f}" x2="{:.2f}" y2="{:.2f}" stroke="#222" stroke-opacity="0.65" stroke-width="1.5" />'.format(
                source["_x"],
                source["_y"],
                target["_x"],
                target["_y"],
            )
        )

    for node in nodes:
        x = node["_x"]
        y = node["_y"]
        title = escape(str(node.get("name", f"node-{node.get('id')}") or f"node-{node.get('id')}"))
        fill = _node_color(node)
        parts.append('<g class="static-node">')
        parts.append(
            '<circle cx="{:.2f}" cy="{:.2f}" r="8" fill="{}" stroke="#000" stroke-width="1.2" />'.format(
                x,
                y,
                fill,
            )
        )
        parts.append('<title>{}</title>'.format(title))
        parts.append(
            '<text x="{:.2f}" y="{:.2f}" font-size="10" fill="#333">{}</text>'.format(
                x + 12,
                y + 4,
                title,
            )
        )
        parts.append("</g>")
    parts.append("</g>")
    return "\n".join(parts)


def _make_state_name(actions: Set[str], distance: int = -1) -> str:
    action_label = ", ".join(sorted(actions)) if actions else "noop"
    if distance == 0:
        return "Goal"
    if distance < 0:
        return action_label
    return f"{action_label} ({distance})"


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _extract_pddl_texts(
    result: Any,
    *,
    domain_pddl: Optional[str] = None,
    problem_pddl: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    domain_text = domain_pddl
    problem_text = problem_pddl

    if not domain_text:
        domain_text = _safe_getattr(result, "domain_pddl")
    if not problem_text:
        problem_text = _safe_getattr(result, "problem_pddl")

    if domain_text and problem_text:
        return str(domain_text), str(problem_text)

    metadata = _safe_getattr(result, "metadata", {})
    if not isinstance(metadata, dict):
        return (
            str(domain_text) if domain_text else None,
            str(problem_text) if problem_text else None,
        )

    problem_obj = metadata.get("problem")
    if problem_obj is None:
        return (
            str(domain_text) if domain_text else None,
            str(problem_text) if problem_text else None,
        )

    try:
        from unified_planning.io import PDDLWriter

        writer = PDDLWriter(problem_obj)
        if not domain_text:
            domain_text = writer.get_domain()
        if not problem_text:
            problem_text = writer.get_problem()
    except Exception:
        pass

    return (
        str(domain_text) if domain_text else None,
        str(problem_text) if problem_text else None,
    )


def _build_action_model_from_pddl(
    domain_text: str,
    problem_text: str,
) -> Tuple[Dict[str, Any], Set[str], Set[str], Set[str]]:
    """Build grounded action/goal/init sets without requiring py_trees."""
    try:
        try:
            from ..bt_synthesis.pddl_grounding import And, Primitive, ground_pddl
            from ..bt_synthesis.causal import (
                GroundedAction,
                _fondparser_predicate_to_fluent,
                _fondparser_op_to_pr2_name,
                _extract_preconditions,
                _extract_outcomes,
                _extract_goal,
            )
        except ImportError:
            try:
                from bt_synthesis.pddl_grounding import And, Primitive, ground_pddl
                from bt_synthesis.causal import (
                    GroundedAction,
                    _fondparser_predicate_to_fluent,
                    _fondparser_op_to_pr2_name,
                    _extract_preconditions,
                    _extract_outcomes,
                    _extract_goal,
                )
            except ImportError:
                from Planner.bt_synthesis.pddl_grounding import And, Primitive, ground_pddl
                from Planner.bt_synthesis.causal import (
                    GroundedAction,
                    _fondparser_predicate_to_fluent,
                    _fondparser_op_to_pr2_name,
                    _extract_preconditions,
                    _extract_outcomes,
                    _extract_goal,
                )

        problem = ground_pddl(domain_text, problem_text)

        def _lower_set(values):
            return frozenset(v.lower() for v in values)

        init_fluents: Set[str] = set()
        if isinstance(problem.init, And):
            for arg in problem.init.args:
                if isinstance(arg, Primitive):
                    init_fluents.add(
                        _fondparser_predicate_to_fluent(arg.predicate).lower()
                    )
        elif isinstance(problem.init, Primitive):
            init_fluents.add(
                _fondparser_predicate_to_fluent(problem.init.predicate).lower()
            )

        goal_pos_raw, goal_neg_raw = _extract_goal(problem.goal)
        goal_positive = set(_lower_set(goal_pos_raw))
        goal_negative = set(_lower_set(goal_neg_raw))

        action_table: Dict[str, Any] = {}
        for op in problem.operators:
            pr2_name = _fondparser_op_to_pr2_name(op).lower()
            pos_pre, neg_pre = _extract_preconditions(op.precondition)
            outcomes = _extract_outcomes(op)
            action_table[pr2_name] = GroundedAction(
                name=pr2_name,
                preconditions=_lower_set(pos_pre),
                neg_preconditions=_lower_set(neg_pre),
                outcomes=[(_lower_set(a), _lower_set(d)) for a, d in outcomes],
            )

        return action_table, goal_positive, goal_negative, init_fluents
    except Exception:
        return {}, set(), set(), set()


def policy_to_state_graph_data(
    result: Any,
    *,
    domain_pddl: Optional[str] = None,
    problem_pddl: Optional[str] = None,
) -> Dict:
    """Convert a policy into an explicit state-transition graph."""
    action_table = {}
    goal_positive = frozenset()
    goal_negative = frozenset()
    init_fluents: Set[str] = set()

    domain_text, problem_text = _extract_pddl_texts(
        result,
        domain_pddl=domain_pddl,
        problem_pddl=problem_pddl,
    )

    if domain_text and problem_text:
        action_table, goal_positive, goal_negative, init_fluents = _build_action_model_from_pddl(
            domain_text,
            problem_text,
        )

    # Some goals include static fluents (for example operational(...)) that are
    # always true in the full world state but are intentionally absent from the
    # policy's partial-state rule signatures. If we keep them in the goal check,
    # edges that actually reach goal are misclassified as unmapped.
    deletable_fluents: Set[str] = set()
    for action in action_table.values():
        for _adds, dels in action.outcomes:
            deletable_fluents.update(dels)
    static_always_true = {
        f.lower()
        for f in init_fluents
        if f.lower() not in deletable_fluents
    }
    effective_goal_positive = {
        f.lower() for f in goal_positive
        if f.lower() not in static_always_true
    }
    effective_goal_negative = {f.lower() for f in goal_negative}

    def get_action_outcomes(action: str):
        raw = action.strip().lower()
        candidates = [raw]

        # Policy actions are often rendered as "name(arg1, arg2)" while the
        # simulator lookup table uses "name arg1 arg2".
        if "(" in raw and raw.endswith(")"):
            name, args_part = raw.split("(", 1)
            args_text = args_part[:-1].strip()
            if args_text:
                args = [a.strip() for a in args_text.split(",") if a.strip()]
                candidates.append(" ".join([name.strip(), *args]))
            else:
                candidates.append(name.strip())

        # Also try converting "name arg1 arg2" -> "name(arg1, arg2)".
        if " " in raw and "(" not in raw:
            parts = [p for p in raw.split(" ") if p]
            if parts:
                if len(parts) == 1:
                    candidates.append(parts[0] + "()")
                else:
                    candidates.append(parts[0] + "(" + ", ".join(parts[1:]) + ")")

        for key in candidates:
            action_info = action_table.get(key)
            if action_info is not None:
                return action_info.outcomes
        return None

    graph = build_policy_state_graph(
        result.policy,
        get_action_outcomes,
        goal_positive=effective_goal_positive,
        goal_negative=effective_goal_negative,
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

    # Keep all state nodes plus special sink nodes, and guarantee that every
    # link endpoint exists as a node so the D3 force-link setup cannot fail.
    node_ids = {n["id"] for n in nodes}
    missing_endpoints = ({e["source"] for e in links} | {e["target"] for e in links}) - node_ids
    for missing_id in sorted(missing_endpoints):
        nodes.append(
            {
                "id": missing_id,
                "name": f"node-{missing_id}",
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
    result: Any,
    output_path: Path,
    domain_name: str = "Unknown",
    problem_name: str = "Unknown",
) -> None:
    """Create interactive HTML showing policy state-transition graph."""
    domain_text = None
    problem_text = None
    artifacts_dir = output_path.parent

    domain_path = artifacts_dir / "domain.pddl"
    if domain_path.exists():
        try:
            domain_text = domain_path.read_text()
        except Exception:
            domain_text = None

    problem_path = artifacts_dir / "problem.pddl"
    if problem_path.exists():
        try:
            problem_text = problem_path.read_text()
        except Exception:
            problem_text = None

    graph_data = policy_to_state_graph_data(
        result,
        domain_pddl=domain_text,
        problem_pddl=problem_text,
    )

    solved_mark = "&#10003;" if graph_data["stats"]["solved"] else "&#10007;"
    sc_mark = "&#10003;" if graph_data["stats"]["strong_cyclic"] else "&#10007;"

    template_dir = Path(__file__).resolve().parents[1] / "templates"
    template_text = (template_dir / "policy_graph.html").read_text()
    static_svg_markup = _build_static_svg_markup(graph_data)
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
        static_svg_markup=static_svg_markup,
        graph_data_json=json.dumps(graph_data),
    )

    output_path.write_text(html_content)
    print(f"Created PRP-style policy graph: {output_path}")

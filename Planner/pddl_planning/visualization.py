#!/usr/bin/env python3
"""Generate interactive policy state-transition visualization for policy plans."""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from string import Template
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

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


def _tarjan_sccs(
    adjacency: Dict[int, List[int]],
    *,
    skip: Optional[Set[int]] = None,
) -> List[List[int]]:
    """Compute strongly-connected components iteratively (Tarjan's algorithm).

    ``skip`` nodes are removed from consideration entirely; edges to/from
    them are ignored. Returns a list of components (each a list of node ids).
    """
    skip = skip or set()
    index_of: Dict[int, int] = {}
    lowlink: Dict[int, int] = {}
    on_stack: Set[int] = set()
    stack: List[int] = []
    result: List[List[int]] = []
    next_index = 0

    def neighbours(v: int) -> List[int]:
        return [w for w in adjacency.get(v, []) if w not in skip]

    for start in adjacency:
        if start in skip or start in index_of:
            continue
        # Iterative DFS with an explicit work stack of (node, neighbour_iter).
        work: List[Tuple[int, List[int], int]] = []
        index_of[start] = next_index
        lowlink[start] = next_index
        next_index += 1
        stack.append(start)
        on_stack.add(start)
        work.append((start, neighbours(start), 0))

        while work:
            v, succs, i = work[-1]
            if i < len(succs):
                w = succs[i]
                work[-1] = (v, succs, i + 1)
                if w not in index_of:
                    index_of[w] = next_index
                    lowlink[w] = next_index
                    next_index += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, neighbours(w), 0))
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index_of[w])
            else:
                if lowlink[v] == index_of[v]:
                    component: List[int] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.append(w)
                        if w == v:
                            break
                    result.append(component)
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])
    return result


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
            '<text x="{:.2f}" y="{:.2f}" font-size="16" fill="#333">{}</text>'.format(
                x + 12,
                y + 4,
                title,
            )
        )
        parts.append("</g>")
    parts.append("</g>")
    return "\n".join(parts)


def _parse_action_name_and_args(action: str) -> Tuple[str, List[str]]:
    raw = str(action or "").strip()
    if not raw:
        return "", []

    if "(" in raw and raw.endswith(")"):
        name, args_part = raw.split("(", 1)
        args_text = args_part[:-1].strip()
        args = [a.strip() for a in args_text.split(",") if a.strip()] if args_text else []
        return name.strip(), args

    parts = [p for p in raw.split() if p]
    if not parts:
        return "", []
    return parts[0], parts[1:]


def _clean_action_name(name: str) -> str:
    base = re.sub(r"_\d+$", "", str(name or "").strip().lower())
    return base.replace("_", " ").strip()


def _is_product_like_token(token: str) -> bool:
    t = str(token or "").strip().lower()
    return (
        t.startswith("mim")
        or t.startswith("product")
        or t.startswith("order")
        or t.startswith("step")
    )


def _literal_args(literal: str, predicate: str) -> Optional[List[str]]:
    prefix = f"{predicate}("
    lit = str(literal or "").strip().lower()
    if not lit.startswith(prefix) or not lit.endswith(")"):
        return None
    inner = lit[len(prefix) : -1].strip()
    if not inner:
        return []
    return [x.strip() for x in inner.split(",") if x.strip()]


def _candidate_action_keys(action: str) -> List[str]:
    raw = str(action or "").strip().lower()
    if not raw:
        return []

    candidates: List[str] = [raw]

    # Policy actions are often rendered as "name(arg1, arg2)" while action
    # lookup tables may use "name arg1 arg2".
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

    # Preserve order but drop duplicates.
    seen: Set[str] = set()
    unique: List[str] = []
    for c in candidates:
        if c not in seen:
            unique.append(c)
            seen.add(c)
    return unique


def _resolve_action_info(action: str, action_table: Dict[str, Any]) -> Optional[Any]:
    for key in _candidate_action_keys(action):
        action_info = action_table.get(key)
        if action_info is not None:
            return action_info
    return None


def _extract_asset_hint_from_action_model(action_info: Any, action_args: List[str]) -> Optional[str]:
    if action_info is None:
        return None

    product_args = {a.lower() for a in action_args if _is_product_like_token(a)}
    scores: Dict[str, int] = {}

    def _bump(token: Optional[str], weight: int) -> None:
        t = str(token or "").strip().lower()
        if not t or _is_product_like_token(t):
            return
        scores[t] = scores.get(t, 0) + weight

    def _scan_literal(literal: str, *, from_outcome: bool = False) -> None:
        operational = _literal_args(literal, "operational")
        if operational and len(operational) == 1:
            _bump(operational[0], 7)

        occupied = _literal_args(literal, "occupied")
        if occupied and len(occupied) == 2 and (not product_args or occupied[1] in product_args):
            _bump(occupied[0], 5)

        # Outcome literals frequently include transport-side state changes
        # (e.g. on/productat/resourceat deltas) that should not override the
        # executing asset. Use them only as weak tie-breakers from
        # preconditions, not as primary evidence.
        if from_outcome:
            return

        on_args = _literal_args(literal, "on")
        if on_args and len(on_args) == 2 and (not product_args or on_args[0] in product_args):
            _bump(on_args[1], 4)

        resource_at = _literal_args(literal, "resourceat")
        if resource_at and len(resource_at) >= 1:
            _bump(resource_at[0], 4)

        free_args = _literal_args(literal, "free")
        if free_args and len(free_args) == 1:
            _bump(free_args[0], 2)

    for lit in getattr(action_info, "preconditions", []) or []:
        _scan_literal(lit, from_outcome=False)

    for adds, dels in getattr(action_info, "outcomes", []) or []:
        for lit in adds:
            _scan_literal(lit, from_outcome=True)
        for lit in dels:
            _scan_literal(lit, from_outcome=True)

    if not scores:
        return None

    best_token, _ = max(sorted(scores.items()), key=lambda item: item[1])
    return best_token


def _infer_resource_hint(
    positive_literals: FrozenSet[str],
    action_args: List[str],
) -> Optional[str]:
    products = {a.lower() for a in action_args if _is_product_like_token(a)}

    for lit in positive_literals:
        args = _literal_args(lit, "on")
        if args and len(args) == 2 and (not products or args[0] in products):
            return args[1]

    for lit in positive_literals:
        args = _literal_args(lit, "occupied")
        if args and len(args) == 2 and (not products or args[1] in products):
            return args[0]

    for lit in positive_literals:
        args = _literal_args(lit, "resourceat")
        if args and len(args) >= 1:
            return args[0]

    return None


def _make_action_display_name(
    action: str,
    positive_literals: FrozenSet[str],
    *,
    action_model_asset_hint: Optional[str] = None,
) -> str:
    raw_name, args = _parse_action_name_and_args(action)
    clean_name = _clean_action_name(raw_name)
    if not clean_name:
        return "noop"

    # If we can infer the executor asset from grounded action semantics,
    # prefer that over positional parameters (which are often transports).
    if action_model_asset_hint:
        return f"{clean_name} {action_model_asset_hint}"

    non_product_args = [a for a in args if not _is_product_like_token(a)]
    if non_product_args:
        return f"{clean_name} {non_product_args[0]}"

    resource_hint = _infer_resource_hint(positive_literals, args)
    if resource_hint:
        return f"{clean_name} {resource_hint}"

    return clean_name


def _make_state_name(
    actions: Set[str],
    positive_literals: FrozenSet[str],
    *,
    action_asset_hints: Optional[Dict[str, Optional[str]]] = None,
) -> str:
    if not actions:
        return "noop"
    labels = [
        _make_action_display_name(
            a,
            positive_literals,
            action_model_asset_hint=(action_asset_hints or {}).get(a),
        )
        for a in sorted(actions)
    ]
    return ", ".join(labels)


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

    action_asset_hint_cache: Dict[str, Optional[str]] = {}

    def _action_asset_hint(action: str) -> Optional[str]:
        if action not in action_asset_hint_cache:
            _name, args = _parse_action_name_and_args(action)
            action_info = _resolve_action_info(action, action_table)
            action_asset_hint_cache[action] = _extract_asset_hint_from_action_model(action_info, args)
        return action_asset_hint_cache[action]

    def get_action_outcomes(action: str):
        action_info = _resolve_action_info(action, action_table)
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
                "name": _make_state_name(
                    set(actions),
                    positive,
                    action_asset_hints={a: _action_asset_hint(a) for a in actions},
                ),
                "type": "state",
                "distance": -1,
                "is_sc": False,
                "num_conditions": len(signature),
                "num_positive": len(positive),
                "num_negative": len(negative),
                "conditions": sorted(signature)[:25],
                "actions": actions,
                "display_actions": [
                    _make_action_display_name(
                        a,
                        positive,
                        action_model_asset_hint=_action_asset_hint(a),
                    )
                    for a in actions
                ],
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

    # graph.distances is rank-based (with optional BFS refinement applied
    # inside build_policy_state_graph), and always contains every state plus
    # goal_node_id. No further BFS pass is required here.
    distances: Dict[int, int] = dict(graph.distances)

    # Strongly-connected components (Tarjan): a node is "on a cycle" iff it
    # belongs to an SCC of size > 1, or to a singleton SCC with a self-loop.
    # This is order-independent and bias-free, unlike the prior
    # any-path-back-to-self traversal. We exclude the goal/unmapped sinks
    # since cycles through them are not meaningful recovery loops.
    sc_nodes: Set[int] = set()
    sccs = _tarjan_sccs(
        forward_adj,
        skip={goal_node_id, unmapped_node_id},
    )
    for component in sccs:
        if len(component) > 1:
            sc_nodes.update(component)
        else:
            (only,) = component
            if only in forward_adj.get(only, []):
                sc_nodes.add(only)

    for node in nodes:
        node_id = node["id"]
        node["distance"] = distances.get(node_id, -1)
        node["is_sc"] = node_id in sc_nodes

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

"""Top-level planning facade.

This module is the first step toward a single public solver API built around
``unified_planning`` while keeping PR2 available for policy-style solving.

Current behavior:
- unified-planning ``Problem`` objects are solved through UP oneshot planners.
- unified-planning ``Problem`` objects can also be routed directly into PR2 with ``backend='pr2'`` for the supported deterministic subset.
- The direct PR2 path also supports native oneof action outcomes on the vendored unified-planning fork.
- Full UP-side support for richer FOND constructs beyond action oneof outcomes is still incomplete.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Sequence


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_VENDORED_UP_ROOT = _REPO_ROOT / "unified-planning"
if _VENDORED_UP_ROOT.exists():
    vendored_up_root = str(_VENDORED_UP_ROOT)
    if vendored_up_root not in sys.path:
        sys.path.insert(0, vendored_up_root)

from .solve_result import SolveResult
from ..pr2_bridge.adapter import PR2Solver


BackendName = Literal["auto", "pr2", "up"]


def solve(
    problem: Any,
    *,
    backend: BackendName = "auto",
    planner_name: Optional[str] = None,
    timeout: Optional[float] = None,
    params: Optional[Dict[str, Any]] = None,
    extra_args: Optional[Sequence[str]] = None,
    disable_object_sampling: bool = True,
    keep_files: bool = False,
) -> SolveResult:
    """Solve a planning problem through a single entrypoint.

    Parameters
    ----------
    problem
        A unified-planning ``Problem`` instance.
    backend
        ``auto`` routes deterministic problems to unified-planning and
        non-deterministic oneof problems to PR2.
    planner_name
        Optional explicit unified-planning engine name.
    timeout
        Per-solve timeout in seconds.
    params
        Planner-specific UP parameters.
    extra_args
        Extra PR2 command-line arguments.
    """
    if _looks_like_unified_planning_problem(problem):
        return _solve_unified_planning_problem(
            problem,
            backend=backend,
            planner_name=planner_name,
            timeout=timeout,
            params=params,
            extra_args=extra_args,
            disable_object_sampling=disable_object_sampling,
            keep_files=keep_files,
        )

    raise TypeError(
        "Unsupported solve() input. Pass a unified-planning Problem."
    )


def solve_from_files(
    domain_file: str | Path,
    problem_file: str | Path,
    *,
    backend: BackendName = "auto",
    planner_name: Optional[str] = None,
    timeout: Optional[float] = None,
    params: Optional[Dict[str, Any]] = None,
    extra_args: Optional[Sequence[str]] = None,
    disable_object_sampling: bool = True,
    keep_files: bool = False,
) -> SolveResult:
    """Solve from PDDL files.

    ``auto`` parses files with unified-planning and applies the same routing
    policy as ``solve()``.
    """
    if backend in ("auto", "up"):
        up_problem = _read_problem_with_unified_planning(domain_file, problem_file)
        return _solve_unified_planning_problem(
            up_problem,
            backend=backend,
            planner_name=planner_name,
            timeout=timeout,
            params=params,
            extra_args=extra_args,
            disable_object_sampling=disable_object_sampling,
            keep_files=keep_files,
        )

    if backend != "pr2":
        raise ValueError(f"Unsupported backend: {backend}")

    solver = PR2Solver(
        disable_object_sampling=disable_object_sampling,
        extra_args=list(extra_args or []),
        timeout=_normalize_timeout(timeout),
        keep_files=keep_files,
    )
    result = solver.solve_from_files(
        str(domain_file),
        str(problem_file),
        timeout=_normalize_timeout(timeout),
        extra_args=list(extra_args or []),
    )
    return SolveResult.from_pr2(result)


def _solve_unified_planning_problem(
    problem: Any,
    *,
    backend: BackendName,
    planner_name: Optional[str],
    timeout: Optional[float],
    params: Optional[Dict[str, Any]],
    extra_args: Optional[Sequence[str]],
    disable_object_sampling: bool,
    keep_files: bool,
) -> SolveResult:
    if backend == "auto" and _should_route_auto_to_pr2(problem):
        solver = PR2Solver(
            disable_object_sampling=disable_object_sampling,
            extra_args=list(extra_args or []),
            timeout=_normalize_timeout(timeout),
            keep_files=keep_files,
        )
        result = solver.solve_unified_planning_problem(
            problem,
            timeout=_normalize_timeout(timeout),
            extra_args=list(extra_args or []),
        )
        return SolveResult.from_pr2(result, backend_name="pr2-direct")

    if backend == "pr2":
        solver = PR2Solver(
            disable_object_sampling=disable_object_sampling,
            extra_args=list(extra_args or []),
            timeout=_normalize_timeout(timeout),
            keep_files=keep_files,
        )
        result = solver.solve_unified_planning_problem(
            problem,
            timeout=_normalize_timeout(timeout),
            extra_args=list(extra_args or []),
        )
        return SolveResult.from_pr2(result, backend_name="pr2-direct")
    if backend not in ("auto", "up"):
        raise ValueError(f"Unsupported backend: {backend}")

    up = _import_unified_planning()
    planner_kwargs: Dict[str, Any] = {"problem_kind": problem.kind}
    if planner_name is not None:
        planner_kwargs["name"] = planner_name
    if params:
        planner_kwargs["params"] = params

    solve_kwargs: Dict[str, Any] = {}
    if timeout is not None:
        solve_kwargs["timeout"] = timeout

    with up.shortcuts.OneshotPlanner(**planner_kwargs) as planner:
        result = planner.solve(problem, **solve_kwargs)
        backend_name = getattr(planner, "name", None) or planner_name or "unified-planning"

    return SolveResult.from_up(result, backend_name=backend_name)


def _read_problem_with_unified_planning(domain_file: str | Path, problem_file: str | Path) -> Any:
    up = _import_unified_planning()
    reader = up.io.PDDLReader()
    return reader.parse_problem(str(domain_file), str(problem_file))


def _looks_like_unified_planning_problem(problem: Any) -> bool:
    problem_type = type(problem)
    module_name = getattr(problem_type, "__module__", "")
    return module_name.startswith("unified_planning.") and hasattr(problem, "kind")


def _import_unified_planning():
    try:
        import unified_planning as up
    except ImportError as exc:
        raise RuntimeError(
            "unified_planning is required for the UP backend. Install it with "
            "'pip install unified-planning'."
        ) from exc
    return up


def _should_route_auto_to_pr2(problem: Any) -> bool:
    """Return True when backend='auto' should use PR2 for policy semantics."""
    kind = getattr(problem, "kind", None)
    has_nondet_method = getattr(kind, "has_non_deterministic_effects", None)
    if callable(has_nondet_method):
        try:
            if bool(has_nondet_method()):
                return True
        except Exception:
            pass

    for action in getattr(problem, "actions", []):
        if len(getattr(action, "oneof_effects", [])) > 0:
            return True
    return False


def _normalize_timeout(timeout: Optional[float]) -> Optional[int]:
    if timeout is None:
        return None
    return int(timeout)
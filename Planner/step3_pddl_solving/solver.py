"""Top-level planning facade.

This module is the first step toward a single public solver API built around
``unified_planning`` while keeping PR2 available for policy-style solving.

Current behavior:
- unified-planning ``Problem`` objects are solved through UP oneshot planners.
- ``backend='pr2'`` uses the UP-registered ``pr2`` engine explicitly.
- ``backend='auto'`` relies on UP factory selection based on ``problem.kind``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Sequence


_PLANNER_ROOT = Path(__file__).resolve().parents[1]
_VENDORED_UP_ROOT = _PLANNER_ROOT / "third_party" / "unified-planning"


def _resolve_vendored_up_root() -> Path:
    if _VENDORED_UP_ROOT.is_dir():
        return _VENDORED_UP_ROOT
    raise RuntimeError(
        "Missing vendored unified-planning fork at "
        f"{_VENDORED_UP_ROOT}."
    )


_VENDORED_UP_ROOT = _resolve_vendored_up_root()

from .solve_result import SolveResult


BackendName = Literal["auto", "pr2", "up"]


def solve(
    problem: Any,
    *,
    backend: BackendName = "auto",
    planner_name: Optional[str] = None,
    timeout: Optional[float] = None,
    params: Optional[Dict[str, Any]] = None,
    extra_args: Optional[Sequence[str]] = None,
    disable_object_sampling: bool = False,
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
    disable_object_sampling: bool = False,
    keep_files: bool = False,
) -> SolveResult:
    """Solve from PDDL files.

    ``auto`` parses files with unified-planning and applies the same routing
    policy as ``solve()``.
    """
    if backend not in ("auto", "up", "pr2"):
        raise ValueError(f"Unsupported backend: {backend}")

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
    if backend not in ("auto", "up", "pr2"):
        raise ValueError(f"Unsupported backend: {backend}")

    _import_unified_planning()
    from unified_planning.shortcuts import OneshotPlanner

    planner_kwargs: Dict[str, Any] = {"problem_kind": problem.kind}

    if backend == "pr2":
        planner_kwargs["name"] = "pr2"
    elif backend == "up" and planner_name is None:
        planner_kwargs["name"] = "aries"
    elif planner_name is not None:
        planner_kwargs["name"] = planner_name

    planner_params: Dict[str, Any] = dict(params or {})
    if backend == "pr2":
        planner_params.setdefault("disable_object_sampling", disable_object_sampling)
        planner_params.setdefault("extra_args", list(extra_args or []))
    if planner_params:
        planner_kwargs["params"] = planner_params

    solve_kwargs: Dict[str, Any] = {}
    if timeout is not None:
        solve_kwargs["timeout"] = timeout

    with OneshotPlanner(**planner_kwargs) as planner:
        result = planner.solve(problem, **solve_kwargs)
        backend_name = getattr(planner, "name", None) or planner_name or "unified-planning"

    return SolveResult.from_up(result, backend_name=backend_name, problem=problem)


def _read_problem_with_unified_planning(domain_file: str | Path, problem_file: str | Path) -> Any:
    _import_unified_planning()
    from unified_planning.io import PDDLReader

    # Prefer the native UP parser first to avoid noisy AI-converter fallback
    # warnings on some nondeterministic oneof domains. If native parsing fails
    # (e.g., stricter syntax handling in specific domains), retry with the
    # reader default strategy.
    try:
        reader = PDDLReader(force_up_pddl_reader=True)
        return reader.parse_problem(str(domain_file), str(problem_file))
    except TypeError:
        # Older/newer UP variants may not expose force_up_pddl_reader.
        reader = PDDLReader()
        return reader.parse_problem(str(domain_file), str(problem_file))
    except Exception:
        reader = PDDLReader()
        return reader.parse_problem(str(domain_file), str(problem_file))


def _looks_like_unified_planning_problem(problem: Any) -> bool:
    problem_type = type(problem)
    module_name = getattr(problem_type, "__module__", "")
    return module_name.startswith("unified_planning.") and hasattr(problem, "kind")


def _import_unified_planning():
    vendored_up_root = str(_VENDORED_UP_ROOT)
    if not sys.path or sys.path[0] != vendored_up_root:
        if vendored_up_root in sys.path:
            sys.path.remove(vendored_up_root)
        sys.path.insert(0, vendored_up_root)

    try:
        import unified_planning as up
    except ImportError as exc:
        raise RuntimeError(
            "Could not import vendored unified_planning from "
            f"{_VENDORED_UP_ROOT}. Ensure the fork is present and complete."
        ) from exc

    module_file = Path(getattr(up, "__file__", "")).resolve()
    if not _is_relative_to(module_file, _VENDORED_UP_ROOT.resolve()):
        raise RuntimeError(
            "Loaded unified_planning from an unexpected location: "
            f"{module_file}. Expected a module under {_VENDORED_UP_ROOT}."
        )

    return up


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        return Path(os.path.commonpath([str(path), str(parent)])) == parent
    except Exception:
        return False
"""PR2 adapter for file-based and Unified Planning-based solving."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .up_lowering import lower_problem as lower_up_problem
from .up_lowering import task_to_sas as up_task_to_sas


# ---------------------------------------------------------------------------
# Locate PR2 root (the pr2/ subdirectory next to this file)
# ---------------------------------------------------------------------------
_PR2_ROOT = Path(__file__).resolve().parent.parent.parent / "pr2"
_PR2_SCRIPT = _PR2_ROOT / "pr2"
_FD_SCRIPT = _PR2_ROOT / "fast-downward.py"


# ---------------------------------------------------------------------------
# Result & Policy data-classes
# ---------------------------------------------------------------------------


@dataclass
class PolicyRule:
    """A single conditional policy rule: if *condition* holds, execute *action*."""
    condition: frozenset  # set of string fluent literals
    action: str           # full grounded action, e.g. "move-car n12 n0"
    action_name: str = ""  # just the operator name, e.g. "move-car"
    action_args: tuple = ()  # just the parameters, e.g. ("n12", "n0")


@dataclass
class FSAP:
    """A Forbidden State-Action Pair: if *condition* holds, forbid *action*."""
    condition: frozenset
    action: str           # full grounded action, e.g. "move-car n2 n1"
    action_name: str = ""  # just the operator name, e.g. "move-car"
    action_args: tuple = ()  # just the parameters, e.g. ("n2", "n1")


@dataclass
class PR2Result:
    """Container for the results of a PR2 solver call."""

    is_solved: bool
    """True if a strong-cyclic solution was found."""

    is_strong_cyclic: bool
    """True if the policy is verified strong-cyclic."""

    policy: List[PolicyRule]
    """The conditional policy rules."""

    fsaps: List[FSAP]
    """Forbidden state-action pairs (dead-end avoidance)."""

    raw_policy: str
    """Raw text of policy.out."""

    raw_fsap: str
    """Raw text of policy.fsap."""

    stdout: str
    """Full stdout from the PR2 process."""

    stderr: str
    """Full stderr from the PR2 process."""

    returncode: int
    """Process return code."""

    domain_file: Optional[str] = None
    """Path to the PDDL domain file used (if kept)."""

    problem_file: Optional[str] = None
    """Path to the PDDL problem file used (if kept)."""

    sas_variables: Dict[str, List[str]] = field(default_factory=dict)
    """Mapping from SAS variable keys to human-readable fluent names."""

    domain_pddl: str = ""
    """Raw PDDL text of the domain (always populated)."""

    problem_pddl: str = ""
    """Raw PDDL text of the problem (always populated)."""


# ---------------------------------------------------------------------------
# Policy / FSAP parser (from output.sas + policy.out + policy.fsap)
# ---------------------------------------------------------------------------


def _parse_sas_mapping(sas_path: str) -> Dict[str, str]:
    """Parse the output.sas file to build a variable-value → fluent mapping."""
    mapping = {}
    try:
        with open(sas_path) as f:
            lines = [line.rstrip("\n") for line in f.readlines()]
    except FileNotFoundError:
        return mapping

    # Find variable declarations between 'end_metric' and 'begin_state'
    in_section = False
    idx = 0
    for i, line in enumerate(lines):
        if "end_metric" in line:
            in_section = True
            idx = i + 1
            break
    if not in_section:
        # Try from beginning
        idx = 0

    while idx < len(lines) and "begin_state" not in lines[idx]:
        if lines[idx] == "begin_variable":
            idx += 1
            name = lines[idx]; idx += 1
            idx += 1  # skip axiom layer (-1)
            num_vals = int(lines[idx]); idx += 1
            vals = []
            for _ in range(num_vals):
                raw = lines[idx]; idx += 1
                if raw.startswith("NegatedAtom"):
                    vals.append("not(%s)" % raw.split("Atom ")[-1])
                else:
                    vals.append(raw.split("Atom ")[-1])
            # Fix <none of those>
            if len(vals) == 2:
                if "<none of those>" == vals[0]:
                    vals[0] = "!%s" % vals[1]
                elif "<none of those>" == vals[1]:
                    vals[1] = "!%s" % vals[0]
            for j, v in enumerate(vals):
                mapping["%s:%s" % (name, j)] = v
            assert lines[idx] == "end_variable"
            idx += 1
        else:
            idx += 1

    return mapping


def _translate_policy_line(line: str, mapping: Dict[str, str]) -> str:
    """Translate a single policy line using the SAS mapping."""
    if line.startswith("If"):
        items = line.split(" ")[2:]
        fluents = [mapping.get(item, item) for item in items]
        return "If holds: %s" % "/".join(fluents)
    elif line.startswith("Execute"):
        actname = line.split(" ")[1]
        # Peel off FD translator suffix
        if "_ver" in actname:
            actname = actname.split("_ver")[0]
        rest = " ".join(line.split(" ")[2:])
        return "Execute: %s %s" % (actname, rest)
    return line


def _parse_policy_file(
    path: str, mapping: Dict[str, str], is_fsap: bool = False
) -> Tuple[List[PolicyRule], List[FSAP], str]:
    """Parse a policy.out or policy.fsap file."""
    rules: List[PolicyRule] = []
    fsaps: List[FSAP] = []

    try:
        with open(path) as f:
            raw = f.read()
        lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
    except FileNotFoundError:
        return rules, fsaps, ""

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("If"):
            items = line.split(" ")[2:]
            fluents = frozenset(mapping.get(item, item) for item in items)
            i += 1
            if i < len(lines):
                act_line = lines[i]
                # Extract the full grounded action from the line.
                # Execute lines: "Execute: move-car n12 n0 / SC / d=1"
                # Forbid lines:  "Forbid: move-car n2 n1"
                if ": " in act_line:
                    action_part = act_line.split(": ", 1)[1]
                else:
                    action_part = act_line
                # Strip metadata suffix (/ SC / d=N or / NSC / d=N)
                if " / " in action_part:
                    action_part = action_part.split(" / ")[0]
                action_part = action_part.strip()
                # Parse into name + args, strip FD translator _ver suffix
                parts = action_part.split()
                if parts and "_ver" in parts[0]:
                    parts[0] = parts[0].split("_ver")[0]
                grounded_action = " ".join(parts)
                action_name = parts[0] if parts else action_part
                action_args = tuple(parts[1:]) if len(parts) > 1 else ()
                if is_fsap:
                    fsaps.append(FSAP(
                        condition=fluents,
                        action=grounded_action,
                        action_name=action_name,
                        action_args=action_args,
                    ))
                else:
                    rules.append(PolicyRule(
                        condition=fluents,
                        action=grounded_action,
                        action_name=action_name,
                        action_args=action_args,
                    ))
        i += 1

    return rules, fsaps, raw


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


class PR2Solver:
    """
    Solve FOND planning problems with PR2.

    Parameters
    ----------
    pr2_root : Path or str, optional
        Path to the PR2 repository root.  Defaults to the directory
        containing this file.
    disable_object_sampling : bool
        Pass ``--disable-object-sampling`` to PR2.
    extra_args : list of str
        Additional command-line arguments forwarded to PR2.
    timeout : int or None
        Timeout in seconds for the PR2 process.
    keep_files : bool
        If True, PDDL/SAS files are kept after solving (in a temp dir).
    """

    # PR2 exit codes (from driver/returncodes.py)
    EXIT_STRONG_CYCLIC = 9
    EXIT_STRONG = 10
    EXIT_NOT_STRONG_CYCLIC = 11

    def __init__(
        self,
        pr2_root: Optional[str | Path] = None,
        disable_object_sampling: bool = True,
        extra_args: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        keep_files: bool = False,
    ):
        self.pr2_root = Path(pr2_root) if pr2_root else _PR2_ROOT
        self.pr2_script = self.pr2_root / "pr2"
        self.disable_object_sampling = disable_object_sampling
        self.extra_args = extra_args or []
        self.timeout = timeout
        self.keep_files = keep_files

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve_from_pddl_strings(
        self,
        domain_pddl: str,
        problem_pddl: str,
        *,
        timeout: Optional[int] = None,
        extra_args: Optional[List[str]] = None,
    ) -> PR2Result:
        """
        Solve from raw PDDL strings (domain + problem).

        Useful when you already have PDDL text and don't need the ``pddl``
        library objects.
        """
        timeout = timeout if timeout is not None else self.timeout
        merged_extra = extra_args or []

        tmpdir = tempfile.mkdtemp(prefix="pr2_")
        domain_file = os.path.join(tmpdir, "domain.pddl")
        problem_file = os.path.join(tmpdir, "problem.pddl")

        with open(domain_file, "w") as f:
            f.write(domain_pddl)
        with open(problem_file, "w") as f:
            f.write(problem_pddl)

        try:
            return self._run_pr2(domain_file, problem_file, tmpdir, timeout, merged_extra)
        finally:
            if not self.keep_files:
                shutil.rmtree(tmpdir, ignore_errors=True)

    def solve_from_files(
        self,
        domain_file: str | Path,
        problem_file: str | Path,
        *,
        timeout: Optional[int] = None,
        extra_args: Optional[List[str]] = None,
    ) -> PR2Result:
        """
        Solve from existing PDDL files on disk.

        A working directory is created automatically; the original files are
        not modified.
        """
        timeout = timeout if timeout is not None else self.timeout
        merged_extra = extra_args or []

        tmpdir = tempfile.mkdtemp(prefix="pr2_")
        dom_copy = os.path.join(tmpdir, "domain.pddl")
        prob_copy = os.path.join(tmpdir, "problem.pddl")
        shutil.copy2(str(domain_file), dom_copy)
        shutil.copy2(str(problem_file), prob_copy)

        try:
            return self._run_pr2(dom_copy, prob_copy, tmpdir, timeout, merged_extra)
        finally:
            if not self.keep_files:
                shutil.rmtree(tmpdir, ignore_errors=True)

    def solve_unified_planning_problem(
        self,
        problem,
        *,
        timeout: Optional[int] = None,
        extra_args: Optional[List[str]] = None,
    ) -> PR2Result:
        """Solve a supported unified-planning Problem through PR2 directly."""
        timeout = timeout if timeout is not None else self.timeout
        merged_extra = extra_args or []
        lowered = lower_up_problem(problem)

        tmpdir = tempfile.mkdtemp(prefix="pr2_up_")
        sas_file = os.path.join(tmpdir, "output.sas")

        try:
            up_task_to_sas(lowered, sas_file)
            return self._run_pr2_from_sas(
                sas_file,
                tmpdir,
                timeout,
                merged_extra,
                domain_pddl=lowered.domain_pddl,
                problem_pddl=lowered.problem_pddl,
            )
        finally:
            if not self.keep_files:
                shutil.rmtree(tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_pr2(
        self,
        domain_file: str,
        problem_file: str,
        workdir: str,
        timeout: Optional[int],
        extra_args: List[str],
    ) -> PR2Result:
        """Execute the pr2 script and parse results."""

        cmd = [str(self.pr2_script)]
        if self.disable_object_sampling:
            cmd.append("--disable-object-sampling")
        cmd.extend([domain_file, problem_file])
        cmd.extend(extra_args)

        env = os.environ.copy()
        # Ensure the pr2 scripts directory is importable
        env["PYTHONPATH"] = str(self.pr2_root / "prp-scripts") + ":" + env.get("PYTHONPATH", "")

        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            return PR2Result(
                is_solved=False,
                is_strong_cyclic=False,
                policy=[],
                fsaps=[],
                raw_policy="",
                raw_fsap="",
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                returncode=-1,
            )

        returncode = proc.returncode

        # Determine solution status.  PR2 prints the verdict to stderr;
        # the search component returns exit code 9 (strong cyclic) but the
        # bash wrapper uses ``|| true`` so the overall exit code is 0.
        combined = proc.stdout + proc.stderr
        is_strong_cyclic = "Strong cyclic solution found." in combined
        is_solved = is_strong_cyclic

        # Parse the SAS mapping from output.sas
        sas_path = os.path.join(workdir, "output.sas")
        mapping = _parse_sas_mapping(sas_path)

        # Parse policies
        policy_path = os.path.join(workdir, "policy.out")
        fsap_path = os.path.join(workdir, "policy.fsap")

        rules, _, raw_policy = _parse_policy_file(policy_path, mapping, is_fsap=False)
        _, fsaps, raw_fsap = _parse_policy_file(fsap_path, mapping, is_fsap=True)

        # Read PDDL content before the workdir might be cleaned up
        try:
            with open(domain_file) as _f:
                _domain_pddl = _f.read()
        except OSError:
            _domain_pddl = ""
        try:
            with open(problem_file) as _f:
                _problem_pddl = _f.read()
        except OSError:
            _problem_pddl = ""

        result = PR2Result(
            is_solved=is_solved,
            is_strong_cyclic=is_strong_cyclic,
            policy=rules,
            fsaps=fsaps,
            raw_policy=raw_policy,
            raw_fsap=raw_fsap,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=returncode,
            sas_variables=mapping,
            domain_pddl=_domain_pddl,
            problem_pddl=_problem_pddl,
        )

        if self.keep_files:
            result.domain_file = domain_file
            result.problem_file = os.path.join(workdir, "problem.pddl")

        return result

    def _run_pr2_from_sas(
        self,
        sas_file: str,
        workdir: str,
        timeout: Optional[int],
        extra_args: List[str],
        *,
        domain_pddl: str = "",
        problem_pddl: str = "",
    ) -> PR2Result:
        """Execute only the PR2 search stage from an already translated SAS task."""
        cmd = [
            sys.executable,
            str(_FD_SCRIPT),
            "--build=release64",
            sas_file,
            "--search",
            "prpsearch()",
        ]
        cmd.extend(extra_args)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.pr2_root / "prp-scripts") + ":" + env.get("PYTHONPATH", "")

        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            return PR2Result(
                is_solved=False,
                is_strong_cyclic=False,
                policy=[],
                fsaps=[],
                raw_policy="",
                raw_fsap="",
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                returncode=-1,
                domain_pddl=domain_pddl,
                problem_pddl=problem_pddl,
            )

        combined = proc.stdout + proc.stderr
        is_strong_cyclic = "Strong cyclic solution found." in combined
        is_solved = is_strong_cyclic

        mapping = _parse_sas_mapping(sas_file)
        policy_path = os.path.join(workdir, "policy.out")
        fsap_path = os.path.join(workdir, "policy.fsap")
        rules, _, raw_policy = _parse_policy_file(policy_path, mapping, is_fsap=False)
        _, fsaps, raw_fsap = _parse_policy_file(fsap_path, mapping, is_fsap=True)

        return PR2Result(
            is_solved=is_solved,
            is_strong_cyclic=is_strong_cyclic,
            policy=rules,
            fsaps=fsaps,
            raw_policy=raw_policy,
            raw_fsap=raw_fsap,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
            sas_variables=mapping,
            domain_pddl=domain_pddl,
            problem_pddl=problem_pddl,
        )

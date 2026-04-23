# From FOND Policy to Behavior Tree

This article describes how `Planner/bt_synthesis/builder.py` converts a
PR2 FOND policy into a reactive Behavior Tree (BT) that preserves PR2's
strong-cyclic execution semantics.

## 1. Background: what PR2 actually returns

PR2 (the PRP-derived FOND planner) emits two artifacts:

- **`policy.out`** — an ordered list of conditional rules of the form

  ```
  If <fluent literals>
  Execute: <grounded action>
  ```

- **`policy.fsap`** — a list of *forbidden state-action pairs* (FSAPs)
  with the same `If ... / Forbid: <action>` shape, used to rule out
  actions in states known to lead to dead ends.

The reference dispatcher shipped with PR2
(`prp-scripts/validators/prp.py`) is the contract a faithful executor
has to honour:

```python
def next_action(s):
    for (n, p, a) in POLICY:                       # iterate in file order
        if 0 == len(n & s.fluents) and p <= s.fluents:
            ok = True
            for (n2, p2) in FSAP.get(a, []):       # FSAP veto
                if 0 == len(n2 & s.fluents) and p2 <= s.fluents:
                    ok = False
            if ok:
                return a
    return None
```

So the semantics the BT must reproduce are:

1. **First-match wins** — rules are evaluated in `policy.out` file order.
2. **FSAP veto** — a rule is skipped if any FSAP for its action fires.
3. **Reactivity** — every tick re-evaluates from the top; no committed
   plan prefix.

These three properties together are what make the policy *strong-cyclic*.
Re-ordering rules, dropping FSAPs, or committing to a previously chosen
action all break the guarantee.

## 2. Why a naive lowering fails

PRP synthesises rule conditions by goal-regression and then *generalises*
them: a rule keeps only the literals that the regression actually relies
on. As a side effect, two generalised rule conditions can both be true
in the same concrete state. The disambiguation is delegated to the file
order plus FSAPs — they are part of the policy, not just metadata.

A previous version of `policy_to_bt` made two independent mistakes:

- It re-sorted rules by a "specificity" key (`-len(condition)`), which
  destroyed the file order PRP relies on.
- Its hoisting recursion globally partitioned rules into "those
  containing literal `X`" and "the rest", then placed the `with-X`
  branch first under a `ReactiveSelector`. That promoted any
  `X`-containing rule above any non-`X` rule, regardless of where they
  appeared in `policy.out`.
- FSAPs were dropped entirely.

On `first-responders` the result was 0 % goal reach — the BT looped on
an idempotent action whose preconditions stayed satisfied because PRP's
intended next rule had been demoted by hoisting.

## 3. The current pipeline

`policy_to_bt(result, problem=None, hoist_conditions=True)` is the
single public entry point. It performs four phases.

### Phase 1 — Normalisation

`_normalize_policy_rules` flattens each `up.plans.PolicyRule` into a
`_PolicyRuleView`:

```python
@dataclass(frozen=True)
class _PolicyRuleView:
    condition: FrozenSet[str]   # e.g. {"have-water(f1)", "not(fire(l3))"}
    action: str                 # "treat-victim-at-hospital v9 l3"
    action_name: str            # "treat-victim-at-hospital"
    action_args: Tuple[str, ...]
```

Conditions are taken from `raw_condition_literals` (the verbatim
PR2-side strings) when available, falling back to the structured
`condition` mapping. Negative literals are normalised to the
`not(<atom>)` form so downstream code can use plain string set
operations. Crucially, **iteration order over the input list is
preserved** — the resulting `List[_PolicyRuleView]` is in PR2 file
order.

`_normalize_fsaps` does the same for `result.fsaps`. FSAPs are then
indexed by `(action_name, action_args)` via `_build_fsap_map`, so each
rule can find the FSAPs that apply to its concrete action in O(1).

`goal` rules (PR2's pseudo-action emitted when the state already
satisfies the goal) are split out and turned into a dedicated branch by
`_build_goal_branch`. If the policy carries no goal rule, the goal
expression of the original `Problem` is used as a fallback gate
(`_build_problem_goal_branch`).

### Phase 2 — FSAP-guarded rule leaves

Each policy rule becomes a `Sequence` whose children are, in order:

1. One `ConditionNode` per positive condition literal, plus an
   `Inverter(ConditionNode)` per negated literal, in lexical order
   (deterministic sub-ordering inside a single rule's preconditions
   does not affect first-match semantics).
2. **Zero or more FSAP guards.** For every FSAP `f` whose
   `(action_name, action_args)` matches this rule,
   `_build_fsap_guard` builds

   ```
   Inverter( ReactiveSequence(
       ConditionNode(lit_1),
       ConditionNode(lit_2),
       ...
   ))
   ```

   The inner `ReactiveSequence` succeeds iff every FSAP literal holds;
   the surrounding `Inverter` then fails, causing the rule's `Sequence`
   to fail, causing the parent `ReactiveSelector` to try the next rule.
   This is *exactly* the veto path in PR2's `next_action`. FSAPs are
   appended in their original PR2 list order. An FSAP with an empty
   condition would unconditionally forbid the action, which PRP never
   emits and which is skipped defensively.
3. The `ActionNode` that executes the grounded action.

### Phase 3 — Order-preserving hoisting

When `hoist_conditions=True` (default), the rule list is fed to
`_build_hoisted_rule_selector`. The recursion walks the list
left-to-right and at each position asks `_longest_shared_run`: *what is
the longest contiguous prefix starting here whose rules all share some
literal `X`?* Concretely:

```python
def _longest_shared_run(rules, start):
    candidates = rules[start].condition
    best_literal, best_end = None, start + 1
    for literal in sorted(candidates):
        end = start + 1
        while end < len(rules) and literal in rules[end].condition:
            end += 1
        if end - start >= 2 and (end - start) > (best_end - start):
            best_literal, best_end = literal, end
    return best_literal, best_end
```

If a run of length `k ≥ 2` is found, the recursion factors literal
`X` out:

```
When_X
├── Condition(X)
└── <recursive hoist of rules[start:end] with X removed>
```

Otherwise the current rule is emitted verbatim and we advance by one.
After processing the whole list, the resulting sequence of branches
becomes the children of a single `ReactiveSelector`.

The crucial difference from the previous design is that **a hoist
never crosses a non-matching neighbour**. If rule `i` does not contain
`X` it terminates the run that started before it, so the resulting
selector children are in exactly the same first-match order as the
original `policy.out`. Hoisting becomes a pure factoring operation:
it changes how conditions are grouped under `When_*` gates, never
which rule fires first in any given state.

`_hoist_common` (a separate, simpler pass) lifts literals shared by
*every* action rule into a single outermost `Sequence("PolicyRules",
…)` gate. This is also order-preserving because it does not reorder
the inner rules; it only deduplicates a check that would otherwise
appear inside every leaf.

A final clean-up pass, `_flatten_linear_condition_sequences`, collapses
the chains `Sequence(cond, Sequence(cond2, …))` that hoisting can
produce when a deeply nested run was factored, turning them into a
single `Sequence` of conditions followed by the inner branching node.
This is a pure structural simplification and does not change tick
semantics.

### Phase 4 — Goal handling and the outer loop

Two cases exist for the root:

- **No goal branch.** The progression itself is the root.
- **Goal branch present.** The progression is wrapped in
  `KeepRunningUntilFailure(progression, name="PolicyLoop")`, and the
  root becomes

  ```
  PolicyRoot (ReactiveSelector)
  ├── GoalBranch       (succeeds when goal literals hold)
  └── PolicyLoop       (KeepRunningUntilFailure(progression))
  ```

  Each tick first checks the goal; on goal reach the BT returns
  `SUCCESS`. Otherwise the progression executes one rule per tick.
  The `KeepRunningUntilFailure` decorator turns rule successes into
  `RUNNING`, keeping the BT live until either the goal branch fires or
  a rule selection genuinely fails (no rule applies and no FSAP-veto
  fall-through is possible).

After construction the tree is passed through `parameterize_subtrees`
and `deduplicate_subtrees` from `optimizer.py`, which extract repeated
subtrees into reusable templates. These transformations are
shape-preserving with respect to tick semantics.

## 4. Resulting tree shape

For a policy with rules

```
R1: If A B   / Execute: act1
R2: If A C   / Execute: act2
R3: If D     / Execute: act3
```

and one FSAP `(C ⇒ Forbid: act2)`, the relevant fragment of the BT is:

```
ReactiveSelector "Progression"
├── Sequence "When_A"
│   ├── Condition A
│   └── ReactiveSelector
│       ├── Sequence "act1"
│       │   ├── Condition B
│       │   └── Action act1
│       └── Sequence "act2"
│           ├── Condition C
│           ├── Inverter(ReactiveSequence(Condition C))   -- FSAP guard
│           └── Action act2
└── Sequence "act3"
    ├── Condition D
    └── Action act3
```

Reading this tick-by-tick: in any state where `A` holds, the inner
selector tries `act1` first (because `R1` came first in `policy.out`);
if `B` is false it tries `act2`; the FSAP veto then blocks `act2` when
`C` holds, and execution falls through to the `act3` sibling — exactly
what PR2's `next_action` would compute, but expressed as a tree.

## 5. The trivial baseline

`policy_to_bt_trivial(result, …)` calls `policy_to_bt` with
`hoist_conditions=False`. That path uses `_build_plain_rule_selector`,
which iterates the rule list in PR2 file order and emits one
FSAP-guarded leaf per rule under a single `ReactiveSelector`. It is
useful as a reference implementation: by construction it is
syntactically the closest BT to the validator loop, so any deviation
from the hoisted variant in simulation indicates a hoisting bug rather
than a semantic gap with PR2.

## 6. Properties of the resulting BT

The synthesis preserves the three properties enumerated in §1:

- **First-match.** `_build_plain_rule_selector` and
  `_build_hoisted_rule_selector` both iterate rules in their input
  order. Hoisting only factors literals across contiguous runs, so the
  left-to-right child order of every `ReactiveSelector` matches the
  PR2 file order of its rules.
- **FSAP veto.** Every action leaf carries the FSAPs for its
  `(action_name, action_args)` as `Inverter` guards before the action,
  exactly mirroring `next_action`'s inner `for (n2, p2) in FSAP[a]`
  loop.
- **Reactivity.** The progression is a `ReactiveSelector`, which
  re-ticks its children from the left every tick; the outer
  `KeepRunningUntilFailure` re-enters the progression every tick after
  each rule completion. There is no committed plan suffix.

Empirically, the change from "globally partitioning" hoisting +
FSAP-less leaves to "contiguous-run" hoisting + FSAP-guarded leaves
takes `first-responders` from 0 % goal reach (100 % timeout) to 100 %
goal reach in roughly 30 ticks per episode, with the hoisted variant
ticking ≈ 43 % fewer nodes per episode than the trivial baseline while
producing identical action traces.

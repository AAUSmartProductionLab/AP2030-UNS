from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence


@dataclass(frozen=True)
class FONDEffect:
    """A boolean effect specification for local FOND modeling on UP actions."""

    fluent: Any
    value: Any
    condition: Any


@dataclass(frozen=True)
class OneOfEffectGroup:
    """A oneof outcome group attached to a UP action."""

    outcomes: tuple[tuple[FONDEffect, ...], ...]
    labels: tuple[str, ...]


def fond_effect(fluent: Any, value: Any = True, condition: Any = None) -> FONDEffect:
    """Create a local FOND effect specification using UP expressions.

    The fluent and condition can be fluent expressions or other UP expressions.
    The value can be a Python bool or a UP expression.
    """
    env = fluent.environment
    em = env.expression_manager
    (fluent_exp,) = em.auto_promote(fluent)
    (value_exp,) = em.auto_promote(value)
    if condition is None:
        condition_exp = em.TRUE()
    else:
        (condition_exp,) = em.auto_promote(condition)
    return FONDEffect(fluent=fluent_exp, value=value_exp, condition=condition_exp)


def add_oneof_effect(
    action: Any,
    outcomes: Iterable[Iterable[FONDEffect]],
    *,
    labels: Optional[Sequence[str]] = None,
) -> OneOfEffectGroup:
    """Attach a oneof outcome group to an InstantaneousAction.

    Each entry in ``outcomes`` is one possible outcome and contains zero or more
    boolean effects represented with ``fond_effect``.
    """
    normalized_outcomes = tuple(tuple(outcome) for outcome in outcomes)
    if len(normalized_outcomes) == 0:
        raise ValueError("A oneof effect group must contain at least one outcome.")
    for outcome in normalized_outcomes:
        for effect in outcome:
            if not isinstance(effect, FONDEffect):
                raise TypeError("oneof outcomes must contain FONDEffect instances.")

    if labels is None:
        normalized_labels = tuple(str(index + 1) for index in range(len(normalized_outcomes)))
    else:
        normalized_labels = tuple(labels)
        if len(normalized_labels) != len(normalized_outcomes):
            raise ValueError("labels must have the same length as outcomes.")

    if not (hasattr(action, "add_oneof_effect") and hasattr(action, "oneof_effects")):
        raise RuntimeError(
            "Native oneof effects are unavailable on this action. "
            "Use the vendored unified-planning fork with oneof support."
        )

    native_outcomes = []
    for outcome in normalized_outcomes:
        native_outcome = []
        for effect in outcome:
            native_outcome.append((effect.fluent, effect.value, effect.condition))
        native_outcomes.append(tuple(native_outcome))
    native_group = action.add_oneof_effect(native_outcomes, labels=normalized_labels)
    return _native_group_to_local(native_group)


def get_oneof_effect_groups(action: Any) -> tuple[OneOfEffectGroup, ...]:
    """Return the oneof outcome groups attached to a UP action."""
    native_groups = getattr(action, "oneof_effects", ())
    return tuple(_native_group_to_local(group) for group in native_groups)


def has_oneof_effects(action: Any) -> bool:
    return len(get_oneof_effect_groups(action)) > 0


def _native_group_to_local(group: Any) -> OneOfEffectGroup:
    outcomes = []
    for outcome in group.outcomes:
        outcomes.append(
            tuple(
                FONDEffect(
                    fluent=effect.fluent,
                    value=effect.value,
                    condition=effect.condition,
                )
                for effect in outcome
            )
        )
    return OneOfEffectGroup(outcomes=tuple(outcomes), labels=tuple(group.labels))
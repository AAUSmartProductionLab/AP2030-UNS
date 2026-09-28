"""Occupation lifecycle in the simulated station.

In session mode (``use_occupation_logic``) the queue holds OCCUPATIONS. A
process command (Stoppering, …) must not consume the occupation when it
finishes — the resource stays occupied until an explicit Release or an abort.

Both copies of the state machine are covered: ``packml_runtime`` is what the
simulated stations import, and ``Planar_Controller/library`` carries the same
state machine, so neither may silently regress.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# `packml_runtime` is a package under the repo root; `PackMLSimulator` is a
# top-level module inside Planar_Controller/library.
for _path in (ROOT, ROOT / "Planar_Controller" / "library"):
    if _path.is_dir():
        sys.path.insert(0, str(_path))

SIMULATOR_MODULES = ["packml_runtime.simulator", "PackMLSimulator"]


class _StubTopic:
    """Captures publishes instead of talking to a broker."""

    def __init__(self):
        self.published = []

    def publish(self, message, client, retained=False):
        self.published.append(message)


def _build(machine_class, state_enum):
    import inspect

    sm = machine_class.__new__(machine_class)
    sm.base_topic = "test/line"
    sm.client = None
    sm.properties = {}
    sm.config_path = None
    sm.custom_handlers = {}
    sm.state = state_enum.IDLE
    sm.uuids = []
    sm.is_processing = False
    sm.current_processing_uuid = None
    sm.Uuid = None
    sm.processing_events = {}
    sm.interruption_requested_for_uuid = {}
    sm.pending_registrations = {}
    sm.register_topic = _StubTopic()
    sm.unregister_topic = _StubTopic()
    sm.transitions = []
    sm.transition_to = lambda new_state, uuid_param=None: (
        sm.transitions.append((new_state, uuid_param)),
        setattr(sm, "state", new_state),
    )[0]
    sm.publish_state = lambda: None
    # The two copies name the occupation flag differently; set whichever the
    # class actually declares so the fixture cannot invent behaviour.
    params = inspect.signature(machine_class.__init__).parameters
    for flag in ("use_occupation_logic", "enable_occupation"):
        if flag in params:
            setattr(sm, flag, True)
    return sm


@pytest.fixture(params=SIMULATOR_MODULES)
def machine(request):
    module = __import__(request.param, fromlist=["PackMLStateMachine"])
    return _build(module.PackMLStateMachine, module.PackMLState)


def test_completing_a_process_keeps_the_occupation(machine):
    machine.register_command(1)
    assert machine.uuids == [1]

    machine.completing_state(1)

    assert machine.uuids == [1], "the occupation must survive a completed process"
    assert machine.is_processing is False


def test_release_is_the_only_thing_that_ends_an_occupation(machine):
    machine.register_command(1)
    machine.state = type(machine.state).EXECUTE
    machine.unregister_command(1)

    assert machine.uuids == []
    assert machine.unregister_topic.published[-1]["State"] == "SUCCESS"


def test_strict_mode_still_consumes_the_queue_entry_on_completion(machine):
    for flag in ("use_occupation_logic", "enable_occupation"):
        if hasattr(machine, flag):
            setattr(machine, flag, False)
    machine.uuids = [1, 2]
    machine.completing_state(1)
    assert machine.uuids == [2]


def test_abort_clears_occupations(machine):
    machine.register_command(1)
    machine.aborting_state(1)
    assert machine.uuids == []

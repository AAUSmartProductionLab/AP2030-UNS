from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from pathlib import Path


PLANNER_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PLANNER_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packml_runtime.simulator import PackMLState, PackMLStateMachine


class _DummyProxy:
    def __init__(self):
        self.topics = []
        self.published = []

    def register_topic(self, topic):
        self.topics.append(topic)

    def publish(self, topic, payload, qos, properties=None, retain=False):
        del properties
        try:
            decoded = json.loads(payload)
        except Exception:
            decoded = payload
        self.published.append((topic, decoded, qos, retain))


class _DummyExecuteTopic:
    def __init__(self):
        self.messages = []
        self._lock = threading.Lock()

    def publish(self, request, client, retain=False):
        del client, retain
        with self._lock:
            self.messages.append(dict(request))


def _wait_for(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class PackMLServiceQueueTests(unittest.TestCase):
    def test_service_mode_queues_next_uuid_and_runs_it_after_completion(self):
        proxy = _DummyProxy()
        machine = PackMLStateMachine(
            base_topic="test/station",
            client=proxy,
            properties=None,
            enable_occupation=False,
            auto_execute=True,
        )
        execute_topic = _DummyExecuteTopic()

        first_done = threading.Event()
        run_order = []

        def process(marker):
            run_order.append(marker)
            if marker == "first":
                first_done.wait(timeout=1.0)
            return {"State": "SUCCESS", "Marker": marker}

        machine.execute_command({"Uuid": "uuid-1"}, execute_topic, process, "first")
        machine.execute_command({"Uuid": "uuid-2"}, execute_topic, process, "second")

        first_done.set()

        success_seen = _wait_for(
            lambda: sum(1 for m in execute_topic.messages if m.get("State") == "SUCCESS") >= 2,
            timeout=3.0,
        )
        self.assertTrue(success_seen, f"Expected two SUCCESS responses, got: {execute_topic.messages}")

        self.assertEqual(run_order, ["first", "second"])
        self.assertEqual(machine.uuids, [])
        self.assertEqual(machine.state, PackMLState.EXECUTE)

        uuid2_failures = [
            m
            for m in execute_topic.messages
            if m.get("Uuid") == "uuid-2" and m.get("State") == "FAILURE"
        ]
        self.assertEqual(uuid2_failures, [])

    def test_service_mode_duplicate_uuid_is_reported_running_not_failed(self):
        proxy = _DummyProxy()
        machine = PackMLStateMachine(
            base_topic="test/station",
            client=proxy,
            properties=None,
            enable_occupation=False,
            auto_execute=True,
        )
        execute_topic = _DummyExecuteTopic()

        done = threading.Event()
        run_calls = []

        def process(marker):
            run_calls.append(marker)
            done.wait(timeout=1.0)
            return {"State": "SUCCESS"}

        machine.execute_command({"Uuid": "dup-uuid"}, execute_topic, process, "once")
        machine.execute_command({"Uuid": "dup-uuid"}, execute_topic, process, "twice")

        done.set()

        finished = _wait_for(
            lambda: any(
                m.get("Uuid") == "dup-uuid" and m.get("State") == "SUCCESS"
                for m in execute_topic.messages
            ),
            timeout=3.0,
        )
        self.assertTrue(finished, f"Expected SUCCESS response for duplicate UUID, got: {execute_topic.messages}")

        self.assertEqual(len(run_calls), 1)
        self.assertEqual(machine.uuids, [])

        failures = [
            m
            for m in execute_topic.messages
            if m.get("Uuid") == "dup-uuid" and m.get("State") == "FAILURE"
        ]
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
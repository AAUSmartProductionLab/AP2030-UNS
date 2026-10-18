"""Dockerized end-to-end assertions for the shared Java DMP pipeline.

Plan: ``.kilo/plans/1788416400000-e2e-station-bindings-plan.md`` Phase 6.
Run AFTER ``compose/e2e/bootstrap.sh`` brought the stack up:

    python -m pytest compose/e2e/test_e2e.py -q

The suite assumes (all host-published):

- AAS env      http://localhost:${E2E_AAS_PORT:-18081}
- MQTT broker  localhost:${E2E_MQTT_PORT:-18830}   (station + DMP)
- Station UA   opc.tcp://localhost:4840/stoppering/
- Java DMP     http://localhost:${E2E_DMP_PORT:-18086}

Data and Operations require managed convergence. E2E skill Operations use only OPC
UA on canonical paths. Native parameter writes remain available, but the synchronous
DMP Property PUT/same-property-writeback proxy and MQTT timers are retired.
Load-derived timeout evaluation is not part of this correctness suite.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
import uuid

import pytest
import requests

AAS_PORT = int(os.getenv("E2E_AAS_PORT", "18081"))
MQTT_PORT = int(os.getenv("E2E_MQTT_PORT", "18830"))
MQTT_HOST = os.getenv("E2E_MQTT_HOST", "localhost")
AAS_BASE = f"http://localhost:{AAS_PORT}"
UA_ENDPOINT = os.getenv("E2E_UA_ENDPOINT", "opc.tcp://localhost:4840/stoppering/")
DMP_BASE = os.getenv("E2E_DMP_BASE_URL", f"http://localhost:{os.getenv('E2E_DMP_PORT', '18086')}").rstrip("/")
AAS_ID_SHORT = "syntegonStopperingSystemAAS"
BASE_TOPIC = "NN/Nybrovej/InnoLab/Stoppering"

pytest.importorskip("paho.mqtt")
pytest.importorskip("asyncua")

import paho.mqtt.client as paho_mqtt  # noqa: E402


# ------------------------------------------------------------------ helpers

def dmp_base_url() -> str:
    """Fixed host-side test endpoint, distinct from AAS's internal dmp:8080."""
    return DMP_BASE


def _b64(sm_id: str) -> str:
    return base64.urlsafe_b64encode(sm_id.encode()).decode().rstrip("=")


def aas_submodel_id(session: requests.Session, id_short: str) -> str:
    resp = session.get(f"{AAS_BASE}/submodels", timeout=10)
    resp.raise_for_status()
    for sm in resp.json().get("result", []):
        if sm.get("idShort") == id_short:
            return sm["id"]
    raise AssertionError(f"submodel {id_short!r} not on the e2e AAS env")


@pytest.fixture(scope="session")
def aas(http):
    """Variables-submodel accessor for the e2e AAS."""
    sm_id = aas_submodel_id(http, "Variables")
    b64 = _b64(sm_id)
    root = f"{AAS_BASE}/submodels/{b64}/submodel-elements"

    def read(path: str):
        resp = http.get(f"{root}/{path}", timeout=10)
        resp.raise_for_status()
        return resp.json().get("value")

    return read


@pytest.fixture(scope="session")
def http():
    session = requests.Session()
    yield session
    session.close()


@pytest.fixture(scope="session")
def dmp(http):
    base = dmp_base_url()
    # A live control feed alone is not proof every authored mapping installed.
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            response = http.get(f"{base}/management/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                if status.get("converged") and status.get("installedMappings", 0) > 0:
                    break
        except Exception:
            pass
        time.sleep(2)
    else:
        raise AssertionError(f"DMP {base} never converged; inspect /management/status for blocked mappings")

    def post(path: str, body: object, timeout: float = 45.0):
        return http.post(f"{base}{path}", json=body, timeout=timeout)

    def put(path: str, body: dict, timeout: float = 45.0):
        return http.put(f"{base}{path}", json=body, timeout=timeout)

    return {"base": base, "post": post, "put": put}


class MqttCapture:
    """Records messages on a topic (plus optionally publishes commands)."""

    def __init__(self, topic: str):
        self.topic = topic
        self.messages: list[dict] = []
        self._lock = threading.Lock()
        self.client = paho_mqtt.Client(
            client_id=f"e2e-capture-{uuid.uuid4().hex[:8]}", protocol=paho_mqtt.MQTTv311)
        self.client.on_message = self._on_message
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.client.loop_start()
        self.client.subscribe(topic, qos=2)

    def _on_message(self, _c, _u, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            payload = {"raw": msg.payload.decode(errors="replace")}
        with self._lock:
            self.messages.append(payload)

    def publish(self, topic: str, payload: dict, retain: bool = False):
        self.client.publish(topic, json.dumps(payload), qos=2, retain=retain)

    def wait_for(self, predicate, timeout: float):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for m in self.messages:
                    if predicate(m):
                        return m
            time.sleep(0.1)
        return None

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


@pytest.fixture()
def mqtt():
    holder: list[MqttCapture] = []

    def capture(topic: str) -> MqttCapture:
        c = MqttCapture(topic)
        holder.append(c)
        return c

    yield capture
    for c in holder:
        c.close()


@pytest.fixture(scope="session")
def ua():
    """Sync-wrapped asyncua client on the simulated station."""
    from asyncua.sync import Client

    client = Client(UA_ENDPOINT, timeout=10)
    client.connect()
    try:
        yield client
    finally:
        client.disconnect()


def ua_node(ua, node_id: str):
    return ua.get_node(f"ns=2;s={node_id}")


def eventually(read, path, expect, timeout: float, *, label: str):
    """Poll an AAS reader until it satisfies ``expect`` (a value, callable,
    or a float-tolerant number: the AAS leaf stores values as strings)."""
    deadline = time.time() + timeout
    last = "<unread>"

    def ok(value):
        if callable(expect):
            return expect(value)
        if isinstance(expect, (int, float)) and not isinstance(expect, bool):
            try:
                return float(value) == float(expect)
            except (TypeError, ValueError):
                return False
        return value == expect

    while time.time() < deadline:
        last = read(path)
        if ok(last):
            return last
        time.sleep(0.4)
    raise AssertionError(f"{label}: value never reached expectation "
                         f"(last={last!r}, within {timeout}s)")


def ensure_ready(mqtt_capture, aas):
    """Make sure the machine is in a ready state (a previous test's Abort
    leaves it ABORTED; a Reset brings it back)."""
    state = aas("PackMLState")
    if state in ("EXECUTE", "IDLE"):
        return
    mqtt_capture.publish(f"{BASE_TOPIC}/CMD/State",
                         {"StateId": "Reset", "Uuid": str(uuid.uuid4()),
                          "TimeStamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                     time.gmtime())})
    eventually(aas, "PackMLState",
               lambda v: v in ("EXECUTE", "IDLE"), 8.0,
               label="station back to a ready state")


def drive_skill(aas, dmp, skill="Stoppering"):
    """Queue the skill: the machine queues the command and runs
    STARTING -> EXECUTE -> process -> ... -> IDLE by itself (service mode)."""
    resp = dmp["post"](f"/operations/{AAS_ID_SHORT}/{skill}", operation_arguments())
    assert resp.status_code == 200, resp.text
    return resp


def operation_arguments(request_id: str | None = None) -> list[dict]:
    """The AAS delegator's OperationVariable array, including unchanged Uuid InOut."""
    return [{"value": {"modelType": "Property", "idShort": "Uuid",
                       "valueType": "xs:string", "value": request_id or str(uuid.uuid4())}}]


# ------------------------------------------------------------------- A: data

def test_a1_mqtt_event_streaming(aas, dmp, mqtt):
    """PackML transition → AAS Variables.PackMLState update (event leg)."""
    capture = mqtt(f"{BASE_TOPIC}/DATA/State")
    # service mode keeps the machine in EXECUTE except for instant flashes;
    # ABORT yields a SUSTAINED state the event leg can stream
    capture.publish(f"{BASE_TOPIC}/CMD/State",
                    {"StateId": "Abort", "Uuid": str(uuid.uuid4()),
                     "TimeStamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                time.gmtime())})
    eventually(aas, "PackMLState", "ABORTED", 5.0,
               label="A1 PackMLState reaches ABORTED (event leg)")
    capture.publish(f"{BASE_TOPIC}/CMD/State",
                    {"StateId": "Reset", "Uuid": str(uuid.uuid4()),
                     "TimeStamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                time.gmtime())})
    eventually(aas, "PackMLState",
               lambda v: v in ("EXECUTE", "IDLE"), 8.0,
               label="A1 PackMLState back to a ready state")


def test_a3_opcua_event_streaming(aas, dmp, ua, mqtt):
    """Station data-change (UA monitored item) → AAS MeasurementFast."""
    capture = mqtt(f"{BASE_TOPIC}/DATA/State")
    ensure_ready(capture, aas)
    ua_fast = ua_node(ua, "MeasurementFast")
    before_ua = float(ua_fast.read_value())
    drive_skill(aas, dmp)
    # each queued skill runs a cycle -> several transitions -> the UA counter
    # bumps; the monitored item streams it
    now_ua = before_ua
    deadline = time.time() + 5.0
    while time.time() < deadline:
        now_ua = ua_fast.read_value()
        if now_ua != before_ua:
            break
        time.sleep(0.2)
    assert now_ua != before_ua, "station did not bump MeasurementFast"
    eventually(aas, "MeasurementFast", now_ua, 5.0,
               label="A3 AAS MeasurementFast equals the UA value")


def test_a4_opcua_timer_streaming(aas, ua):
    """MeasurementSlow (sine, 1 s) sampled at the declared 2 s cadence."""
    first = aas("MeasurementSlow")
    deadline = time.time() + 6.0
    second = first
    while time.time() < deadline:
        second = aas("MeasurementSlow")
        if second != first:
            return
        time.sleep(0.4)
    raise AssertionError(f"A4 MeasurementSlow never updated (stuck at {first!r})")


# --------------------------------------------------------------- B: writes

def test_b1_native_mqtt_parameter_write(mqtt, ua):
    """Native MQTT parameter writes remain available without a DMP proxy."""
    value = 42
    request_id = str(uuid.uuid4())
    feed = mqtt(f"{BASE_TOPIC}/DATA/Parameter")
    feed.publish(f"{BASE_TOPIC}/CMD/Parameter", {"Uuid": request_id, "Value": value})
    ack = feed.wait_for(lambda m: m.get("Uuid") == request_id and m.get("State") == "SUCCESS", 10.0)
    assert ack is not None, "no matching successful native Parameter acknowledgement"
    assert ack["Value"] == value
    assert ua_node(ua, "Parameter").read_value() == value


def test_b2_native_opcua_parameter_write(ua):
    """Native UA writes retain their declared Double representation."""
    from asyncua import ua as ua_types

    value = 77.0
    ua_node(ua, "Parameter").write_value(ua_types.Variant(value, ua_types.VariantType.Double))
    assert ua_node(ua, "Parameter").read_value() == value


@pytest.mark.parametrize("suffix", ["", "/opcua"])
def test_b3_synchronous_property_proxy_is_absent(dmp, suffix):
    response = dmp["put"](f"/properties/{AAS_ID_SHORT}/Parameter{suffix}", {"value": 77})
    assert response.status_code == 404, response.text


# ------------------------------------------------------------- C: operations

def test_c1_canonical_operation_uses_ua_not_mqtt(dmp, mqtt):
    """The canonical E2E operation is UA-backed, not an MQTT command fan-out."""
    request_id = str(uuid.uuid4())
    commands = mqtt(f"{BASE_TOPIC}/CMD/Halt")
    resp = dmp["post"](f"/operations/{AAS_ID_SHORT}/Halt", operation_arguments(request_id))
    assert resp.status_code == 200, resp.text
    variables = resp.json()
    assert variables[0]["value"]["idShort"] == "Uuid"
    reply = {v["value"]["idShort"]: v["value"]["value"] for v in variables}
    assert reply["Uuid"]
    assert reply["State"] == "SUCCESS"
    time.sleep(0.5)
    with commands._lock:
        assert not commands.messages, "UA-only operation also sent an MQTT command"


def test_c2_opcua_operation_delegation(dmp, ua, mqtt, aas):
    """The canonical skill path invokes the UA method and returns declared values."""
    ensure_ready(mqtt(f"{BASE_TOPIC}/DATA/State"), aas)
    resp = dmp["post"](f"/operations/{AAS_ID_SHORT}/Stoppering", operation_arguments())
    assert resp.status_code == 200, resp.text
    reply = {v["value"]["idShort"]: v["value"]["value"] for v in resp.json()}
    assert reply["State"] == "SUCCESS", reply
    assert reply["Uuid"]


def test_c2_legacy_ua_alias_is_not_an_extra_operation(dmp):
    resp = dmp["post"](f"/operations/{AAS_ID_SHORT}/Stoppering/opcua", operation_arguments())
    assert resp.status_code == 404, resp.text


@pytest.mark.skip(reason="Legacy load-derived timeout evaluation is deferred; isolated Java tests cover deterministic 504")
def test_c3_operation_timeout_is_504(dmp, mqtt, aas):
    """A skill that cannot reply within the route timeout returns 504.

    The stoppering process runs ~2 s per command and the station queues
    concurrent commands; flooding 18 invocations makes the tail replies land
    beyond the 30 s route timeout."""
    results: list[int] = []
    lock = threading.Lock()

    ensure_ready(mqtt(f"{BASE_TOPIC}/DATA/State"), aas)

    def invoke():
        try:
            resp = dmp["post"](f"/operations/{AAS_ID_SHORT}/Stoppering", operation_arguments(),
                               timeout=60.0)
            with lock:
                results.append(resp.status_code)
        except Exception:
            with lock:
                results.append(-1)

    threads = [threading.Thread(target=invoke) for _ in range(18)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(70)
    assert 504 in results, f"no gateway timeout observed: {sorted(results)}"
    assert set(results) <= {200, 504}, sorted(results)

"""OPC UA twin of the MQTT skill surface (asyncua).

Runs an ``asyncua.Server`` on its own asyncio loop in a daemon thread —
the OPC UA counterpart of ``packml_runtime.mqtt.Proxy`` — and builds the
address space the AID's ``InterfaceTemplateForOPCUA`` describes:

- a ``Station`` Object (``ns=2;s=Station``, mirrors the CCI) with a
  read-only ``StationState`` variable;
- one Object + Method per skill: ``ns=2;s=<Skill>`` owning
  ``ns=2;s=<Skill>Method`` (OPC-10101 §7.1.3). The DMP's milo-client Call
  rides the Lua-shaped command as a single String InputArgument
  ``Command`` — the JSON blob ``{"Uuid": "..."}`` (a bare Uuid from a
  plain UA client is accepted too); OutputArguments are
  ``State: String`` / ``Outcome: Int32``. Each invocation runs the SAME
  skill logic the MQTT callbacks run, via ``skill_handler``;
- ``MeasurementFast`` (Double, event-updated on PackML state transitions —
  the event-mode stream) and ``MeasurementSlow`` (Double, a slowly varying
  simulated process value — the timer-mode stream), so polled and
  subscription consumers are independently observable;
- a writable ``Parameter`` (Double) whose write hook runs the parameter
  logic and acknowledges: the UA write status IS the ack, read-back
  returns the effective value.

The first custom namespace is expected to be index 2 (the AID authors
``ns=2;s=...`` NodeIds); a deviation is logged loudly.
"""

import asyncio
import faulthandler
import json
import logging
import math
import signal
import sys
import threading
import time
import uuid as uuid_module
from typing import Callable, Dict, Optional, Sequence

from asyncua import Server, ua

logger = logging.getLogger("packml_runtime.opcua")

#: The AID authors ``ns=2;s=...`` NodeIds (one registered custom namespace).
EXPECTED_NAMESPACE_INDEX = 2

#: The writable process parameter (stopper force threshold, N) — the value
#: written via OPC UA (and, from the MQTT binding, via the parameter command
#: topic) must stay within this range.
PARAMETER_MIN = 0.0
PARAMETER_MAX = 100.0

#: Effective value before the first write.
PARAMETER_DEFAULT = 50.0

#: Slowly varying simulated process value (bar): sine period in seconds.
SLOW_MEASUREMENT_PERIOD_S = 40.0


class StationOpcuaServer:
    """asyncua server exposing skills, measurements and the writable
    parameter. Skill invocations are delegated to ``skill_handler(skill,
    uuid) -> {"State": str, "Outcome": int}``; the PackML state mirror is
    read from ``state_provider() -> str``."""

    def __init__(
        self,
        endpoint: str = "opc.tcp://0.0.0.0:4840/stoppering/",
        namespace_uri: str = "https://aausmartproductionlab.github.io/AP2030-UNS/Stoppering",
        skills: Sequence[str] = ("Stoppering", "Halt", "Occupy", "Release"),
        skill_handler: Optional[Callable[[str, str], Dict]] = None,
        state_provider: Optional[Callable[[], str]] = None,
        transition_counter: Optional[Callable[[], int]] = None,
        slow_interval: float = 1.0,
        parameter_state: Optional[Dict] = None,
        parameter_lock: Optional[threading.Lock] = None,
    ):
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.skills = list(skills)
        self.skill_handler = skill_handler
        self.state_provider = state_provider or (lambda: "")
        # preferred: a machine-side transition counter (the PackML machine
        # flips intermediate states synchronously — polling the STATE misses
        # the flashes, a counter cannot)
        self.transition_counter = transition_counter or (lambda: -1)
        self.slow_interval = slow_interval
        # shared parameter state: BOTH bindings (UA write hook + the MQTT
        # parameter command callback) back the SAME effective value
        self._parameter_state = parameter_state if parameter_state is not None \
            else {"value": PARAMETER_DEFAULT}
        self._parameter_lock = parameter_lock or threading.Lock()

        self.namespace_index = EXPECTED_NAMESPACE_INDEX
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready = threading.Event()
        self._stopped: Optional[asyncio.Event] = None

    @property
    def parameter(self) -> float:
        """The effective parameter value, shared across both bindings."""
        with self._parameter_lock:
            return float(self._parameter_state.get("value", PARAMETER_DEFAULT))

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the server thread; returns once the endpoint accepts
        connections (or raises after a 15 s timeout)."""
        if self._thread is not None:
            return
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._thread_main, name="OpcuaServer", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise RuntimeError(f"OPC UA server did not start within 15 s "
                               f"({self.endpoint})")
        logger.info("OPC UA server serving on %s (ns=%d, skills=%s)",
                    self.endpoint, self.namespace_index, self.skills)

    def stop(self) -> None:
        if self._loop is not None and self._stopped is not None:
            self._loop.call_soon_threadsafe(self._stopped.set)
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._thread = None
        self._loop = None

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        except Exception as exc:  # noqa: BLE001 - surface server crashes
            logger.error("OPC UA server loop crashed: %s", exc)

    def request_task_stack_dump(self) -> None:
        """Thread-safe: schedules a dump of all asyncio task stacks on the
        server loop (SIGUSR2 diagnostic; the signal handler lives in the
        main thread — signal.signal is main-thread-only)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def _dump() -> None:
            print("==== asyncio task stacks ====", file=sys.stderr)
            for task in asyncio.all_tasks():
                print(f"--- {task.get_name()} done={task.done()}", file=sys.stderr)
                task.print_stack(file=sys.stderr)
            print("==== end task stacks ====", file=sys.stderr)

        loop.call_soon_threadsafe(_dump)

    async def _run(self) -> None:
        server = Server()
        await server.init()
        server.set_endpoint(self.endpoint)
        self.namespace_index = await server.register_namespace(self.namespace_uri)
        if self.namespace_index != EXPECTED_NAMESPACE_INDEX:
            logger.error(
                "OPC UA namespace index is %d, not %d — the AID authors "
                "ns=%d NodeIds; the address space will not match the "
                "authored config", self.namespace_index,
                EXPECTED_NAMESPACE_INDEX, EXPECTED_NAMESPACE_INDEX)
        await self._build_address_space(server)

        self._stopped = asyncio.Event()
        try:
            async with server:
                self._ready.set()
                await self._stopped.wait()
        finally:
            for task in getattr(self, "_tasks", []):
                task.cancel()
            await asyncio.gather(*getattr(self, "_tasks", []),
                                 return_exceptions=True)
            logger.info("OPC UA server stopped")

    # ── address space ─────────────────────────────────────────────────────

    async def _build_address_space(self, server: Server) -> None:
        idx = self.namespace_index
        objects = server.nodes.objects

        station = await objects.add_object(
            ua.NodeId("Station", idx, ua.NodeIdType.String),
            f"{idx}:Station")

        state = await station.add_variable(
            ua.NodeId("StationState", idx, ua.NodeIdType.String),
            f"{idx}:StationState", self.state_provider(),
            ua.VariantType.String)
        await state.set_writable(False)
        self._station_state_var = state

        for skill in self.skills:
            skill_obj = await objects.add_object(
                ua.NodeId(skill, idx, ua.NodeIdType.String), f"{idx}:{skill}")
            await skill_obj.add_method(
                ua.NodeId(f"{skill}Method", idx, ua.NodeIdType.String),
                f"{idx}:{skill}Method",
                self._make_method_callback(skill),
                [self._command_argument()],
                [self._output_argument("State", ua.VariantType.String),
                 self._output_argument("Outcome", ua.VariantType.Int32)])

        # Event-mode stream: updated ONLY on PackML state transitions.
        self._measurement_fast = await objects.add_variable(
            ua.NodeId("MeasurementFast", idx, ua.NodeIdType.String),
            f"{idx}:MeasurementFast", 0.0, ua.VariantType.Double)
        # Timer-mode stream: a slowly varying simulated process value.
        self._measurement_slow = await objects.add_variable(
            ua.NodeId("MeasurementSlow", idx, ua.NodeIdType.String),
            f"{idx}:MeasurementSlow", self._slow_value(time.time()),
            ua.VariantType.Double)

        parameter = await objects.add_variable(
            ua.NodeId("Parameter", idx, ua.NodeIdType.String),
            f"{idx}:Parameter", self.parameter, ua.VariantType.Double)
        await parameter.set_writable(True)
        server.iserver.set_attribute_value_setter(
            parameter.nodeid, ua.AttributeIds.Value, self._parameter_setter)
        self._parameter_var = parameter

        # The terminal reply of the LAST invoked skill method, as a JSON blob
        # {"Uuid", "State", "Outcome"}. camel-milo's method-call path drops
        # the CallMethodResult (upstream SubscriptionManager lambda), so the
        # DMP reads the reply back from here; the caller-facing response is
        # rebuilt from this node (the DMP UA surface contract).
        self._method_reply = await objects.add_variable(
            ua.NodeId("MethodReply", idx, ua.NodeIdType.String),
            f"{idx}:MethodReply", "", ua.VariantType.String)

        self._transition_counter = 0
        self._last_state = self.state_provider()
        self._last_transition_count = -1
        self._tasks = [
            asyncio.create_task(self._fast_measurement_loop()),
            asyncio.create_task(self._slow_measurement_loop()),
        ]

    @staticmethod
    def _command_argument() -> ua.Argument:
        """The single InputArgument: the JSON command blob the DMP's
        milo-client Call rides as one String variant (mapCallValue)."""
        arg = ua.Argument()
        arg.Name = "Command"
        arg.DataType = ua.NodeId(ua.ObjectIds.String)
        arg.ValueRank = -1
        return arg

    @staticmethod
    def _output_argument(name: str, variant_type) -> ua.Argument:
        arg = ua.Argument()
        arg.Name = name
        arg.DataType = ua.NodeId(getattr(ua.ObjectIds,
                                         {"String": "String",
                                          "Int32": "Int32"}[variant_type.name]))
        arg.ValueRank = -1
        return arg

    def _make_method_callback(self, skill: str):
        async def invoke(parent, command_value=None):
            command_uuid = self._uuid_from_command(command_value)
            if not command_uuid:
                command_uuid = str(uuid_module.uuid4())
            command_uuid = str(command_uuid)
            logger.debug("UA method %sMethod invoked (Uuid=%s)",
                        skill, command_uuid)
            loop = asyncio.get_running_loop()
            reply = await loop.run_in_executor(
                None, self._invoke_skill, skill, command_uuid)
            state = str(reply.get("State", "FAILURE"))
            try:
                outcome = int(reply.get("Outcome", 0))
            except (TypeError, ValueError):
                outcome = 0
            # publish the terminal reply for the DMP's read-back
            try:
                blob = json.dumps({"Uuid": command_uuid, "State": state,
                                   "Outcome": outcome})
                await self._method_reply.write_value(
                    ua.Variant(blob, ua.VariantType.String))
            except Exception as exc:  # noqa: BLE001 - reply node write is best effort
                logger.error("method reply write failed: %s", exc)
            return [ua.Variant(state, ua.VariantType.String),
                    ua.Variant(outcome, ua.VariantType.Int32)]
        return invoke

    @staticmethod
    def _uuid_from_command(command_value) -> Optional[str]:
        """The correlation Uuid from the invoked method argument: either the
        JSON command blob ``{"Uuid": "..."}`` (the DMP's milo-client Call
        body) or a bare Uuid string (a plain UA client)."""
        if isinstance(command_value, ua.Variant):
            command_value = command_value.Value
        if not isinstance(command_value, str):
            return None
        text = command_value.strip()
        if not text:
            return None
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return text
            if isinstance(parsed, dict):
                uuid_value = parsed.get("Uuid") or parsed.get("uuid")
                return str(uuid_value) if uuid_value else None
        return text

    def _invoke_skill(self, skill: str, command_uuid: str) -> Dict:
        if self.skill_handler is None:
            return {"State": "FAILURE", "Outcome": 0}
        try:
            reply = self.skill_handler(skill, command_uuid) or \
                {"State": "FAILURE", "Outcome": 0}
            logger.debug("skill %s (Uuid=%s) -> %s", skill, command_uuid,
                        reply.get("State"))
            return reply
        except Exception as exc:  # noqa: BLE001 - skill logic must not crash the server
            logger.exception("skill %s (Uuid=%s) failed", skill, command_uuid)
            return {"State": "FAILURE", "Outcome": 0}

    # ── variables ─────────────────────────────────────────────────────────

    @staticmethod
    def _slow_value(now: float) -> float:
        return round(40.0 + 10.0 * math.sin(
            2 * math.pi * (now % SLOW_MEASUREMENT_PERIOD_S) /
            SLOW_MEASUREMENT_PERIOD_S), 3)

    async def _slow_measurement_loop(self) -> None:
        try:
            while True:
                try:
                    value = self._slow_value(time.time())
                    logger.debug("slow loop writing %s", value)
                    await self._measurement_slow.write_value(
                        ua.Variant(value, ua.VariantType.Double))
                    logger.debug("slow loop wrote %s", value)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.error("slow measurement update failed: %s", exc)
                await asyncio.sleep(self.slow_interval)
        except asyncio.CancelledError:
            logger.debug("slow measurement loop cancelled")
            raise
        except BaseException as exc:  # noqa: BLE001 - make silent deaths loud
            logger.exception("slow measurement loop DIED: %r", exc)
            raise

    async def _fast_measurement_loop(self) -> None:
        while True:
            try:
                count = self.transition_counter()
                if count >= 0 and count != self._last_transition_count:
                    self._last_transition_count = count
                    state = self.state_provider()
                    self._transition_counter = count
                    await self._measurement_fast.write_value(
                        ua.Variant(float(count), ua.VariantType.Double))
                    await self._station_state_var.write_value(
                        ua.Variant(state, ua.VariantType.String))
                    logger.debug("transition %d -> state %s", count, state)
                else:
                    state = self.state_provider()
                    if state != self._last_state:
                        self._last_state = state
                        self._transition_counter += 1
                        await self._measurement_fast.write_value(
                            ua.Variant(float(self._transition_counter),
                                       ua.VariantType.Double))
                        await self._station_state_var.write_value(
                            ua.Variant(state, ua.VariantType.String))
                        logger.debug("transition %d -> state %s",
                                    self._transition_counter, state)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("fast measurement update failed: %s", exc)
            await asyncio.sleep(0.1)

    def _parameter_setter(self, node, attr, value: ua.DataValue) -> None:
        """Server-side write hook for the Parameter variable: store the
        value, run the parameter logic and acknowledge (the UA write status
        is the ack; read-back returns the effective value). An out-of-range
        write is REJECTED: not stored, so read-back keeps the previous
        effective value."""
        try:
            written = value.Value.Value if value.Value is not None else None
        except AttributeError:
            written = None
        if isinstance(written, (int, float)) and \
                PARAMETER_MIN <= float(written) <= PARAMETER_MAX:
            with self._parameter_lock:
                self._parameter_state["value"] = float(written)
            logger.info("Parameter write acknowledged: %s (effective %s)",
                        written, self.parameter)
            node.value = value
        else:
            logger.error("Parameter write REJECTED: %s outside [%s, %s]; "
                         "read-back keeps the previous value",
                         written, PARAMETER_MIN, PARAMETER_MAX)

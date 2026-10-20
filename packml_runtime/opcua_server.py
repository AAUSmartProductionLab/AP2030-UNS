"""OPC UA native interface of a PackML station (asyncua).

Runs an ``asyncua.Server`` on its own asyncio loop in a daemon thread and
builds the address space that aas-model's ``OperationalOpcuaInterfaces``
describes:

- the ``Station`` Object (``ns=2;s=Station``) with the read-only variables
  ``Station.State`` (String, the PackML state) and ``Station.ProcessQueue``
  (String[], the occupation queue), plus any station variables (e.g.
  ``Station.Weight``);
- one Method per skill, ``ns=2;s=Station.<Skill>``, owned by ``Station``
  (OPC 10101 §7.1.3). Its InputArguments are the members of the command
  schema by name (``Uuid``, and e.g. ``Volume``); its OutputArguments are
  the commandResponse members ``Uuid``, ``State``, ``Outcome`` and
  ``TimeStamp``, or none for an invoke-only skill (Halt). A Call returns once
  the skill has finished.

A skill can run for seconds. asyncua serves a connection's requests one after
another, and the DMP's client shares one connection between its Calls and its
subscriptions, so a running Call would hold back the Publish requests (the
live values, e.g. the weight while dispensing) and the keepalive reads. The
server therefore answers each Call from its own task; OPC UA matches
responses to requests by id, so they may arrive out of order.

The first custom namespace is expected to be index 2 (the AID authors
``ns=2;s=...`` NodeIds); a deviation is logged loudly.
"""

import asyncio
import datetime
import logging
import sys
import threading
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple

from asyncua import Server, ua
from asyncua.server.uaprocessor import UaProcessor

from .simulator import PackMLState, Replies

logger = logging.getLogger("packml_runtime.opcua")

#: The AID authors ``ns=2;s=...`` NodeIds (one registered custom namespace).
EXPECTED_NAMESPACE_INDEX = 2

#: The Object owning the PackML Methods and variables.
STATION = "Station"

#: InputArguments of a plain command (command.schema.json).
COMMAND_ARGUMENTS = (("Uuid", ua.VariantType.String),)

#: OutputArguments of every skill (commandResponse.schema.json).
REPLY_ARGUMENTS = (
    ("Uuid", ua.VariantType.String),
    ("State", ua.VariantType.String),
    ("Outcome", ua.VariantType.Int32),
    ("TimeStamp", ua.VariantType.String),
)

#: How long a Method waits for the skill's terminal reply — below the DMP's
#: 30 s call timeout, so the caller gets the station's FAILURE, not a timeout.
SKILL_REPLY_TIMEOUT_S = 25.0

Arguments = Sequence[Tuple[str, ua.VariantType]]


def timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def reply(command_uuid: str, state: str) -> Dict:
    return {"Uuid": command_uuid, "State": state, "Outcome": 0, "TimeStamp": timestamp()}


_CALL_REQUEST = ua.NodeId(ua.ObjectIds.CallRequest_Encoding_DefaultBinary)
_calls_in_flight = set()


def _answer_calls_concurrently() -> None:
    """Patch asyncua (2.0.1) so a Call does not block its connection; see
    the module docstring. Errors are answered as ``process_message`` would."""
    process = UaProcessor._process_message
    if getattr(process, "concurrent_calls", False):
        return

    async def _process_message(self, typeid, requesthdr, seqhdr, body):
        if typeid != _CALL_REQUEST or self.session is None:
            return await process(self, typeid, requesthdr, seqhdr, body)

        async def answer():
            try:
                await process(self, typeid, requesthdr, seqhdr, body)
            except Exception as exc:  # noqa: BLE001 - answered as a ServiceFault
                logger.exception("Call failed")
                code = getattr(exc, "code", ua.StatusCodes.BadInternalError)
                response = ua.ServiceFault()
                response.ResponseHeader.ServiceResult = ua.StatusCode(code)
                self.send_response(requesthdr.RequestHandle, seqhdr, response)

        task = asyncio.create_task(answer())
        _calls_in_flight.add(task)
        task.add_done_callback(_calls_in_flight.discard)
        return True

    _process_message.concurrent_calls = True
    UaProcessor._process_message = _process_message


class StationOpcuaServer:
    """asyncua server exposing a station's skills and variables.

    ``skills`` maps each skill to its InputArguments; invocations are
    delegated to ``skill_handler(skill, arguments) -> reply`` with the
    arguments by name. A skill in ``invoke_only`` has no OutputArguments:
    its Method answers nothing, whatever the handler returns. ``variables`` maps each station variable to its
    initial value and type. The server is also the PackML machine's state
    sink: ``publish`` writes ``State`` and ``ProcessQueue``.
    """

    def __init__(
        self,
        endpoint: str,
        skills: Mapping[str, Arguments],
        skill_handler: Callable[[str, Dict], Dict],
        variables: Optional[Mapping[str, Tuple[object, ua.VariantType]]] = None,
        namespace_uri: str = "https://aausmartproductionlab.github.io/AP2030-UNS/Station",
        invoke_only: Sequence[str] = (),
    ):
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.skills = dict(skills)
        self.invoke_only = frozenset(invoke_only)
        self.skill_handler = skill_handler
        self._values = {"State": PackMLState.IDLE.value, "ProcessQueue": []}
        self._types = {"State": ua.VariantType.String, "ProcessQueue": ua.VariantType.String}
        for name, (value, variant_type) in (variables or {}).items():
            self._values[name] = value
            self._types[name] = variant_type
        self._nodes: Dict = {}

        self.namespace_index = EXPECTED_NAMESPACE_INDEX
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready = threading.Event()
        self._stopped: Optional[asyncio.Event] = None

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
                    self.endpoint, self.namespace_index, list(self.skills))

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
        _answer_calls_concurrently()
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
        async with server:
            self._ready.set()
            await self._stopped.wait()
        logger.info("OPC UA server stopped")

    # ── address space ─────────────────────────────────────────────────────

    def _node_id(self, name: str) -> ua.NodeId:
        return ua.NodeId(name, self.namespace_index, ua.NodeIdType.String)

    async def _build_address_space(self, server: Server) -> None:
        idx = self.namespace_index
        station = await server.nodes.objects.add_object(self._node_id(STATION), f"{idx}:{STATION}")

        for name, value in self._values.items():
            variant = ua.Variant(value, self._types[name])
            node = await station.add_variable(
                self._node_id(f"{STATION}.{name}"), f"{idx}:{name}", variant)
            if variant.is_array:
                # asyncua leaves a 1-D array's ValueRank unset
                await node.write_value_rank(ua.ValueRank.OneDimension)
                await node.write_array_dimensions([0])
            self._nodes[name] = node

        for skill, inputs in self.skills.items():
            outputs = () if skill in self.invoke_only else REPLY_ARGUMENTS
            await station.add_method(
                self._node_id(f"{STATION}.{skill}"), f"{idx}:{skill}",
                self._method(skill, inputs),
                [_argument(name, variant_type) for name, variant_type in inputs],
                [_argument(name, variant_type) for name, variant_type in outputs])

    def _method(self, skill: str, inputs: Arguments):
        async def invoke(parent, *values):
            arguments = {
                name: value.Value if isinstance(value, ua.Variant) else value
                for (name, _), value in zip(inputs, values)
            }
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._invoke, skill, arguments)
            if skill in self.invoke_only:
                return []
            command_uuid = str(result.get("Uuid") or arguments.get("Uuid") or "")
            try:
                outcome = int(result.get("Outcome", 0))
            except (TypeError, ValueError):
                outcome = 0
            return [
                ua.Variant(command_uuid, ua.VariantType.String),
                ua.Variant(str(result.get("State", "FAILURE")), ua.VariantType.String),
                ua.Variant(outcome, ua.VariantType.Int32),
                ua.Variant(str(result.get("TimeStamp") or timestamp()), ua.VariantType.String),
            ]
        return invoke

    def _invoke(self, skill: str, arguments: Dict) -> Dict:
        command_uuid = str(arguments.get("Uuid") or "")
        try:
            result = self.skill_handler(skill, arguments) or reply(command_uuid, "FAILURE")
            logger.info("skill %s %s -> %s", skill, arguments, result.get("State"))
            return result
        except ValueError as rejected:  # an argument the skill does not accept
            logger.warning("skill %s %s rejected: %s", skill, arguments, rejected)
            return reply(command_uuid, "FAILURE")
        except Exception:  # noqa: BLE001 - skill logic must not crash the server
            logger.exception("skill %s %s failed", skill, arguments)
            return reply(command_uuid, "FAILURE")

    # ── variables ─────────────────────────────────────────────────────────

    def write(self, name: str, value) -> None:
        """Thread-safe write of a station variable."""
        self._values[name] = value
        loop, node = self._loop, self._nodes.get(name)
        if loop is None or node is None or not self._ready.is_set():
            return  # the value is the initial one when the node is built
        future = asyncio.run_coroutine_threadsafe(
            node.write_value(ua.Variant(value, self._types[name])), loop)
        if threading.current_thread() is not self._thread:
            future.result(timeout=5)  # keep writes in order

    def publish(self, message, client=None, retain=False) -> None:
        """PackML state sink: the machine's state message to its variables."""
        self.write("ProcessQueue", [str(item) for item in message.get("ProcessQueue", [])])
        self.write("State", str(message["State"]))


def _argument(name: str, variant_type: ua.VariantType) -> ua.Argument:
    argument = ua.Argument()
    argument.Name = name
    argument.DataType = ua.NodeId(getattr(ua.ObjectIds, variant_type.name))
    argument.ValueRank = ua.ValueRank.Scalar
    return argument


def packml_skill_handler(machine, processes: Mapping[str, Callable[[Dict], Tuple]],
                         timeout: float = SKILL_REPLY_TIMEOUT_S):
    """The OPC UA skill logic of a PackML station with a ``state_sink``:
    Halt, Occupy and Release on the machine, and each process skill of
    ``processes``, which maps the Method arguments to ``(process_function,
    *args)`` for ``machine.execute_command``. Each returns the terminal
    reply."""

    def handle(skill: str, arguments: Dict) -> Dict:
        command_uuid = str(arguments.get("Uuid") or "")
        if not command_uuid:
            return reply(command_uuid, "FAILURE")
        if skill == "Halt":
            if machine.is_processing:
                # interrupt the active process: ABORTING -> ABORTED
                machine.abort_command()
            return reply(command_uuid, "SUCCESS")
        if skill == "Occupy":
            wait = machine.register_topic.expect(command_uuid)
            machine.register_command(command_uuid)
            result = wait(timeout)
            if result is None:
                # still queued behind another occupant: withdraw the request
                machine.unregister_command(command_uuid)
            return result or reply(command_uuid, "FAILURE")
        if skill == "Release":
            wait = machine.unregister_topic.expect(command_uuid)
            machine.unregister_command(command_uuid)
            return wait(timeout) or reply(command_uuid, "FAILURE")
        if skill in processes:
            replies = Replies()
            wait = replies.expect(command_uuid)
            function, *process_args = processes[skill](arguments)
            machine.execute_command({"Uuid": command_uuid}, replies, function, *process_args)
            return wait(timeout) or reply(command_uuid, "FAILURE")
        return reply(command_uuid, "FAILURE")

    return handle

"""Simulated IMA dispensing station — OPC UA only.

Its native interface is the OPC UA server that aas-model's ``ima_dispensing``
AID describes (``ns=2;s=Station``):

==================  =================  ================================
Method              InputArguments     OutputArguments
==================  =================  ================================
Station.Occupy      Uuid               Uuid, State, Outcome, TimeStamp
Station.Release     Uuid               Uuid, State, Outcome, TimeStamp
Station.Halt        Uuid               (none: Halt only invokes)
Station.Dispensing  Uuid, Volume (ml)  Uuid, State, Outcome, TimeStamp
==================  =================  ================================

Variables: ``Station.State`` (PackML), ``Station.ProcessQueue`` (occupation
queue) and ``Station.Weight`` (g), which follows the fill at 10 Hz while
Dispensing runs. A Method returns when its skill has finished. As over MQTT,
Dispensing runs for the Uuid that occupies the station.

MQTT is used only to publish the station's description to the registration
service: the ``ima_dispensing`` Resource, with the AID base set to where this
server is reachable (``OPCUA_ADVERTISED_ENDPOINT``).
"""

import logging
import math
import os
import random
import signal
import time

from asyncua import ua

from packml_runtime.mqtt import Proxy
from packml_runtime.opcua_server import COMMAND_ARGUMENTS, StationOpcuaServer, packml_skill_handler
from packml_runtime.simulator import PackMLStateMachine
from services.stations.simple_station import BROKER_ADDRESS, BROKER_PORT, load_resource

# Halt only invokes, as the resource describes it: its Method has no OutputArguments.
INVOKE_ONLY_SKILLS = ("Halt",)
OPCUA_ENDPOINT = os.getenv("OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/dispensing/")
OPCUA_ADVERTISED_ENDPOINT = os.getenv(
    "OPCUA_ADVERTISED_ENDPOINT", "opc.tcp://dispensing-station:4840/dispensing/")

FLOW_RATE_ML_S = 1.0
DENSITY_G_ML = 1.0
#: Larger volumes would outlast the Method's reply timeout.
MAX_VOLUME_ML = 20.0
SAMPLE_PERIOD_S = 0.1


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    def dispense(interrupt_event, volume):
        """Fill ``volume`` ml into a fresh container on the tared scale: the
        weight rises as a first-order lag and settles at the dispensed mass."""
        duration = max(0.5, volume / FLOW_RATE_ML_S)
        dispensed = volume * DENSITY_G_ML * random.gauss(1.0, 0.01)
        server.write("Weight", 0.0)
        started = time.monotonic()
        while (elapsed := time.monotonic() - started) < duration:
            if interrupt_event.wait(SAMPLE_PERIOD_S):
                return {"State": "FAILURE"}
            reading = dispensed * (1.0 - math.exp(-5.0 * elapsed / duration))
            server.write("Weight", round(max(0.0, reading + random.gauss(0.0, 0.002)), 4))
        server.write("Weight", round(dispensed, 4))

    def dispensing(arguments):
        volume = float(arguments["Volume"])
        if not 0.0 < volume <= MAX_VOLUME_ML:
            raise ValueError(f"Volume {volume} ml is outside (0, {MAX_VOLUME_ML}]")
        return dispense, volume

    handler = None
    server = StationOpcuaServer(
        endpoint=OPCUA_ENDPOINT,
        skills={
            "Halt": COMMAND_ARGUMENTS,
            "Occupy": COMMAND_ARGUMENTS,
            "Release": COMMAND_ARGUMENTS,
            "Dispensing": COMMAND_ARGUMENTS + (("Volume", ua.VariantType.Double),),
        },
        skill_handler=lambda skill, arguments: handler(skill, arguments),
        variables={"Weight": (0.0, ua.VariantType.Double)},
        namespace_uri="https://aausmartproductionlab.github.io/AP2030-UNS/Dispensing",
        invoke_only=INVOKE_ONLY_SKILLS,
    )
    server.start()
    signal.signal(signal.SIGUSR2, lambda signum, frame: server.request_task_stack_dump())

    resource = load_resource("imaDispensingSystemAAS", "InterfaceTemplateForOPCUA", OPCUA_ADVERTISED_ENDPOINT)

    proxy = Proxy(BROKER_ADDRESS, BROKER_PORT, "DispensingProxy", [])
    machine = PackMLStateMachine(None, proxy, None, state_sink=server, resource=resource)
    handler = packml_skill_handler(machine, {"Dispensing": dispensing})

    proxy.on_ready(machine.register_asset)
    proxy.loop_forever()


if __name__ == "__main__":
    main()

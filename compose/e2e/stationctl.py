#!/usr/bin/env python3
"""Drive the e2e stations by hand and watch what the DMP does with them.

Run after ``compose/e2e/bootstrap.sh``. Stations:

  stoppering   syntegonStopperingSystemAAS  MQTT only   skill Stoppering
  dispensing   imaDispensingSystemAAS       OPC UA only skill Dispensing (--volume ml)

Commands:

  status                     DMP convergence and every station's AAS variables
  call STATION SKILL         invoke a skill Operation (Occupy, Release, Halt, …)
  run STATION                Occupy -> process skill -> Release with one Uuid
  watch [STATION]            print AAS variable changes as the DMP writes them
  device STATION             the station's own native values (bypasses the DMP)
  reset stoppering           PackML Reset over MQTT (after a Halt/Abort)

``call``/``run`` invoke the AAS Operation on the repository, which delegates
to the DMP (the real path); ``--direct`` posts to the DMP's endpoint instead.

Examples:

  python3 compose/e2e/stationctl.py watch &                 # in a second terminal
  python3 compose/e2e/stationctl.py call dispensing Occupy --uuid job-1
  python3 compose/e2e/stationctl.py call dispensing Dispensing --uuid job-1 --volume 5
  python3 compose/e2e/stationctl.py call dispensing Release --uuid job-1
  python3 compose/e2e/stationctl.py run stoppering
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import uuid

import requests

AAS = f"http://localhost:{os.getenv('E2E_AAS_PORT', '18081')}"
DMP = f"http://localhost:{os.getenv('E2E_DMP_PORT', '18086')}"
MQTT_PORT = int(os.getenv("E2E_MQTT_PORT", "18830"))
UA_ENDPOINT = os.getenv("E2E_UA_ENDPOINT", "opc.tcp://localhost:4840/dispensing/")
BASE_URL = "https://smartproductionlab.aau.dk/aas"

STATIONS = {
    "stoppering": {"aas": "syntegonStopperingSystemAAS", "skill": "Stoppering",
                   "topic": "NN/Nybrovej/InnoLab/Stoppering", "variables": ("PackMLState", "OccupationState")},
    "dispensing": {"aas": "imaDispensingSystemAAS", "skill": "Dispensing",
                   "variables": ("PackMLState", "OccupationState", "Weight")},
}


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


#: Skills that only invoke (aas-model ``INVOKE_ONLY_SKILLS``).
INVOKE_ONLY = ("Halt",)


def _submodel(station: str, name: str) -> str:
    return f"{AAS}/submodels/{_b64(f'{BASE_URL}/{STATIONS[station]['aas']}/submodels/{name}')}"


def variables(station: str) -> dict:
    values = {}
    for name in STATIONS[station]["variables"]:
        response = requests.get(f"{_submodel(station, 'Variables')}/submodel-elements/{name}", timeout=5)
        values[name] = response.json().get("value") if response.ok else f"<{response.status_code}>"
    return values


def _property(name: str, value, value_type: str) -> dict:
    return {"value": {"modelType": "Property", "idShort": name, "valueType": value_type, "value": str(value)}}


def call(station: str, skill: str, command_uuid: str, volume: float | None, direct: bool) -> dict:
    inputs = [_property("Volume", volume, "xs:double")] if volume is not None else []
    inouts = [_property("Uuid", command_uuid, "xs:string")]
    if skill in INVOKE_ONLY:  # no outputs: the Uuid is only an input, and the reply is empty
        inputs, inouts = inputs + inouts, []
    started = time.monotonic()
    if direct:
        response = requests.post(f"{DMP}/operations/{STATIONS[station]['aas']}/{skill}",
                                 json=inputs + inouts, timeout=60)
        body = response.json() if response.content else None
        reply = ({v["value"]["idShort"]: v["value"].get("value") for v in body}
                 if response.ok and isinstance(body, list) else body)
    else:
        response = requests.post(
            f"{_submodel(station, 'ControlComponentInstance')}/submodel-elements/Skills.{skill}.operation/invoke",
            json={"inputArguments": inputs, "inoutputArguments": inouts, "clientTimeoutDuration": "PT60S"},
            timeout=60)
        body = response.json() if response.content else None
        reply = body
        if response.ok and isinstance(body, dict):
            reply = {v["value"]["idShort"]: v["value"].get("value")
                     for v in body.get("outputArguments", []) + body.get("inoutputArguments", [])}
            if not body.get("success", True):
                reply["executionState"] = body.get("executionState")
                reply["messages"] = body.get("messages")
    elapsed = time.monotonic() - started
    print(f"{station} {skill} [{'DMP' if direct else 'AAS'}] -> HTTP {response.status_code} "
          f"in {elapsed:.1f}s: {json.dumps(reply)}")
    return reply if isinstance(reply, dict) else {}


def status(_args) -> None:
    try:
        dmp = requests.get(f"{DMP}/management/status", timeout=5).json()
        summary = {k: v for k, v in dmp.items() if not isinstance(v, (list, dict))}
        print("DMP:", json.dumps(summary))
        for key, value in dmp.items():
            if isinstance(value, list) and value and key.lower().startswith(("blocked", "fail", "issue")):
                print(f"  {key}:", json.dumps(value, indent=2)[:2000])
    except requests.RequestException as error:
        print("DMP unreachable:", error)
    for station in STATIONS:
        print(f"{station}:", json.dumps(variables(station)))


def watch(args) -> None:
    stations = [args.station] if args.station else list(STATIONS)
    last: dict = {}
    print("watching AAS Variables (Ctrl-C to stop)")
    while True:
        for station in stations:
            for name, value in variables(station).items():
                if last.get((station, name)) != value:
                    last[(station, name)] = value
                    print(f"{time.strftime('%H:%M:%S')} {station:10s} {name:15s} {value}", flush=True)
        time.sleep(0.1)


def device(args) -> None:
    if args.station == "stoppering":
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        client.on_message = lambda c, u, m: print(
            f"{time.strftime('%H:%M:%S')} {m.topic.rsplit('/', 2)[-2:]} {m.payload.decode()}"
            + (" [correlated]" if getattr(m.properties, "CorrelationData", None) else ""), flush=True)
        client.connect("localhost", MQTT_PORT)
        client.subscribe(f"{STATIONS['stoppering']['topic']}/#", qos=2)
        print("native MQTT traffic of the stoppering station (Ctrl-C to stop)")
        client.loop_forever()
    else:
        from asyncua.sync import Client

        class Printer:
            def datachange_notification(self, node, value, data):
                print(f"{time.strftime('%H:%M:%S')} {node.nodeid.Identifier:22s} {value}", flush=True)

        with Client(UA_ENDPOINT) as client:
            subscription = client.create_subscription(100, Printer())
            subscription.subscribe_data_change([client.get_node(f"ns=2;s=Station.{n}")
                                                for n in ("State", "ProcessQueue", "Weight")])
            print("native OPC UA values of the dispensing station (Ctrl-C to stop)")
            while True:
                time.sleep(1)


def run(args) -> None:
    command_uuid = args.uuid or str(uuid.uuid4())
    skill = STATIONS[args.station]["skill"]
    volume = args.volume if args.station == "dispensing" else None
    for step, step_volume in (("Occupy", None), (skill, volume), ("Release", None)):
        reply = call(args.station, step, command_uuid, step_volume, args.direct)
        if reply.get("State") != "SUCCESS":
            print(f"stopping: {step} did not succeed")
            return
    time.sleep(1.0)  # the DMP writes the final state shortly after the reply
    print(f"{args.station}:", json.dumps(variables(args.station)))


def reset(args) -> None:
    import paho.mqtt.client as mqtt
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.connect("localhost", MQTT_PORT)
    client.loop_start()
    client.publish(f"{STATIONS['stoppering']['topic']}/CMD/State", json.dumps({
        "StateId": "Reset", "Uuid": str(uuid.uuid4()),
        "TimeStamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), qos=2).wait_for_publish()
    client.loop_stop()
    print("Reset sent to the stoppering station")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status").set_defaults(handler=status)
    p = commands.add_parser("call")
    p.add_argument("station", choices=STATIONS)
    p.add_argument("skill")
    p.add_argument("--uuid", default=None)
    p.add_argument("--volume", type=float, default=None, help="Dispensing volume in ml")
    p.add_argument("--direct", action="store_true", help="post to the DMP instead of the AAS Operation")
    p.set_defaults(handler=lambda a: call(a.station, a.skill, a.uuid or str(uuid.uuid4()), a.volume, a.direct))
    p = commands.add_parser("run")
    p.add_argument("station", choices=STATIONS)
    p.add_argument("--uuid", default=None)
    p.add_argument("--volume", type=float, default=5.0, help="Dispensing volume in ml")
    p.add_argument("--direct", action="store_true")
    p.set_defaults(handler=run)
    p = commands.add_parser("watch")
    p.add_argument("station", nargs="?", choices=STATIONS)
    p.set_defaults(handler=watch)
    p = commands.add_parser("device")
    p.add_argument("station", choices=STATIONS)
    p.set_defaults(handler=device)
    p = commands.add_parser("reset")
    p.add_argument("station", choices=["stoppering"])
    p.set_defaults(handler=reset)
    args = parser.parse_args()
    try:
        args.handler(args)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())

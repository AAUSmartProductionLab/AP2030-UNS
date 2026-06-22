"""
Test script for sending MQTT commands to the XBot Planar Controller.

Topic structure:
  System commands : NN/Nybrovej/InnoLab/Planar/CMD/Command
  XBot motion     : NN/Nybrovej/InnoLab/Planar/Xbot{N}/CMD/XYMotion
  State feedback  : NN/Nybrovej/InnoLab/Planar/DATA/State
  XBot feedback   : NN/Nybrovej/InnoLab/Planar/Xbot{N}/DATA/State
"""

import json
import time
import uuid
import os
import paho.mqtt.client as mqtt

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT   = int(os.environ.get("MQTT_PORT", 1883))
BASE_TOPIC  = "NN/Nybrovej/InnoLab/Planar"

# ── helpers ──────────────────────────────────────────────────────────────────

def make_client() -> mqtt.Client:
    client = mqtt.Client()

    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
            # Subscribe to all feedback topics so we can see state changes
            c.subscribe(f"{BASE_TOPIC}/DATA/State", qos=1)
            c.subscribe(f"{BASE_TOPIC}/DATA/ButtonStates", qos=1)
            for xbot_id in range(1, 10):
                c.subscribe(f"{BASE_TOPIC}/Xbot{xbot_id}/DATA/State", qos=1)
            print("[MQTT] Subscribed to all feedback topics\n")
        else:
            print(f"[MQTT] Connection failed (rc={rc})")

    def on_message(c, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            print(f"  << {msg.topic}: {json.dumps(payload)}")
        except Exception:
            print(f"  << {msg.topic}: {msg.payload}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    time.sleep(1)  # Wait for connection
    return client


def send_command(client: mqtt.Client, button_id: str):
    """Send a PackML system command (Start / Stop / Hold / UnHold / Reset / Clear)."""
    topic   = f"{BASE_TOPIC}/CMD/Command"
    payload = {"ButtonId": button_id}
    client.publish(topic, json.dumps(payload), qos=1)
    print(f"  >> {topic}: {payload}")


def send_motion(client: mqtt.Client, xbot_id: int, x: float, y: float,
                rotation_deg: float = None, task_uuid: str = None):
    """
    Send an XY motion command (and optional rotation) to an XBot.

    Args:
        xbot_id      : XBot number (1-9)
        x, y         : Target position in metres
        rotation_deg : Optional target heading in degrees (0 = default orientation)
        task_uuid    : UUID string for tracking; auto-generated if omitted
    """
    topic = f"{BASE_TOPIC}/Xbot{xbot_id}/CMD/XYMotion"
    position = [x, y] if rotation_deg is None else [x, y, rotation_deg]
    payload  = {
        "Uuid"    : task_uuid or str(uuid.uuid4()),
        "Position": position,
    }
    client.publish(topic, json.dumps(payload), qos=1)
    print(f"  >> {topic}: {payload}")


# ── test scenarios ────────────────────────────────────────────────────────────

def test_start_stop(client: mqtt.Client):
    """Start the system then immediately stop it."""
    print("\n=== Test: Start → Stop ===")
    send_command(client, "Start")
    time.sleep(2)
    send_command(client, "Stop")
    time.sleep(2)
    send_command(client, "Reset")
    time.sleep(1)


def test_single_move(client: mqtt.Client, xbot_id: int = 1,
                     x: float = 0.36, y: float = 0.36):
    """Start the system, move one XBot to a position, then stop."""
    print(f"\n=== Test: Move XBot {xbot_id} to ({x:.3f}, {y:.3f}) ===")
    send_command(client, "Start")
    time.sleep(1.5)
    send_motion(client, xbot_id, x, y)
    print("  Waiting for completion (up to 30 s)…")
    time.sleep(30)
    send_command(client, "Stop")
    time.sleep(2)
    send_command(client, "Reset")
    time.sleep(1)


def test_move_with_rotation(client: mqtt.Client, xbot_id: int = 1,
                             x: float = 0.36, y: float = 0.36,
                             rotation_deg: float = 90.0):
    """Move an XBot to a position and rotate it."""
    print(f"\n=== Test: Move XBot {xbot_id} to ({x:.3f}, {y:.3f}) + rotate {rotation_deg}° ===")
    send_command(client, "Start")
    time.sleep(1.5)
    send_motion(client, xbot_id, x, y, rotation_deg=rotation_deg)
    print("  Waiting for completion (up to 45 s)…")
    time.sleep(45)
    send_command(client, "Stop")
    time.sleep(2)
    send_command(client, "Reset")
    time.sleep(1)


def test_hold_unhold(client: mqtt.Client, xbot_id: int = 1):
    """Start, dispatch a move, hold mid-flight, then unhold."""
    print(f"\n=== Test: Hold / UnHold while XBot {xbot_id} is moving ===")
    send_command(client, "Start")
    time.sleep(1.5)
    send_motion(client, xbot_id, 0.72, 0.72)
    time.sleep(3)                # Let it start moving
    print("  Holding…")
    send_command(client, "Hold")
    time.sleep(5)
    print("  UnHolding…")
    send_command(client, "UnHold")
    time.sleep(30)
    send_command(client, "Stop")
    time.sleep(2)
    send_command(client, "Reset")
    time.sleep(1)


def test_multi_xbot(client: mqtt.Client):
    """Send two XBots to different positions simultaneously."""
    print("\n=== Test: Two XBots moving simultaneously ===")
    send_command(client, "Start")
    time.sleep(1.5)
    send_motion(client, xbot_id=1, x=0.36, y=0.12)
    send_motion(client, xbot_id=2, x=0.84, y=0.60)
    print("  Waiting for completion (up to 45 s)…")
    time.sleep(45)
    send_command(client, "Stop")
    time.sleep(2)
    send_command(client, "Reset")
    time.sleep(1)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    client = make_client()

    # Pick which test to run via a simple CLI argument, e.g.:
    #   python test_mqtt_commands.py start_stop
    #   python test_mqtt_commands.py move
    #   python test_mqtt_commands.py rotate
    #   python test_mqtt_commands.py hold
    #   python test_mqtt_commands.py multi
    # Default: just Start → Stop

    scenario = sys.argv[1] if len(sys.argv) > 1 else "start_stop"

    try:
        if scenario == "start_stop":
            test_start_stop(client)

        elif scenario == "move":
            xbot_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            x       = float(sys.argv[3]) if len(sys.argv) > 3 else 0.36
            y       = float(sys.argv[4]) if len(sys.argv) > 4 else 0.36
            test_single_move(client, xbot_id, x, y)

        elif scenario == "rotate":
            xbot_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            x       = float(sys.argv[3]) if len(sys.argv) > 3 else 0.36
            y       = float(sys.argv[4]) if len(sys.argv) > 4 else 0.36
            deg     = float(sys.argv[5]) if len(sys.argv) > 5 else 90.0
            test_move_with_rotation(client, xbot_id, x, y, deg)

        elif scenario == "hold":
            xbot_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            test_hold_unhold(client, xbot_id)

        elif scenario == "multi":
            test_multi_xbot(client)

        else:
            print(f"Unknown scenario '{scenario}'. Choices: start_stop | move | rotate | hold | multi")

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        client.loop_stop()
        client.disconnect()
        print("[MQTT] Disconnected")

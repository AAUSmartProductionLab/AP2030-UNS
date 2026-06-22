from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine
import datetime
import cv2
import base64
import numpy as np
import os

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "localhost")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/QualityControl"

uuid = ""

# Publisher for the final image data (local PC captures image)
image_publisher = Publisher(
    BASE_TOPIC + "/DATA/Image",
    "./MQTTSchemas/image.schema.json",
    2)

VC_cmd_publisher = Publisher(
    BASE_TOPIC + "/VC/CMD/Capture",
    "./MQTTSchemas/command.schema.json",
    2)

simulation_running = False


def capture_process(duration=0.1):
    """Send capture command to VC (if any), then generate a dummy image locally and publish it."""
    global simulation_running
    simulation_running = True

    # Trigger Visual Components animation/capture if running (non-blocking)
    try:
        VC_cmd_publisher.publish({"Command": "CaptureImage", "Uuid": uuid}, cameraProxy, False)
    except Exception as e:
        print(f"Error sending VC capture command: {e}")

    # short wait to allow VC animation to progress if needed
    time.sleep(duration)

    try:
        # Create a simple placeholder image (640x480, light gray)
        height, width = 480, 640
        image = np.full((height, width, 3), 200, dtype=np.uint8)

        # Draw timestamp to make images unique and human-readable
        ts_text = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        cv2.putText(image, ts_text, (10, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        # Encode image to compressed format (JPEG)
        _, img_encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        img_bytes = base64.b64encode(img_encoded).decode('utf-8')

        # Generate ISO 8601 timestamp with Z suffix for UTC
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec='milliseconds').replace('+00:00', 'Z')

        response = {
            "Image": img_bytes,
            "TimeStamp": timestamp,
            "Format": "base64_jpeg",
            "Uuid": uuid,
        }
        image_publisher.publish(response, cameraProxy, True)
    except Exception as e:
        print(f"Error publishing dummy image: {e}")
    finally:
        simulation_running = False


def capture_callback(topic, client, message, properties):
    """Callback handler for capture commands from controller."""
    global uuid
    uuid = message.get("Uuid")
    try:
        state_machine.execute_command(message, capture, capture_process)
    except Exception as e:
        print(f"Error in capture_callback: {e}")


capture = ResponseAsync(
    BASE_TOPIC+"/DATA/Capture",
    BASE_TOPIC+"/CMD/Capture",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
    2,
    capture_callback
)

cameraProxy = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "CameraProxy",
    [capture, image_publisher, VC_cmd_publisher]
)

state_machine = PackMLStateMachine(
    BASE_TOPIC, cameraProxy, None, config_path="omronCamera.yaml")
state_machine.failureChance = 0

# Register asset after MQTT connection is established
cameraProxy.on_ready(state_machine.register_asset)


def main():
    """Main entry point for the filling proxy"""
    cameraProxy.loop_forever()


if __name__ == "__main__":
    main()

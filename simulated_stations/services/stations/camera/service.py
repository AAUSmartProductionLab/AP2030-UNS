from packml_runtime.mqtt import Proxy, ResponseAsync, Publisher, Subscriber
import time
import random
from packml_runtime.simulator import PackMLStateMachine
import datetime
import cv2
import base64
import os

BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/QualityControl"
QC_OK_RATE = float(os.getenv("QC_OK_RATE", "0.8"))
uuid = ""

image_publisher = Publisher(
    BASE_TOPIC + "/DATA/Image",
    "./MQTTSchemas/image.schema.json",
    2)

quality_publisher = Publisher(
    BASE_TOPIC + "/DATA/Quality",
    "./MQTTSchemas/qualityResult.schema.json",
    2)


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec='milliseconds').replace('+00:00', 'Z')


def publish_quality_result():
    """Sample Ok/NotOk for the currently inspected product and publish it.

    The result is retained so a late-subscribing FluentCheck (PR4 sensor
    predicate) can still see the latest classification per product UUID.
    """
    if not uuid:
        return
    result = "Ok" if random.random() < QC_OK_RATE else "NotOk"
    confidence = round(random.uniform(0.7, 0.99), 3)
    payload = {
        "TimeStamp": _now_iso(),
        "Uuid": uuid,
        "Result": result,
        "Confidence": confidence,
    }
    print(f"[QualityControl] {uuid} -> {result} (confidence={confidence})")
    quality_publisher.publish(payload, cameraProxy, True)


def capture_process(duration=0.5):
    time.sleep(duration)
    webcam = None
    try:
        webcam = cv2.VideoCapture(0)
        ret, image = webcam.read()

        if not ret:
            print("Failed to capture image from webcam")
            # Still publish a QC result so the FOND policy can branch
            publish_quality_result()
            return

        # Rotate image 90 degrees counter-clockwise
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

        # Encode image to compressed format (JPEG)
        _, img_encoded = cv2.imencode(
            '.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        img_bytes = base64.b64encode(img_encoded).decode('utf-8')

        # Generate ISO 8601 timestamp with Z suffix for UTC
        timestamp = _now_iso()

        response = {
            "Image": img_bytes,
            "TimeStamp": timestamp,
            "Format": "base64_jpeg",
            "Uuid": uuid,
        }
        image_publisher.publish(response, cameraProxy, True)
    except Exception as e:
        print(f"Error publishing image: {e}")
    finally:
        if webcam is not None:
            webcam.release()
        # The FOND outcome is published regardless of imaging success so
        # the BT executor always has a sensor reading to evaluate
        # QualityOk(Product) against.
        publish_quality_result()


def capture_callback(topic, client, message, properties):
    """Callback handler for capture commands"""
    global uuid
    uuid = message.get("Uuid")
    try:
        state_machine.execute_command(message, capture, capture_process)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


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
    [capture, image_publisher, quality_publisher]
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

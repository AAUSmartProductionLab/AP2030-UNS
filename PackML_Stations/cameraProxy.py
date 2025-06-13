from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine
import datetime
import cv2
import base64

BROKER_ADDRESS = "172.18.0.1"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Camera"
uuid=""

image_publisher = Publisher(
        BASE_TOPIC + "/DATA/Image",
        "./schemas/image.schema.json", 
        2)


def capture_process(duration=0.5):
    time.sleep(duration)
    webcam = None
    try:
        webcam = cv2.VideoCapture(0)
        ret, image = webcam.read()
        
        if not ret:
            print("Failed to capture image from webcam")
            return
            
        # Encode image to compressed format (JPEG)
        _, img_encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        img_bytes = base64.b64encode(img_encoded).decode('utf-8')
        
        # Generate ISO 8601 timestamp with Z suffix for UTC
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        
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


def capture_callback(topic, client, message, properties):
    """Callback handler for capture commands"""
    global uuid
    uuid =message.get("Uuid")
    try:
        state_machine.execute_command(message, capture, capture_process)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


capture = ResponseAsync(
    BASE_TOPIC+"/DATA/Capture", 
    BASE_TOPIC+"/CMD/Capture",
    "./schemas/commandResponse.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    capture_callback
)

cameraProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "CameraProxy", 
    [capture,image_publisher]
)

state_machine = PackMLStateMachine(BASE_TOPIC, cameraProxy, None)
state_machine.failureChance=0

def main():
    """Main entry point for the filling proxy"""

    
    cameraProxy.loop_forever()


if __name__ == "__main__":
    main()

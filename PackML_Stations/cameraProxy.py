from MQTT_classes import Proxy, ResponseAsync, Publisher, Subscriber
import time
from PackMLSimulator import PackMLStateMachine
import datetime
import cv2
import base64

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Camera"


image_publisher = Publisher(
        BASE_TOPIC + "/DATA/Image",
        "./schemas/image.schema.json", 
        2)


def capture_process(duration=0.5, state_machine=None):
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
            "Format": "base64_jpeg"
        }
        image_publisher.publish(response, cameraProxy, True)
    except Exception as e:
        print(f"Error publishing image: {e}")
    finally:
        if webcam is not None:
            webcam.release()


def start_callback(topic, client, message, properties):
    """Callback handler for registering commands without executing them"""
    try:  
        # Register the command without executing
        state_machine.start_command(message)
        
    except Exception as e:
        print(f"Error in register_callback: {e}")

def complete_callback(topic, client, message, properties):
    """Callback handler for unregistering commands by removing them from the queue"""
    try:  
        # Unregister/remove the command from the queue if it's not being processed
        state_machine.complete_command(message)
        
    except Exception as e:
        print(f"Error in unregister_callback: {e}")

def capture_callback(topic, client, message, properties):
    """Callback handler for capture commands"""
    try:
        state_machine.execute_command(message, capture, capture_process)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


start = Subscriber(
    BASE_TOPIC+"/CMD/Start",
    "./schemas/command.schema.json", 
    2, 
    start_callback
)
complete = Subscriber(
    BASE_TOPIC+"/CMD/Complete",
    "./schemas/command.schema.json", 
    2, 
    complete_callback
)

state = Publisher(
    BASE_TOPIC+"/DATA/State", 
    "./schemas/stationState.schema.json",
    2
)

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
    [capture,start, complete,image_publisher]
)

state_machine = PackMLStateMachine(state, cameraProxy, None)
state_machine.failureChance=0

def main():
    """Main entry point for the filling proxy"""

    
    cameraProxy.loop_forever()


if __name__ == "__main__":
    main()

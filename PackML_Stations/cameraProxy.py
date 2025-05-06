from MQTT_classes import Proxy, ResponseAsync, Publisher
import time
import numpy as np
from PackMLSimulator import PackMLStateMachine, PackMLState
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
    if state_machine and state_machine.total_duration:
        state_machine.elapsed_time = duration


def publishImage(state_machine, reset=False):
    # Only publish on final completion, not during progress or reset
    if reset or state_machine.progress < 1.0:
        return
        
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
        image_publisher.publish(response, state_machine.client, True)
    except Exception as e:
        print(f"Error publishing image: {e}")
    finally:
        if webcam is not None:
            webcam.release()

def register_callback(topic, client, message, properties):
    """Callback handler for registering commands without executing them"""
    try:  
        # Register the command without executing
        state_machine.register_command(message)
        
    except Exception as e:
        print(f"Error in register_callback: {e}")

def capture_callback(topic, client, message, properties):
    """Callback handler for capture commands"""
    if state_machine.state == PackMLState.IDLE:
        try:
            duration = 2.0
            state_machine.process_next_command(message, capture_process, duration)
        except Exception as e:
            print(f"Error in stopper_callback: {e}")

def unregister_callback(topic, client, message, properties):
    """Callback handler for unregistering commands by removing them from the queue"""
    try:  
        # Unregister/remove the command from the queue if it's not being processed
        state_machine.unregister_command(message)
        
    except Exception as e:
        print(f"Error in unregister_callback: {e}")

capture = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Capture",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    capture_callback
)
register = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Register",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    register_callback
)

unregister = ResponseAsync(
    BASE_TOPIC+"/DATA/State", 
    BASE_TOPIC+"/CMD/Unregister",
    "./schemas/stationState.schema.json", 
    "./schemas/command.schema.json", 
    2, 
    unregister_callback
)

cameraProxy = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "CameraProxy", 
    [capture,register, unregister,image_publisher]
)
state_machine = PackMLStateMachine(capture,register,unregister, cameraProxy, None,publishImage)
state_machine.failureChance=0

def main():
    """Main entry point for the filling proxy"""

    
    cameraProxy.loop_forever()


if __name__ == "__main__":
    main()

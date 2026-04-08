import json
import base64
import io
from PIL import Image
import paho.mqtt.client as mqtt
import os

# MQTT broker settings
MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.100.123")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = "NN/Nybrovej/InnoLab/QualityControl/DATA/Image"

# Callback when connecting to the MQTT broker


def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # Subscribe to the image topic
    client.subscribe(MQTT_TOPIC)
    print(f"Subscribed to {MQTT_TOPIC}")

# Callback when a message is received from the broker


def on_message(client, userdata, msg):
    try:
        # Decode the JSON message
        payload = json.loads(msg.payload.decode())

        # Extract the base64 encoded image and its format
        if "Image" in payload and "Format" in payload:
            image_base64 = payload["Image"]
            image_format = payload["Format"]

            print(f"Received image with format: {image_format}")

            # Decode the base64 image
            image_data = base64.b64decode(image_base64)

            # Create an image from the binary data
            image = Image.open(io.BytesIO(image_data))

            # Display the image
            image.show()
        else:
            print("Received payload does not contain required Image or Format fields")

    except Exception as e:
        print(f"Error processing message: {e}")
        print(f"Payload: {msg.payload}")


# Set up the MQTT client
client = mqtt.Client(client_id="ImageSubscriber")
client.on_connect = on_connect
client.on_message = on_message

# Connect to the broker
try:
    print(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    # Start the loop to process callbacks
    print("Starting MQTT subscriber. Press Ctrl+C to exit.")
    client.loop_forever()

except KeyboardInterrupt:
    print("Subscriber terminated by user")
except Exception as e:
    print(f"Connection failed: {e}")
finally:
    client.disconnect()

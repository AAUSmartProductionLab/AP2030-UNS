import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes
from random import randint
import json
from jsonschema import validate

BASE_TOPIC = "IMATile/PMC"

MQTT_TOPICS = [(BASE_TOPIC + "/connect/response", 0),
               (BASE_TOPIC + "/moveToFilling/response", 0)]

# A MQTT client that requests things from the PMC proxy. To be replaced with behavior trees down the line


class PMCProxy(mqtt.Client):
    def __init__(self, address: str, port: int, id: str):
        super().__init__(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=id,
            protocol=mqtt.MQTTv5
        )
        self.address = address
        self.port = port
        self.on_connect = self.on_connect_callback
        self.on_disconnect = self.on_disconnect_callback
        self.connect(self.address, self.port)

    def on_connect_callback(self, client, userdata, flags, rc, properties):
        self.message_callback_add(
            BASE_TOPIC + "/connect/response", self.on_connect_response_callback)
        self.message_callback_add(
            BASE_TOPIC + "/moveToFilling/response", self.on_move_to_filling_response_callback)
        self.subscribe(MQTT_TOPICS)
        print("Connected with result code " + str(rc))
        self.request_connection()

    def on_disconnect_callback(self, client, userdata, rc):
        print(f"Disconnected with result code {rc}")

    def request_connection(self):
        base_topic = BASE_TOPIC + "/connect"
        schema = load_schema("connection.schema.json")

        request = {}
        request["address"] = "127.0.0.1"
        request["target_state"] = "connected"
        request["xbot_no"] = 3
        publish_properties = Properties(PacketTypes.PUBLISH)
        publish_properties.ResponseTopic = base_topic + \
            schema["responsesubtopic"]
        publish_properties.CorrelationData = str(randint(1000, 9999)).encode()
        self.publish(base_topic, json.dumps(request),
                     0, properties=publish_properties)
        print("Published connection request")

    def on_connect_response_callback(self, client, userdata, message):
        msg = json.loads(message.payload.decode("utf-8"))
        validate(instance=msg, schema=load_schema(
            "response_state.schema.json"))
        print("Received response to connection request: " + msg["state"])
        print("CorrelationData:", message.properties.CorrelationData)
        self.move_to_filling()

    def move_to_filling(self):
        base_topic = BASE_TOPIC + "/moveToFilling"
        schema = load_schema("moveToPosition.schema.json")

        request = {}
        request["target_pos"] = "filling"
        request["xbot_id"] = 1
        publish_properties = Properties(PacketTypes.PUBLISH)
        publish_properties.ResponseTopic = base_topic + \
            schema["responsesubtopic"]
        publish_properties.CorrelationData = str(randint(1000, 9999)).encode()
        self.publish(base_topic, json.dumps(request),
                     0, properties=publish_properties)
        print("Published fill request")

    def on_move_to_filling_response_callback(self, client, userdata, message):
        msg = json.loads(message.payload.decode("utf-8"))
        validate(instance=msg, schema=load_schema(
            "response_state.schema.json"))
        print("Received response to fill request: " + msg["state"])
        print("CorrelationData:", message.properties.CorrelationData)
        exit()


def load_schema(schema_file):
    with open(schema_file, 'r') as file:
        return json.load(file)


def main():
    pmcProxy = PMCProxy("192.168.0.104", 1883, "MQTTPythonClient")
    pmcProxy.loop_forever()  # This will block and wait for callbacks


if __name__ == "__main__":
    main()

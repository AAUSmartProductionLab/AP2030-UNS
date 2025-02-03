from utils import load_schema

from random import randint

import json
from jsonschema import validate

import paho.mqtt.client as mqtt
from paho.mqtt.enums import MQTTProtocolVersion
from paho.mqtt.properties import Properties, PacketTypes


from typing import List


class TopicPubSub:
    # A class that handles the publishing and subscribing to a topic including json validation
    def __init__(self, topic, qos: int = 0, publish_schema_path: str = None, subscribe_schema_path: str = None, callback_method: callable = None):

        self.qos = qos
        self.pub_schema = load_schema(publish_schema_path)
        self.sub_schema = load_schema(subscribe_schema_path)

        self.pubtopic = topic + \
            self.pub_schema["subtopic"] if self.pub_schema != None else None
        self.subtopic = topic + \
            self.sub_schema["subtopic"] if self.sub_schema != None else None
        self.callback_method = callback_method

    def publish(self, request, client):
        publish_properties = Properties(PacketTypes.PUBLISH)
        publish_properties.CorrelationData = str(randint(1000, 9999)).encode()
        client.publish(self.pubtopic, json.dumps(request),
                       0, properties=publish_properties)
        print("Published request")

    def registerCallback(self, client):
        if self.sub_schema != None:
            client.message_callback_add(self.subtopic, self.callback)

    def subscribe(self, client):
        if self.sub_schema != None:
            client.subscribe(self.subtopic, self.qos)

    def callback(self, client, userdata, message):
        msg = json.loads(message.payload.decode("utf-8"))
        validate(instance=msg, schema=self.sub_schema)
        if self.callback_method is not None:
            self.callback_method(client, msg, self.pubtopic,
                                 self.subtopic, message.properties)
        print("Received message: " + str(msg))


class PMCProxy(mqtt.Client):
    def __init__(self, address: str, port: int, id: str, pubsubs: List[TopicPubSub]):
        super().__init__(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=id,
            protocol=mqtt.MQTTv5
        )
        self.address = address
        self.port = port
        self.pubsubs = pubsubs
        self.on_connect = self.on_connect_callback
        self.on_disconnect = self.on_disconnect_callback

        self.connect(self.address, self.port)

    def on_connect_callback(self, client, userdata, flags, rc, properties):
        for topic in self.pubsubs:
            topic.registerCallback(self)
            topic.subscribe(self)

        print("Connected with result code " + str(rc))

    def on_disconnect_callback(self, client, userdata, rc):
        print(f"Disconnected with result code {rc}")

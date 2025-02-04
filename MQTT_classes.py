from random import randint
from typing import List
from uuid import uuid4
import json
from jsonschema import validate

import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties, PacketTypes

from utils import load_schema


class Topic:
    # A class for publishing on and subscribing to a topic including json validation before publishing and after receiving a message
    def __init__(self, topic: str, publish_schema_path: str = None, subscribe_schema_path: str = None, qos: int = 0, callback_method: callable = None):

        self.qos: int = qos
        self.pub_schema = load_schema(publish_schema_path)
        self.sub_schema = load_schema(subscribe_schema_path)

        self.pubtopic: str = topic + self.pub_schema["subtopic"]
        self.subtopic: str = topic + self.sub_schema["subtopic"]

        self.callback_method: callable = callback_method

        self.publish_properties = Properties(PacketTypes.PUBLISH)
        self.publish_properties.CorrelationData = str(
            randint(1000, 9999)).encode()

    def publish(self, request, client):
        if self.pub_schema != None:
            validate(instance=request, schema=self.pub_schema)
            if self.pubtopic != None and self.pubtopic != "":
                client.publish(self.pubtopic, json.dumps(request),
                               self.qos, properties=self.publish_properties)

    def registerCallback(self, client):
        if self.subtopic != None and self.subtopic != "":
            client.message_callback_add(self.subtopic, self.callback)

    def subscribe(self, client):
        if self.subtopic != None and self.subtopic != "":
            client.subscribe(self.subtopic, self.qos)

    def callback(self, client, userdata, message):
        if self.sub_schema != None:
            msg = json.loads(message.payload.decode("utf-8"))
            validate(instance=msg, schema=self.sub_schema)
            if self.callback_method is not None:
                self.callback_method(self, client, msg, message.properties)
            print("Received response: " + str(msg) +
                  " on topic" + self.subtopic)


class Response(Topic):
    # A class handling responding to requests on a topic described in the user property ResponseTopic
    def __init__(self, topic: str,  publish_schema_path: str, subscribe_schema_path: str, qos: int = 0, callback_method: callable = None):
        super().__init__(topic, publish_schema_path,
                         subscribe_schema_path, qos, callback_method)

    def publish(self, request, client, publish_properties):
        if self.pub_schema != None:
            validate(instance=request, schema=self.pub_schema)
            if publish_properties.ResponseTopic != None and publish_properties.ResponseTopic != "":
                # The response is to be published on the ResponseTopic provided with the request
                client.publish(publish_properties.ResponseTopic, json.dumps(request),
                               self.qos, properties=publish_properties)


class Request(Topic):
    # A class for requesting a service from a proxy and listening for response on a unique topic
    def __init__(self, topic: str, publish_schema_path: str, subscribe_schema_path: str, qos: int = 0, callback_method: callable = None):
        super().__init__(topic, publish_schema_path,
                         subscribe_schema_path, qos, callback_method)

        # The subtopic is appended with a generated unique identifier and added to the ResponseTopic user property
        self.subtopic: str = self.pubtopic + self.sub_schema["subtopic"] + \
            "/"+str(uuid4())
        self.publish_properties.ResponseTopic = self.subtopic
        # Not strictly necessary since the response topic includes a uuid


class Proxy(mqtt.Client):
    def __init__(self, address: str, port: int, id: str, pubsubs: List[Topic]):
        super().__init__(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=id,
            protocol=mqtt.MQTTv5
        )
        self.address: str = address
        self.port: int = port
        self.topics: List[Topic] = pubsubs
        self.on_connect = self.on_connect_callback
        self.on_disconnect = self.on_disconnect_callback

        self.connect(self.address, self.port)

    def on_connect_callback(self, client, userdata, flags, rc, properties):
        for topic in self.topics:
            topic.registerCallback(self)
            topic.subscribe(self)

        print("Connected to Broker with result code " + str(rc))

    def on_disconnect_callback(self, client, userdata, flags, rc, properties):
        print(f"Disconnected with result code {rc}")


# class TopicPubSub:
#     # A generic class that handles the publishing and subscribing to a topic including json validation
#     def __init__(self, topic: str, qos: int = 0, publish_schema_path: str = None, subscribe_schema_path: str = None, callback_method: callable = None):

#         self.qos: int = qos
#         self.pub_schema = load_schema(publish_schema_path)
#         self.sub_schema = load_schema(subscribe_schema_path)

#         self.pubtopic: str = topic + \
#             self.pub_schema["subtopic"] if self.pub_schema != None else None
#         self.subtopic: str = topic + \
#             self.sub_schema["subtopic"] if self.sub_schema != None else None
#         self.callback_method: callable = callback_method

#     def publish(self, request, client, publish_properties=None):
#         if publish_properties == None:
#             publish_properties = Properties(PacketTypes.PUBLISH)
#             # Random 4digit correlation data so requests can be mapped to responses
#             publish_properties.CorrelationData = str(
#                 randint(1000, 9999)).encode()
#         client.publish(self.pubtopic, json.dumps(request),
#                        self.qos, properties=publish_properties)

#     def registerCallback(self, client):
#         if self.sub_schema != None:
#             client.message_callback_add(self.subtopic, self.callback)

#     def subscribe(self, client):
#         if self.sub_schema != None:
#             client.subscribe(self.subtopic, self.qos)

#     def callback(self, client, userdata, message):
#         msg = json.loads(message.payload.decode("utf-8"))
#         validate(instance=msg, schema=self.sub_schema)
#         if self.callback_method is not None:
#             self.callback_method(self, client, msg, message.properties)
#         print("Received message: " + str(msg))

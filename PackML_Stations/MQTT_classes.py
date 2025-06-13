from random import randint
from typing import List
from uuid import uuid4
import json
from jsonschema import validate, RefResolver

import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties, PacketTypes

from utils import load_schema
import threading


class Topic:
    # A class for publishing on and subscribing to a topic including json validation before publishing and after receiving a message
    def __init__(self, publish_topic: str="",subscribe_topic: str="", publish_schema_path: str = None, subscribe_schema_path: str = None, qos: int = 2, callback_method: callable = None):

        self.qos: int = qos
        # Handle the new return format from load_schema
        schema_data = load_schema(publish_schema_path)
        self.pub_schema = schema_data[0] if schema_data else None
        self.pub_resolver = schema_data[1] if schema_data else None
        
        schema_data = load_schema(subscribe_schema_path)
        self.sub_schema = schema_data[0] if schema_data else None
        self.sub_resolver = schema_data[1] if schema_data else None

        # The suptopic is inspired by VDA5050
        self.pubtopic: str = publish_topic
        self.subtopic: str = subscribe_topic

        self.callback_method: callable = callback_method

        self.publish_properties = Properties(PacketTypes.PUBLISH)

    def publish(self, message, client, retain=False):
        if self.pub_schema != None:
            validate(instance=message, schema=self.pub_schema, resolver=self.pub_resolver)
            if self.pubtopic != None and self.pubtopic != "":
                client.publish(self.pubtopic, json.dumps(message),
                               self.qos, properties=self.publish_properties, retain=retain)

    def registerCallback(self, client):
        if self.subtopic != None and self.subtopic != "":
            client.message_callback_add(self.subtopic, self.callback)

    def subscribe(self, client):
        if self.subtopic != None and self.subtopic != "":
            print("Subscribing to topic " + self.subtopic)
            client.subscribe(self.subtopic, self.qos)

    def callback(self, client, userdata, message):
        if self.sub_schema != None:
            try:
                msg = json.loads(message.payload.decode("utf-8"))
                validate(instance=msg, schema=self.sub_schema, resolver=self.sub_resolver)
                if self.callback_method is not None:
                    self.callback_method(self, client, msg, message.properties)
                print("Received message on topic" +
                      self.subtopic + ": " + str(msg))
            except Exception as e:
                print(f"Error in callback: {e}")


class Response(Topic):
    # A class handling responding to requests on a topic described in the user property ResponseTopic
    def __init__(self,publish_topic: str,subscribe_topic: str,  publish_schema_path: str, subscribe_schema_path: str, qos: int = 2, callback_method: callable = None):
        super().__init__(publish_topic, subscribe_topic, publish_schema_path,
                         subscribe_schema_path, qos, callback_method)

    def publish(self, request, client, publish_properties, retain=False):
        if self.pub_schema != None:
            validate(instance=request, schema=self.pub_schema, resolver=self.pub_resolver)
            if publish_properties.ResponseTopic != None and publish_properties.ResponseTopic != "":
                # The response is to be published on the ResponseTopic provided with the request
                client.publish(publish_properties.ResponseTopic, json.dumps(request),
                               self.qos, properties=publish_properties, retain=retain)

class Subscriber(Topic):
    # A class handling responding to requests on a topic described in the user property ResponseTopic
    # The callback is executed in a seperate thread so time.sleep can be used to wait for processes to finish without blocking the paho loop
    def __init__(self, subscribe_topic: str, subscribe_schema_path: str, qos: int = 2, callback_method: callable = None):
        super().__init__("",subscribe_topic, "",subscribe_schema_path, qos, callback_method)
    def callback(self, client, userdata, message):
        # run callback function in seperate thread
        if self.sub_schema != None:
            try:
                msg = json.loads(message.payload.decode("utf-8"))
                validate(instance=msg, schema=self.sub_schema, resolver=self.sub_resolver)
                if self.callback_method is not None:
                    thr = threading.Thread(target=self.callback_method, args=(
                        self, client, msg, message.properties))
                    thr.start()
                print("Received message on topic" +
                      self.subtopic + ": " + str(msg))
            except Exception as e:
                print(f"Error in register_callback: {e}")


class ResponseAsync(Topic):
    # A class handling responding to requests on a topic described in the user property ResponseTopic
    # The callback is executed in a seperate thread so time.sleep can be used to wait for processes to finish without blocking the paho loop
    def __init__(self, publish_topic: str,subscribe_topic: str, publish_schema_path: str, subscribe_schema_path: str, qos: int = 2, callback_method: callable = None):
        super().__init__(publish_topic,subscribe_topic, publish_schema_path,
                         subscribe_schema_path, qos, callback_method)

    def publish(self, request, client, publish_properties=None, retain=False):
        if self.pub_schema != None:
            try:
                validate(instance=request, schema=self.pub_schema, resolver=self.pub_resolver)
                # The response is to be published on the ResponseTopic provided with the request
                client.publish(self.pubtopic, json.dumps(request),
                               self.qos, retain=retain)
            except Exception as e:
                print(f"Error in publish: {e}")

    def callback(self, client, userdata, message):
        # run callback function in seperate thread
        if self.sub_schema != None:
            try:
                msg = json.loads(message.payload.decode("utf-8"))
                validate(instance=msg, schema=self.sub_schema, resolver=self.sub_resolver)
                if self.callback_method is not None:
                    thr = threading.Thread(target=self.callback_method, args=(
                        self, client, msg, message.properties))
                    thr.start()
                print("Received message on topic" +
                      self.subtopic + ": " + str(msg))
            except Exception as e:
                print(f"Error in register_callback: {e}")


class Request(Topic):
    # A class for requesting a service from a proxy and listening for response on a unique topic
    def __init__(self,publish_topic: str,subscribe_topic: str, publish_schema_path: str, subscribe_schema_path: str, qos: int = 2, callback_method: callable = None):
        super().__init__(publish_topic,subscribe_topic, publish_schema_path,
                         subscribe_schema_path, qos, callback_method)

        # The subtopic is appended with a generated unique identifier and added to the ResponseTopic user property
        self.subtopic: str = self.pubtopic
        # Not strictly necessary since the response topic includes a uuid


class Publisher(Topic):
    """
    A class for only publishing messages to a topic with schema validation.
    This class does not subscribe to any topics or handle responses.
    """
    def __init__(self, publish_topic: str, publish_schema_path: str, qos: int = 2):
        # Pass None for subscribe_schema_path and callback since we won't be subscribing
        super().__init__(publish_topic, None, publish_schema_path, None, qos, None)
    
    # Override subscribe-related methods to do nothing
    def registerCallback(self, client):
        pass  # No subscription, so no callback to register
    
    def subscribe(self, client):
        pass  # Do not subscribe
    
    def callback(self, client, userdata, message):
        pass  # Not expecting any callbacks
        
    def publish(self, request, client, retain=False):
        if self.pub_schema != None:
            validate(instance=request, schema=self.pub_schema, resolver=self.pub_resolver)
            client.publish(self.pubtopic, json.dumps(request),
                           self.qos, retain=retain)


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

        # self.connect(self.address, self.port)
        
        self.connect("hivemq-broker")

    def on_connect_callback(self, client, userdata, flags, rc, properties):
        for topic in self.topics:
            topic.registerCallback(self)
            topic.subscribe(self)

        print("Connected to Broker with result code " + str(rc))

    def register_topic(self, topic: Topic):
        # Register a new topic to the client
        self.topics.append(topic)
        topic.registerCallback(self)
        topic.subscribe(self)

    def on_disconnect_callback(self, client, userdata, flags, rc, properties):
        print(f"Disconnected with result code {rc}")

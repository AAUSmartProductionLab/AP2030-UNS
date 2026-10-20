from random import randint
from typing import List
from uuid import uuid4
import json
from jsonschema import validate, RefResolver

import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties, PacketTypes

from .schema_utils import load_schema
import threading

# ---------------------------------------------------------------------------
# MQTT 5 request/reply correlation (mqv_responseTopic): every incoming
# command's Correlation Data is recorded under its reply topic and Uuid; the
# TERMINAL reply (SUCCESS/FAILURE) echoes it. The requester takes the first
# correlated reply as the result, so progress acks (State RUNNING) are
# published without correlation. The reply payload stays the station's
# declared contract.
# ---------------------------------------------------------------------------

_correlation_key = "Uuid"  # the station reply contract's correlation field
_correlation_capacity = 64
_pending_correlations: dict = {}
_correlation_lock = threading.Lock()


def _record_request_correlation(reply_topic, message_properties, msg):
    try:
        echo = getattr(message_properties, "CorrelationData", None)
        key = msg.get(_correlation_key) if isinstance(msg, dict) else None
        if echo is None or key is None:
            return
        props = Properties(PacketTypes.PUBLISH)
        props.CorrelationData = echo
        with _correlation_lock:
            if len(_pending_correlations) >= _correlation_capacity:
                _pending_correlations.pop(next(iter(_pending_correlations)))
            _pending_correlations[(reply_topic, str(key))] = props
    except Exception:
        pass


def _correlation_for(reply_topic, message):
    """The recorded correlation of a terminal reply, consumed; ``None`` for a
    progress ack (State RUNNING), which must not end the request."""
    try:
        if not isinstance(message, dict) or message.get("State") == "RUNNING":
            return None
        key = message.get(_correlation_key)
        if key is None:
            return None
        with _correlation_lock:
            return _pending_correlations.pop((reply_topic, str(key)), None)
    except Exception:
        return None


class Topic:
    # A class for publishing on and subscribing to a topic including json validation before publishing and after receiving a message
    def __init__(self, publish_topic: str = "", subscribe_topic: str = "", publish_schema_path: str = None, subscribe_schema_path: str = None, qos: int = 2, callback_method: callable = None):

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

    def publish(self, message, client, retain=False, properties=None):
        if self.pub_schema != None:
            validate(instance=message, schema=self.pub_schema,
                     resolver=self.pub_resolver)
            if self.pubtopic != None and self.pubtopic != "":
                props = properties
                if props is None:
                    props = _correlation_for(self.pubtopic, message) or self.publish_properties
                client.publish(self.pubtopic, json.dumps(message),
                               self.qos, properties=props, retain=retain)

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
                validate(instance=msg, schema=self.sub_schema,
                         resolver=self.sub_resolver)
                _record_request_correlation(self.pubtopic, message.properties, msg)
                if self.callback_method is not None:
                    self.callback_method(self, client, msg, message.properties)
                print("Received message on topic" +
                      self.subtopic + ": " + str(msg))
            except Exception as e:
                print(f"Error in callback: {e}")


class Response(Topic):
    # A class handling responding to requests on a topic described in the user property ResponseTopic
    def __init__(self, publish_topic: str, subscribe_topic: str,  publish_schema_path: str, subscribe_schema_path: str, qos: int = 2, callback_method: callable = None):
        super().__init__(publish_topic, subscribe_topic, publish_schema_path,
                         subscribe_schema_path, qos, callback_method)

    def publish(self, request, client, publish_properties, retain=False):
        if self.pub_schema != None:
            validate(instance=request, schema=self.pub_schema,
                     resolver=self.pub_resolver)
            if publish_properties.ResponseTopic != None and publish_properties.ResponseTopic != "":
                # The response is to be published on the ResponseTopic provided with the request
                client.publish(publish_properties.ResponseTopic, json.dumps(request),
                               self.qos, properties=publish_properties, retain=retain)


class Subscriber(Topic):
    # A class handling responding to requests on a topic described in the user property ResponseTopic
    # The callback is executed in a seperate thread so time.sleep can be used to wait for processes to finish without blocking the paho loop
    def __init__(self, subscribe_topic: str, subscribe_schema_path: str, qos: int = 2, callback_method: callable = None):
        super().__init__("", subscribe_topic, None, subscribe_schema_path, qos, callback_method)

    def callback(self, client, userdata, message):
        # run callback function in seperate thread
        if self.sub_schema != None:
            try:
                msg = json.loads(message.payload.decode("utf-8"))
                validate(instance=msg, schema=self.sub_schema,
                         resolver=self.sub_resolver)
                _record_request_correlation(self.pubtopic, message.properties, msg)
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
    def __init__(self, publish_topic: str, subscribe_topic: str, publish_schema_path: str, subscribe_schema_path: str, qos: int = 2, callback_method: callable = None):
        super().__init__(publish_topic, subscribe_topic, publish_schema_path,
                         subscribe_schema_path, qos, callback_method)

    def publish(self, request, client, publish_properties=None, retain=False):
        try:
            # Validate only if schema is available
            if self.pub_schema is not None:
                validate(instance=request, schema=self.pub_schema,
                         resolver=self.pub_resolver)
            # Publish regardless of schema availability; the terminal reply
            # echoes the request's correlation (see _correlation_for).
            props = publish_properties if isinstance(publish_properties, Properties) else None
            if props is None:
                props = _correlation_for(self.pubtopic, request) or self.publish_properties
            client.publish(self.pubtopic, json.dumps(request),
                           self.qos, retain=retain, properties=props)
            print(f"Published to {self.pubtopic}: {request}", flush=True)
        except Exception as e:
            print(f"Error in publish: {e}", flush=True)

    def callback(self, client, userdata, message):
        # run callback function in separate thread
        try:
            msg = json.loads(message.payload.decode("utf-8"))
            # Validate only if schema is available
            if self.sub_schema is not None:
                validate(instance=msg, schema=self.sub_schema,
                         resolver=self.sub_resolver)
            _record_request_correlation(self.pubtopic, message.properties, msg)
            if self.callback_method is not None:
                thr = threading.Thread(target=self.callback_method, args=(
                    self, client, msg, message.properties))
                thr.start()
            print(
                f"Received message on topic {self.subtopic}: {msg}", flush=True)
        except Exception as e:
            print(f"Error in ResponseAsync callback: {e}", flush=True)


class Request(Topic):
    # A class for requesting a service from a proxy and listening for response on a unique topic
    def __init__(self, publish_topic: str, subscribe_topic: str, publish_schema_path: str, subscribe_schema_path: str, qos: int = 2, callback_method: callable = None):
        super().__init__(publish_topic, subscribe_topic, publish_schema_path,
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
            validate(instance=request, schema=self.pub_schema,
                     resolver=self.pub_resolver)
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
        self._on_ready_callbacks = []  # Callbacks to invoke after connection
        self._is_connected = False  # Track connection state

        print(f"[Proxy:{id}] Connecting to {address}:{port}...", flush=True)
        self.connect(self.address, self.port)

    def on_connect_callback(self, client, userdata, flags, rc, properties):
        print(f"[Proxy] Connected to Broker! Result code: {rc}", flush=True)
        self._is_connected = True
        for topic in self.topics:
            topic.registerCallback(self)
            topic.subscribe(self)
        print(f"[Proxy] Subscribed to {len(self.topics)} topics", flush=True)

        # Execute any registered on-ready callbacks
        for callback in self._on_ready_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"[Proxy] Error in on_ready callback: {e}", flush=True)

    def on_ready(self, callback):
        """Register a callback to be invoked after MQTT connection is established.
        If already connected, the callback is executed immediately."""
        self._on_ready_callbacks.append(callback)
        # If already connected, execute immediately
        if self._is_connected:
            try:
                callback()
            except Exception as e:
                print(f"[Proxy] Error in on_ready callback: {e}", flush=True)

    def register_topic(self, topic: Topic):
        # Register a new topic to the client
        self.topics.append(topic)
        topic.registerCallback(self)
        topic.subscribe(self)

    def on_disconnect_callback(self, client, userdata, flags, rc, properties):
        print(
            f"[Proxy] Disconnected from broker! Result code: {rc}", flush=True)

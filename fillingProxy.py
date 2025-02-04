from MQTT_classes import PMCProxy, TopicPubSub

import threading

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "IMATile/Fill"


# A MQTT client that emulates a filling and IPC station


def main():
    fillProxy = PMCProxy(BROKER_ADDRESS, BROKER_PORT,
                         "FillProxy", [
                             TopicPubSub(
                                 BASE_TOPIC, 0, "schemas/response_state.schema.json", "schemas/dispense.schema.json", dispense_callback),
                             TopicPubSub(
                                 BASE_TOPIC, 0, "schemas/response_state.schema.json", "schemas/weigh.schema.json", weigh_callback)
                         ]
                         )
    fillProxy.loop_forever()


def dispense_callback(pubsub: TopicPubSub, client, message, properties):
    time = 0.0
    # TODO these are for now arbitray time outs
    if message["product_state"] == "empty":
        time = 5
    elif message["product_state"] == "half-full":
        time = 3
    else:
        time = 1
    timer = threading.Timer(time, dispense, args=(
        pubsub, client, "", properties))
    timer.start()


def weigh_callback(pubsub: TopicPubSub, client, message, properties):
    timer = None
    if message["product_state"] == "empty":
        timer = threading.Timer(5, weigh, args=(
            pubsub, client, 0.0, properties))
    elif message["product_state"] == "half-full":
        timer = threading.Timer(5, weigh, args=(
            pubsub, client, 1.5, properties))
    else:
        timer = threading.Timer(5, weigh, args=(
            pubsub, client, 3.0, properties))
    timer.start()


def dispense(pubsub: TopicPubSub, client, message, properties):
    # since the process is asynchronos it should return running once it runs
    response = {}
    response["state"] = "running"
    pubsub.publish(response, client, properties)
    try:
        response["state"] = "successful"
        response["filling_status"] = "filled"
    except Exception as e:
        response["state"] = "failure"
        response["error_code"] = str(e)

    # answer on the same main topic and the configured pubtopic
    pubsub.publish(response, client, properties)


def weigh(pubsub: TopicPubSub, client, weight, properties):
    # since the process is asynchronos it should return running once it runs
    response = {}
    response["state"] = "running"
    pubsub.publish(response, client, properties)
    try:
        response["state"] = "successful"
        response["weight"] = weight
    except Exception as e:
        response["state"] = "failure"
        response["error_code"] = str(e)

    # answer on the same main topic and the configured pubtopic
    pubsub.publish(response, client, properties)


if __name__ == "__main__":
    main()

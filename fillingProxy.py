from MQTT_classes import PMCProxy, TopicPubSub

import threading

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "IMATile/Fill"


# A MQTT client that requests things from the PMC proxy. To be replaced with behavior trees down the line


def main():
    fillProxy = PMCProxy(BROKER_ADDRESS, BROKER_PORT,
                         "FillProxy", [
                             TopicPubSub(
                                 BASE_TOPIC, 0, "schemas/response_state.schema.json", "schemas/dispense.schema.json", dispense_callback),
                             TopicPubSub(
                                 BASE_TOPIC, 0, "schemas/response_state.schema.json", "schemas/weigh.schema.json", weigh_callback)
                         ]
                         )
    fillProxy.loop_forever


def dispense_callback(pubsub: TopicPubSub, client, message, properties):
    timer = threading.Timer(5, dispense(pubsub, client, message, properties))
    timer.start()


def weigh_callback(pubsub: TopicPubSub, client, message, properties):
    timer = threading.Timer(5, weigh(pubsub, client, message, properties))
    timer.start()


def dispense(pubsub: TopicPubSub, client, message, properties):
    response = {}
    try:
        timer = threading.Timer(5, dispense)
        timer.start()
        response["state"] = "success"
    except Exception as e:
        print(e)
        response["state"] = "failure"

    # answer on the same main topic and the configured pubtopic
    pubsub.publish(response, client, properties)


def weigh(pubsub: TopicPubSub, client, message, properties):
    response = {}
    try:
        timer = threading.Timer(5, dispense)
        timer.start()
        response["state"] = "success"
    except Exception as e:
        print(e)
        response["state"] = "failure"

    # answer on the same main topic and the configured pubtopic
    pubsub.publish(response, client, properties)


if __name__ == "__main__":
    main()

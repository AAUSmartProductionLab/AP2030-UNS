from MQTT_classes import PMCProxy, TopicResponse

import time

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "IMATile/Fill"


# A MQTT client that emulates a filling and IPC station


def main():
    fillProxy = PMCProxy(BROKER_ADDRESS, BROKER_PORT,
                         "FillProxy", [
                             TopicResponse(
                                 BASE_TOPIC, "schemas/dispense.schema.json", "schemas/response_state.schema.json", 2,  dispense_callback),
                             TopicResponse(
                                 BASE_TOPIC, "schemas/weigh.schema.json", "schemas/response_state.schema.json", 2,  weigh_callback)
                         ]
                         )
    fillProxy.loop_forever()


def dispense_callback(pubsub: TopicResponse, client, message, properties):
    response = {}
    response["state"] = "running"
    pubsub.publish(response, client, properties)
    try:
        duration = 0
        if message["product_state"] == "empty":
            duration = 5
        elif message["product_state"] == "half-full":
            duration = 3
        else:
            duration = 1
        time.sleep(duration)
        response["state"] = "successful"
        response["filling_status"] = "filled"
    # since the process is asynchronos it should return running once it runs

    except Exception as e:
        response["state"] = "failure"
        response["error_code"] = str(e)
    # answer on the same main topic and the configured pubtopic
    pubsub.publish(response, client, properties)


def weigh_callback(pubsub: TopicResponse, client, message, properties):
    response = {}
    response["state"] = "running"
    pubsub.publish(response, client, properties)
    try:
        time.sleep(2)

        if message["product_state"] == "empty":
            weight = 0.0
        elif message["product_state"] == "half-full":
            weight = 1.5
        else:
            weight = 3.0
        response["state"] = "successful"
        response["weight"] = weight
    # since the process is asynchronos it should return running once it runs

    except Exception as e:
        response["state"] = "failure"
        response["error_code"] = str(e)

    # answer on the same main topic and the configured pubtopic
    pubsub.publish(response, client, properties)


if __name__ == "__main__":
    main()

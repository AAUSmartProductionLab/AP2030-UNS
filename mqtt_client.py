from MQTT_classes import PMCProxy, TopicPubSub

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "IMATile/PMC"


# A MQTT client that requests things from the PMC proxy. To be replaced with behavior trees down the line


def main():
    pmcProxy = PMCProxy(BROKER_ADDRESS, BROKER_PORT,
                        "MQTTPythonClient", [
                            TopicPubSub(BASE_TOPIC + "/connect", 0,
                                        "connection.schema.json", "response_state.schema.json"),
                            TopicPubSub(BASE_TOPIC + "/moveToPosition",
                                        0, "moveToPosition.schema.json", "response_state.schema.json")
                        ]
                        )
    run = True
    pmcProxy.loop()
    connect_to_simulated_PMC(pmcProxy)
    while run:
        rc = pmcProxy.loop(timeout=1.0)
        if rc != 0:
            exit()


def connect_to_simulated_PMC(client):
    request = {}
    request["address"] = "127.0.0.1"
    request["target_state"] = "connected"
    request["xbot_no"] = 3
    client.pubsubs[0].publish(request, client)
    move_to_loading(client)
    move_to_filling(client)
    move_to_unloading(client)
    move_to_loading(client)


def move_to_filling(client):
    request = {}
    request["target_pos"] = "filling"
    request["xbot_id"] = 1
    client.pubsubs[1].publish(request, client)


def move_to_loading(client):
    request = {}
    request["target_pos"] = "loading"
    request["xbot_id"] = 1
    client.pubsubs[1].publish(request, client)


def move_to_unloading(client):
    request = {}
    request["target_pos"] = "unloading"
    request["xbot_id"] = 1
    client.pubsubs[1].publish(request, client)


if __name__ == "__main__":
    main()

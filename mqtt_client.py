from MQTT_classes import PMCProxy, TopicRequest

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "IMATile"


# A MQTT client that requests things from the PMC proxy and the Filling Proxy. To be replaced with behavior trees down the line


def main():
    pmcProxy = PMCProxy(BROKER_ADDRESS, BROKER_PORT,
                        "MQTTPythonClient", [
                            TopicRequest(BASE_TOPIC+"/PMC",
                                         "schemas/connection.schema.json", "schemas/response_state.schema.json", 2, move_to_loading),
                            # Loading Postion
                            TopicRequest(BASE_TOPIC+"/PMC",
                                         "schemas/moveToPosition.schema.json", "schemas/response_state.schema.json", 2, move_to_filling),
                            # Filling Postion
                            TopicRequest(BASE_TOPIC+"/PMC",
                                         "schemas/moveToPosition.schema.json", "schemas/response_state.schema.json", 2, weigh1),
                            # Weigh, IPC, Weigh
                            TopicRequest(BASE_TOPIC+"/Fill",
                                         "schemas/weigh.schema.json", "schemas/response_state.schema.json", 2, dispense),
                            TopicRequest(BASE_TOPIC+"/Fill",
                                         "schemas/dispense.schema.json", "schemas/response_state.schema.json", 2, weigh2),
                            TopicRequest(BASE_TOPIC+"/Fill",
                                         "schemas/weigh.schema.json", "schemas/response_state.schema.json", 2, move_to_unloading),
                            # Unloading Postion
                            TopicRequest(BASE_TOPIC+"/PMC",
                                         "schemas/moveToPosition.schema.json", "schemas/response_state.schema.json", 2, move_to_loading)

                            # TopicPubSub(BASE_TOPIC+"/PMC", 0,
                            #             "schemas/connection.schema.json", "schemas/response_state.schema.json"),
                            # TopicPubSub(BASE_TOPIC+"/PMC",
                            #             0, "schemas/moveToPosition.schema.json", "schemas/response_state.schema.json"),
                            # TopicPubSub(BASE_TOPIC+"/Fill",
                            #             0, "schemas/dispense.schema.json", "schemas/response_state.schema.json"),
                            # TopicPubSub(BASE_TOPIC+"/Fill",
                            #             0, "schemas/weigh.schema.json", "schemas/response_state.schema.json"),
                        ]
                        )
    run = True
    pmcProxy.loop()
    connect_to_simulated_PMC(None, pmcProxy, "", "")
    while run:
        rc = pmcProxy.loop(timeout=1.0)
        if rc != 0:
            exit()


def connect_to_simulated_PMC(self, client, msg, properties):
    request = {}
    request["address"] = "127.0.0.1"
    request["target_state"] = "connected"
    request["xbot_no"] = 3
    client.pubsubs[0].publish(request, client)


def move_to_loading(self, client, msg, properties):

    request = {}
    request["target_pos"] = "loading"
    request["xbot_id"] = 1
    client.pubsubs[1].publish(request, client)


def move_to_filling(self, client, msg, properties):

    request = {}
    request["target_pos"] = "filling"
    request["xbot_id"] = 1
    client.pubsubs[2].publish(request, client)


def weigh1(self, client, msg, properties):

    request = {}
    request["product_state"] = "empty"
    client.pubsubs[3].publish(request, client)


def dispense(self, client, msg, properties):

    request = {}
    request["product_state"] = "empty"
    client.pubsubs[4].publish(request, client)


def weigh2(self, client, msg, properties):

    request = {}
    request["product_state"] = "full"
    client.pubsubs[5].publish(request, client)


def move_to_unloading(self, client, msg, properties):

    request = {}
    request["target_pos"] = "unloading"
    request["xbot_id"] = 1
    client.pubsubs[6].publish(request, client)


if __name__ == "__main__":
    main()

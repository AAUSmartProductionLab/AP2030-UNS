from MQTT_classes import Proxy, Request

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "IMATile"


# A MQTT client that requests things from the PMC proxy and the Filling Proxy. To be replaced with behavior trees down the line


def main():
    pmcProxy = Proxy(BROKER_ADDRESS, BROKER_PORT,
                     "MQTTPythonClient", [
                         Request(BASE_TOPIC+"/PMC",
                                 "schemas/connection.schema.json", "schemas/response_state.schema.json", 2, move_to_loading),
                         # Loading Postion
                         Request(BASE_TOPIC+"/PMC",
                                 "schemas/moveToPosition.schema.json", "schemas/response_state.schema.json", 2, move_to_filling),
                         # Filling Postion
                         Request(BASE_TOPIC+"/PMC",
                                 "schemas/moveToPosition.schema.json", "schemas/response_state.schema.json", 2, weigh1),
                         # Weigh, IPC, Weigh
                         Request(BASE_TOPIC+"/Fill",
                                 "schemas/weigh.schema.json", "schemas/response_state.schema.json", 2, dispense),
                         Request(BASE_TOPIC+"/Fill",
                                 "schemas/dispense.schema.json", "schemas/response_state.schema.json", 2, weigh2),
                         Request(BASE_TOPIC+"/Fill",
                                 "schemas/weigh.schema.json", "schemas/response_state.schema.json", 2, move_to_unloading),
                         # Unloading Postion
                         Request(BASE_TOPIC+"/PMC",
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
    client.topics[0].publish(request, client)


def move_to_loading(self, client, msg, properties):
    if msg["state"] == "successful":
        request = {}
        request["target_pos"] = "loading"
        request["xbot_id"] = 1
        client.topics[1].publish(request, client)


def move_to_filling(self, client, msg, properties):
    if msg["state"] == "successful":
        request = {}
        request["target_pos"] = "filling"
        request["xbot_id"] = 1
        client.topics[2].publish(request, client)


def weigh1(self, client, msg, properties):
    if msg["state"] == "successful":
        request = {}
        request["product_state"] = "empty"
        client.topics[3].publish(request, client)


def dispense(self, client, msg, properties):
    if msg["state"] == "successful":
        request = {}
        request["product_state"] = "empty"
        client.topics[4].publish(request, client)


def weigh2(self, client, msg, properties):
    if msg["state"] == "successful":
        request = {}
        request["product_state"] = "full"
        client.topics[5].publish(request, client)


def move_to_unloading(self, client, msg, properties):
    if msg["state"] == "successful":
        request = {}
        request["target_pos"] = "unloading"
        request["xbot_id"] = 1
        client.topics[6].publish(request, client)


if __name__ == "__main__":
    main()

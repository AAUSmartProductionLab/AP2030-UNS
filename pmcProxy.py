from pmclib import system_commands as _sys   # PMC System related commands
from pmclib import xbot_commands as bot     # PMC Mover related commands
from pmclib import pmc_types                # PMC API Types

import paho.mqtt.client as mqtt
from paho.mqtt.enums import MQTTProtocolVersion
from paho.mqtt.properties import Properties, PacketTypes

import json
from jsonschema import validate

import time
import threading

MQTT_TOPICS = [("IMATile/PMC/connect", 0)]


class PlanarMotorProxy(mqtt.Client):
    def __init__(self, address: str, port: int, id: str):
        super().__init__(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=id,
            protocol=MQTTProtocolVersion.MQTTv5
        )
        self.address = address
        self.port = port
        self.on_connect = self.on_connect_callback
        # self.on_message = self.on_message_callback
        # self.on_subscribe = self.on_subscribe_callback
        # self.on_publish = self.on_publish_callback
        # self.on_unsubscribe = self.on_unsubscribe_callback
        self.connect(self.address, self.port)

        self.loop_forever()

    def on_connect_callback(self, client, userdata, flags, rc, properties):

        self.message_callback_add(
            "IMATile/PMC/connect", self.on_connect_request_callback)
        self.subscribe(MQTT_TOPICS)
        print("Connected with result code "+str(rc))

    # def on_subscribe_callback(self, client, userdata, mid, reason_code_list, properties):
    #     # Since we subscribed only for a single channel, reason_code_list contains
    #     # a single entry
    #     if reason_code_list[0].is_failure:
    #         print(f"Broker rejected you subscription: {reason_code_list[0]}")
    #     else:
    #         print(
    #             f"Broker granted the following QoS: {reason_code_list[0].value}")

    # def on_unsubscribe_callback(self, client, userdata, mid, reason_code_list, properties):
    #     # Be careful, the reason_code_list is only present in MQTTv5.
    #     # In MQTTv3 it will always be empty
    #     if len(reason_code_list) == 0 or not reason_code_list[0].is_failure:
    #         print("unsubscribe succeeded (if SUBACK is received in MQTTv3 it success)")
    #     else:
    #         print(f"Broker replied with failure: {reason_code_list[0]}")
    #     client.disconnect()

    def on_connect_request_callback(self, client, userdata, message):
        retval = False
        try:
            msg = json.loads(message.payload.decode("utf-8"))
            validate(instance=msg, schema=load_schema(
                "connection.schema.json"))
            if msg["target_state"] == "connected":
                retval = pmc_startup(msg["address"], msg.get("xbot_count", 0))
            else:
                pass

        except Exception as e:
            print(e)
            retval = False

        response = {}
        response["state"] = "successful" if retval == True else "failure"
        if retval == True:
            # If the pmc is connected start publishing the information of the xBots
            threading.Timer(5.0, publish_xbot_positions, [
                            client, userdata, message]).start()
        self.publish(message.properties.ResponseTopic, json.dumps(response),
                     properties=message.properties)


def load_schema(schema_file):
    with open(schema_file, 'r') as file:
        return json.load(file)


def pmc_startup(ip: str = "127.0.0.1", expected_xbot_count: int = 0):
    try:
        # Connect to the PMC
        if not _sys.connect_to_specific_pmc(ip):
            raise Exception("Could not connect to PMC")
        # Gain mastership
        if not _sys.is_master():
            _sys.gain_mastership()
        # Get PMC status
        pmc_status = _sys.get_pmc_status()
        if pmc_status != pmc_types.PMCSTATUS.PMC_FULLCTRL and pmc_status != pmc_types.PMCSTATUS.PMC_INTELLIGENTCTRL:
            isPMCInOperation = False
            attemtedActivation = False
            while isPMCInOperation == False:
                pmc_status = _sys.get_pmc_status()
                # PMC is in transition state
                if pmc_status == pmc_types.PMCSTATUS.PMC_ACTIVATING or pmc_status == pmc_types.PMCSTATUS.PMC_BOOTING or pmc_status == pmc_types.PMCSTATUS.PMC_DEACTIVATING or pmc_status == pmc_types.PMCSTATUS.PMC_ERRORHANDLING:
                    isPMCInOperation = False
                    time.sleep(10)
                # PMC is in stable state but not operational
                elif pmc_status == pmc_types.PMCSTATUS.PMC_ERROR or pmc_status == pmc_types.PMCSTATUS.PMC_INACTIVE:
                    isPMCInOperation = False
                    if attemtedActivation == False:
                        attemtedActivation = True
                        # no need to catch the possible exception as we want to quit anyway in that case so we catch it with the big try catch block
                        bot.activate_xbots()
                    else:
                        raise Exception(
                            "Attempted to activate xbots but failed")
                # PMC is now operational
                elif pmc_status == pmc_types.PMCSTATUS.PMC_FULLCTRL or pmc_status == pmc_types.PMCSTATUS.PMC_INTELLIGENTCTRL:
                    isPMCInOperation = True
                else:
                    raise Exception("Unexpected PMC status")
        # Check configuration
        # TODO
        # Check xbot ammount
        # will throw an exception if PmcRtn is not ALLOK
        xbotIDs: pmc_types.XBotIDs = bot.get_xbot_ids()
        if expected_xbot_count > 0:
            if len(xbotIDs.xbot_ids) != expected_xbot_count:
                raise Exception("Incorrect amount of xBots")
        # stop motions
        bot.stop_motion(0)
        # check xbot state and levitate
        areXbotsLevitated = False
        attemptedLevitation = False
        areXbotsinTransitionState = False
        while areXbotsLevitated == False:
            areXbotsLevitated = True
            areXbotsinTransitionState = False
            for xbotID in xbotIDs.xbot_ids_array:
                xbot = bot.get_xbot_status(xbotID)
                if xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_LANDED:
                    areXbotsLevitated = False
                elif xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_STOPPING or xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_DISCOVERING or xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_MOTION:
                    areXbotsLevitated = False
                    areXbotsinTransitionState = True
                elif xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_IDLE or xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_STOPPED:
                    pass
                elif xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_WAIT or xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_OBSTACLE_DETECTED or xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_HOLDPOSITION:
                    raise Exception(
                        "Failed to stop motion, current state is " + xbot.xbot_state)
                elif xbot.xbot_state == pmc_types.XBOTSTATE.XBOT_DISABLED:
                    raise Exception(
                        "Error cannor levelate xbot, current state is " + xbot.xbot_state)
                else:
                    raise Exception(
                        "Error unexpected xbot state, current state is " + xbot.xbot_state)
            if areXbotsinTransitionState == False and areXbotsinTransitionState == False:
                if attemptedLevitation == False:
                    bot.levitation_command(
                        0, pmc_types.LEVITATEOPTIONS.LEVITATE)
                    attemptedLevitation = True
                else:
                    raise Exception("Attempted to levitate xBots but failed")
        return True
    except Exception as e:
        print(e)
        return False


def gain_mastership():
    if not _sys.is_master():
        rtn = _sys.gain_mastership()
        print(pmc_types.PMCRTN.ALLOK)
        if rtn != pmc_types.PMCRTN.ALLOK:
            raise Exception("Could not gain mastership")


def wait_for_full_control(timeout=60):
    max_time = time.time() + timeout
    while _sys.get_pmc_status() != pmc_types.PMCSTATUS.PMC_FULLCTRL:
        time.sleep(0.5)
        if time.time() > max_time:
            raise TimeoutError("PMC Activation timeout")


class xBot:
    def __init__(self, xBotInfo: pmc_types.XBotInfo):
        self.xbot_id: int = xBotInfo.xbot_id
        self.x_pos: float = xBotInfo.x_pos
        self.y_pos: float = xBotInfo.y_pos
        self.z_pos: float = xBotInfo.z_pos
        self.rx_pos: float = xBotInfo.rx_pos
        self.ry_pos: float = xBotInfo.ry_pos
        self.rz_pos: float = xBotInfo.rz_pos
        self.xbot_state: pmc_types.XBOTSTATE = xBotInfo.xbot_state
        self.xbot_type: pmc_types.XBOTTYPE = xBotInfo.xbot_type

    def linear_motion_si(self,
                         x: float,
                         y: float,
                         final_speed: float,
                         max_speed: float,
                         max_accel: float,
                         cmd_label: int = 1,
                         position_mode: pmc_types.POSITIONMODE = pmc_types.POSITIONMODE.ABSOLUTE,
                         path_type: pmc_types.LINEARPATHTYPE = pmc_types.LINEARPATHTYPE.DIRECT):
        bot.linear_motion_si(
            cmd_label,
            self.xbot_id,
            position_mode,
            path_type,
            x,
            y,
            final_speed,
            max_speed,
            max_accel
        )

    def get_xbot_status(self, feedback_type: pmc_types.FEEDBACKOPTION = None):
        return bot.get_xbot_status(self.xbot_id, feedback_type)


def get_xbot_positions():
    xbot_list = bot.get_all_xbot_info(
        pmc_types.ALLXBOTSFEEDBACKOPTION.POSITION)
    return [xBot(xBotInfo) for xBotInfo in xbot_list]


def main():
    # runs the proxy in a blocking way forever
    pmProxy = PlanarMotorProxy("192.168.0.104", 1883, "PlanarMotorProxy")

    # connect_to_pmc(ip="127.0.0.1")
    # gain_mastership()
    # bot.activate_xbots()
    # wait_for_full_control()
    # xbots: list[xBot] = get_xbot_positions()
    # xbots[0].linear_motion_si(0.1, 0.1, 0.0, 10.0, 2.0)
    # xbots[0].linear_motion_si(0.15, 0.15, 0.0, 10.0, 2.0)
    # print(xbots[0].get_xbot_status(pmc_types.FEEDBACKOPTION.FORCE))
    # xbots = get_xbot_positions()
    # print(xbots[0].x_pos)
    # time.sleep(60)
    # _sys.release_mastership()


if __name__ == "__main__":
    # perhaps ap2030@192.169.0.104
    main()

from MQTT_classes import PMCProxy, TopicPubSub

from pmclib import system_commands as _sys   # PMC System related commands
from pmclib import xbot_commands as bot     # PMC Mover related commands
from pmclib import pmc_types                # PMC API Types

import time
from typing import List, Tuple
from random import randint

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "IMATile/PMC"

FILL_POS = (0.480, 0.660)
LOADING_POS = (0.060, 0.120)
UNLOADING_POS = (0.900, 0.120)


def connection_callback(self, client, message, properties):
    response = {}
    try:
        if message["target_state"] == "connected":
            pmc_startup(message["address"], message.get("xbot_no", 0))
        else:
            pass
        response["state"] = "successful"
    except Exception as e:
        print(e)
        response["state"] = "failure"

    # answer on the same main topic and the configured pubtopic
    self.publish(response, client, properties)


def move_to_position_callback(self, client, message, properties):
    response = {}
    try:
        if message["target_pos"] == "filling":
            pmc_move_to_pos(message["xbot_id"], FILL_POS)
        elif message["target_pos"] == "loading":
            pmc_move_to_pos(message["xbot_id"], LOADING_POS)
        elif message["target_pos"] == "unloading":
            pmc_move_to_pos(message["xbot_id"], UNLOADING_POS,
                            linearPathType=pmc_types.LINEARPATHTYPE.XTHENY)
        else:
            pass
        wait_untiL_xbots_idle([message["xbot_id"]])
        # TODO check if the xbot is in the correct position

        response["state"] = "successful"

    except Exception as e:
        print(e)
        response["state"] = "failure"

    # answer on the same main topic and the configured pubtopic
    self.publish(response, client, properties)


def pmc_startup(ip: str = "127.0.0.1", expected_xbot_count: int = 0):
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
                time.sleep(1)
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
        if len(xbotIDs.xbot_ids_array) != expected_xbot_count:
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
        if areXbotsLevitated == False and areXbotsinTransitionState == False:
            if attemptedLevitation == False:
                bot.levitation_command(
                    0, pmc_types.LEVITATEOPTIONS.LEVITATE)
                attemptedLevitation = True
            else:
                raise Exception("Attempted to levitate xBots but failed")


def wait_untiL_xbots_idle(xBotIDs: List[int]):
    areXbotsIdle = False
    if _sys.get_pmc_status() == pmc_types.PMCSTATUS.PMC_FULLCTRL:
        while True:
            areXbotsIdle = True
            for xbotID in xBotIDs:
                xbotState: pmc_types.XBOTSTATE = bot.get_xbot_status(
                    xbotID).xbot_state
                if xbotState == pmc_types.XBOTSTATE.XBOT_IDLE:
                    pass  # Continue with the next xbot
                elif xbotState == pmc_types.XBOTSTATE.XBOT_STOPPING or xbotState == pmc_types.XBOTSTATE.XBOT_MOTION or xbotState == pmc_types.XBOTSTATE.XBOT_WAIT or xbotState == pmc_types.XBOTSTATE.XBOT_HOLDPOSITION or xbotState == pmc_types.XBOTSTATE.XBOT_OBSTACLE_DETECTED:
                    areXbotsIdle = False
                else:
                    raise Exception("Unexpected xbot state" + str(xbotState))
                if areXbotsIdle == False:
                    time.sleep(0.5)
            if areXbotsIdle == True:
                break
    else:
        raise Exception("PMC is not in full control")


def pmc_move_to_pos(xbotID: int,  pos: Tuple[float, float], positionMode=pmc_types.POSITIONMODE.ABSOLUTE, linearPathType=pmc_types.LINEARPATHTYPE.DIRECT, final_vel=0.0, max_vel=10.0, max_acc=2.0):
    wait_untiL_xbots_idle([xbotID])
    cmd_label = randint(1, 65535)
    bot.linear_motion_si(cmd_label, xbotID, positionMode,
                         linearPathType, pos[0], pos[1], final_vel, max_vel, max_acc)

    # bot.auto_driving_motion_si(1, pmc_types.ASYNCOPTIONS.MOVEALL, [
    #                            xbotID], [pos[0]], [pos[1]])
    return cmd_label


def main():
    # runs the proxy in a blocking way forever
    pmcProxy = PMCProxy(BROKER_ADDRESS, BROKER_PORT,
                        "PlanarMotorProxy", [
                            TopicPubSub(BASE_TOPIC + "/connect", 0, "response_state.schema.json",
                                        "connection.schema.json",  connection_callback),
                            TopicPubSub(BASE_TOPIC + "/moveToPosition",
                                        0, "response_state.schema.json", "moveToPosition.schema.json",  move_to_position_callback)
                        ]
                        )
    pmcProxy.loop_forever()


if __name__ == "__main__":
    main()

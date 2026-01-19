"""
XBot Controller Module

Handles all XBot hardware interaction including:
- PMC connection and mastership
- XBot activation and state management  
- Path execution with motion commands
- Position feedback and monitoring
"""

from pmclib import xbot_commands as xbot
from pmclib import system_commands as sys
from pmclib import pmc_types as pm
import time
from math import sqrt


# Constants
POSITION_TOLERANCE_M = 0.005


def connect_to_pmc(pmc_ip=None):
    """Connect to PMC system and gain mastership."""
    try:
        if pmc_ip:
            success = sys.connect_to_specific_pmc(pmc_ip)
        else:
            success = sys.auto_search_and_connect_to_pmc()

        if not success:
            print("ERROR: Failed to connect to PMC")
            return False

        # Gain mastership
        sys.gain_mastership()

        # Wait for PMC to be ready
        for _ in range(50):
            status = sys.get_pmc_status()
            if status in (pm.PMCSTATUS.PMC_FULLCTRL, pm.PMCSTATUS.PMC_INTELLIGENTCTRL):
                return True
            time.sleep(0.2)

        return True

    except Exception as e:
        print(f"ERROR: Connection failed: {e}")
        return False


def disconnect_from_pmc():
    """Disconnect from PMC system."""
    try:
        sys.disconnect_from_pmc()
    except Exception as e:
        print(f"ERROR: Disconnect failed: {e}")


def check_mastership():
    """Check if we have mastership."""
    try:
        is_master = sys.is_master()
        return is_master
    except Exception as e:
        print(f"ERROR: Mastership check failed: {e}")
        return False


def ensure_xbot_ready(xbot_id):
    """
    Ensure XBot is in a ready state (IDLE).
    Handles recovery from STOPPED, MOTION, or other states.
    """
    try:
        status = xbot.get_xbot_status(
            xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
        state = status.xbot_state

        if state == pm.XBOTSTATE.XBOT_IDLE:
            return True

        if state == pm.XBOTSTATE.XBOT_MOTION:
            xbot.stop_motion(xbot_id=xbot_id)
            time.sleep(0.5)
            status = xbot.get_xbot_status(
                xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
            state = status.xbot_state

        if state == pm.XBOTSTATE.XBOT_STOPPED:
            xbot.deactivate_xbots()
            time.sleep(0.5)
            xbot.activate_xbots()
            time.sleep(0.5)
            status = xbot.get_xbot_status(
                xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
            state = status.xbot_state

        if state == pm.XBOTSTATE.XBOT_IDLE:
            return True
        else:
            print(f"ERROR: XBot {xbot_id} in state {state}, cannot proceed")
            return False

    except Exception as e:
        print(f"ERROR: XBot {xbot_id} preparation failed: {e}")
        return False


def activate_xbot(xbot_id):
    """Activate a specific XBot and ensure it's ready."""
    try:
        if not ensure_xbot_ready(xbot_id):
            return False

        xbot.activate_xbots()
        time.sleep(0.5)

        return True

    except Exception as e:
        print(f"ERROR: XBot {xbot_id} activation failed: {e}")
        return False


def get_active_xbot_ids():
    """Get list of all active XBot IDs in the system."""
    try:
        rtn = xbot.get_xbot_ids()
        # access attributes using snake_case as per pmclib conventions
        return [rtn.xbot_ids_array[i] for i in range(rtn.xbot_count)]
    except Exception as e:
        print(f"ERROR: Failed to get active XBot IDs: {e}")
        return []


def get_xbot_position(xbot_id):
    """Get current XBot position, return None if failed."""
    try:
        status = xbot.get_xbot_status(
            xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
        pos = status.feedback_position_si
        return (float(pos[0]), float(pos[1]))
    except Exception as e:
        print(f"ERROR: Failed to get XBot {xbot_id} position: {e}")
        return None


def execute_path(xbot_id, path_meters, workspace):
    """
    Execute a path with the XBot using DIRECT path type for all segments.

    The A* algorithm with turning cost ensures smooth, obstacle-free paths,
    so we can safely use DIRECT motion for horizontal, vertical, and diagonal moves.

    Args:
        xbot_id: ID of the XBot
        path_meters: List of waypoints in meters [(x, y), ...]
        workspace: Workspace configuration (kept for consistency)

    Returns:
        True if successful, False otherwise
    """
    for i in range(len(path_meters) - 1):
        current = path_meters[i]
        target = path_meters[i + 1]

        # Send motion command with DIRECT path type
        xbot.linear_motion_si(
            cmd_label=i + 1,
            xbot_id=xbot_id,
            position_mode=pm.POSITIONMODE.ABSOLUTE,
            path_type=pm.LINEARPATHTYPE.DIRECT,
            target_xmeters=target[0],
            target_ymeters=target[1],
            final_speed_meters_ps=0.0,
            max_speed_meters_ps=0.5,
            max_acceleration_meters_ps2=1.0,
            corner_radius=0.0
        )

        # Wait for completion
        timeout = 30.0
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = xbot.get_xbot_status(
                xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
            pos = status.feedback_position_si
            current_x, current_y = float(pos[0]), float(pos[1])
            state = status.xbot_state

            # Check if reached target
            dist = sqrt((current_x - target[0])
                        ** 2 + (current_y - target[1])**2)
            if dist < POSITION_TOLERANCE_M:
                break

            # Check if stopped unexpectedly
            if state == pm.XBOTSTATE.XBOT_STOPPED:
                print(
                    f"ERROR: XBot stopped at ({current_x:.3f}, {current_y:.3f})")
                return False

            time.sleep(0.05)
        else:
            # Timeout
            print(f"ERROR: Segment {i+1} timeout")
            return False

    return True

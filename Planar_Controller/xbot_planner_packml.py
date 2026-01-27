import sys
import time
import json
import threading
import os
import numpy as np
from math import sqrt
from datetime import datetime, timezone
import logging

# Ensure we can import from local library and PackML_Stations
sys.path.append(os.path.join(os.path.dirname(__file__), 'library'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'PackML_Stations'))

from pmclib import system_commands as pmc_sys
from pmclib import pmc_types as pm
from pmclib import xbot_commands as xbot

from library.xbot_controller import (
    connect_to_pmc,
    disconnect_from_pmc,
    activate_xbot,
    get_xbot_position,
    get_active_xbot_ids
)
from library.occupancy_grid import (
    load_workspace_from_pmc,
    meters_to_grid,
    grid_to_meters,
    create_occupancy_grid,
    grid_path_to_meters,
    GRID_CELL_SIZE_M,
    FLYWAY_SIZE_M
)
from library.astar_pathfinding import astar_search
from library.path_simplifier import simplify_path, merge_collinear_segments

from PackMLSimulator import PackMLStateMachine, PackMLState
from MQTT_classes import Proxy, ResponseAsync, Publisher, Topic

# MQTT Configuration
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_BASE_TOPIC = "NN/Nybrovej/InnoLab/Planar"

# Global Workspace Config
WORKSPACE = None
ACTIVE_XBOT_IDS = set()
PMC_LOCK = threading.Lock()
XBOT_POS_PUBLISHERS = {}

def get_flyway_centers():
    """Get all valid flyway centers."""
    workspace_width_m = WORKSPACE['width'] * FLYWAY_SIZE_M
    workspace_height_m = WORKSPACE['height'] * FLYWAY_SIZE_M
    centers = []
    half_flyway = FLYWAY_SIZE_M / 2
    x = half_flyway
    while x < workspace_width_m:
        y = half_flyway
        while y < workspace_height_m:
            col = int(x / FLYWAY_SIZE_M)
            row = int(y / FLYWAY_SIZE_M)
            is_hole = False
            if 'holes' in WORKSPACE:
                for hole in WORKSPACE['holes']:
                    if hole[0] == col and hole[1] == row:
                        is_hole = True
                        break
            if not is_hole:
                centers.append((x, y))
            y += FLYWAY_SIZE_M
        x += FLYWAY_SIZE_M
    return centers

def select_rotation_point(current_pos, goal_pos, known_obstacles=None):
    centers = get_flyway_centers()
    obstacles = known_obstacles if known_obstacles is not None else []
    grid, grid_w, grid_h = create_occupancy_grid(WORKSPACE, obstacles)
    
    best_point = None
    best_dist = float('inf')
    
    for center in centers:
        cg = meters_to_grid(center[0], center[1])
        if not (0 <= cg[0] < grid_w and 0 <= cg[1] < grid_h): continue
        if grid[cg[1]][cg[0]] == 1: continue
        
        d = sqrt((center[0]-current_pos[0])**2 + (center[1]-current_pos[1])**2) + \
            sqrt((goal_pos[0]-center[0])**2 + (goal_pos[1]-center[1])**2)
        if d < best_dist:
            best_dist = d
            best_point = center
    return best_point

def find_nearest_valid(position, grid, w, h):
    gx, gy = meters_to_grid(position[0], position[1])
    if 0 <= gx < w and 0 <= gy < h and grid[gy][gx] == 0: return position
    
    for r in range(1, 21):
        for dx in range(-r, r+1):
            for dy in range(-r, r+1):
                if abs(dx)==r or abs(dy)==r:
                    tx, ty = gx+dx, gy+dy
                    if 0 <= tx < w and 0 <= ty < h and grid[ty][tx] == 0:
                        return grid_to_meters(tx, ty)
    return None

def execute_rotation(xbot_id, target_rad):
    try:
        status = xbot.get_xbot_status(xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
        curr_rz = float(status.feedback_position_si[5])
        delta = target_rad - curr_rz
        while delta > np.pi: delta -= 2*np.pi
        while delta < -np.pi: delta += 2*np.pi
        
        xbot.rotary_motion_p2p(
            cmd_label=9999, xbot_id=xbot_id, mode=pm.ROTATIONMODE.NO_ANGLE_WRAP,
            target_rz=target_rad, target_rz_vel=1.0, target_rz_acc=2.0,
            position_mode=pm.POSITIONMODE.ABSOLUTE
        )
        t_start = time.time()
        while time.time() - t_start < 30:
            s = xbot.get_xbot_status(xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
            if s.xbot_state == pm.XBOTSTATE.XBOT_ERROR: return False
            if abs(float(s.feedback_position_si[5]) - target_rad) < 0.02: return True
            time.sleep(0.05)
        return False
    except Exception as e:
        print(f"Rotation Error: {e}")
        return False

# Function to be called by PackML Execute
def perform_xbot_task(xbot_id, goal_pos, goal_rot, execute_topic_publisher):
    # This runs in a thread managed by PackMLSimulator
    print(f"XBot {xbot_id}: Task Started. Moving to {goal_pos}", flush=True)

    # 1. Activation
    with PMC_LOCK:
        if xbot_id not in ACTIVE_XBOT_IDS:
             if not activate_xbot(xbot_id):
                 raise Exception(f"Failed to activate XBot {xbot_id}")
             ACTIVE_XBOT_IDS.add(xbot_id)
    
    # 2. Planning Loop
    # We maintain current_path logic here locally
    max_replans = 5
    replan_count = 0
    
    while True:
        # Get Position
        curr_pos = get_xbot_position(xbot_id)
        if not curr_pos: raise Exception("Lost position")
        
        # Check Rotation Logic
        rot_point = None
        if goal_rot is not None:
            # Simple check if start/goal are centers
            # (Simplified from original for brevity, but logic holds)
            centers = get_flyway_centers()
            near_start = any(sqrt((curr_pos[0]-c[0])**2+(curr_pos[1]-c[1])**2)<0.01 for c in centers)
            near_goal = any(sqrt((goal_pos[0]-c[0])**2+(goal_pos[1]-c[1])**2)<0.01 for c in centers)
            
            if near_start:
                # Rotate HERE
                print(f"XBot {xbot_id}: Rotating at start", flush=True)
                if not execute_rotation(xbot_id, goal_rot): raise Exception("Rotation Failed")
                goal_rot = None # Done
            elif near_goal:
                rot_point = None # Rotate at end
            else:
                rot_point = select_rotation_point(curr_pos, goal_pos)
                if not rot_point: raise Exception("No rotation point found")
        
        # Obstacles
        others = []
        # Query all active IDs from PMC
        # Using PMC status for all xbots is safest
        
        # Plan Path
        # simplified obstacle detection based on known active bots
        active_ids_pmc = get_active_xbot_ids()
        for oid in active_ids_pmc:
            if oid != xbot_id:
                op = get_xbot_position(oid)
                if op: others.append(op)
        
        grid, gw, gh = create_occupancy_grid(WORKSPACE, others)
        
        # Plan to intermediate rotation or goal
        target_stage = rot_point if rot_point else goal_pos
        
        start_grid = meters_to_grid(curr_pos[0], curr_pos[1])
        target_grid = meters_to_grid(target_stage[0], target_stage[1])
        
        # Validation
        if grid[start_grid[1]][start_grid[0]] == 1:
            # Inside obstacle
            p = find_nearest_valid(curr_pos, grid, gw, gh)
            if p: 
                curr_pos = p
                start_grid = meters_to_grid(p[0], p[1])
            else:
                raise Exception("Stuck in obstacle")
        
        path_grid = astar_search(grid, start_grid, target_grid, gw, gh)
        if not path_grid: raise Exception("No path found")
        
        path_meters = grid_path_to_meters(simplify_path(path_grid))
        
        # Execution Loop for Path
        path_interrupted = False
        print(f"XBot {xbot_id}: Following Path ({len(path_meters)} pts)", flush=True)

        for i in range(len(path_meters)-1):
            pt_next = path_meters[i+1]
            
            # Send Linear Motion (X then Y)
            xbot.linear_motion_si(
                cmd_label=i*10, xbot_id=xbot_id, position_mode=pm.POSITIONMODE.ABSOLUTE,
                path_type=pm.LINEARPATHTYPE.XTHENY,
                target_xmeters=pt_next[0], target_ymeters=pt_next[1],
                final_speed_meters_ps=0.0, max_speed_meters_ps=0.5,
                max_acceleration_meters_ps2=1.0, corner_radius=0.0
            )
            
            # Wait loop
            t_move_start = time.time()
            while time.time() - t_move_start < 30:
                s = xbot.get_xbot_status(xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
                if s.xbot_state == pm.XBOTSTATE.XBOT_OBSTACLE_DETECTED:
                    # Collision
                    print(f"XBot {xbot_id}: Obstacle Detected!", flush=True)
                    xbot.stop_motion(xbot_id=xbot_id)
                    path_interrupted = True
                    break
                if s.xbot_state == pm.XBOTSTATE.XBOT_ERROR:
                     print(f"XBot {xbot_id}: Hardware Error!", flush=True)
                     raise Exception("XBot Error State")
                
                cp = s.feedback_position_si
                d = sqrt((float(cp[0])-pt_next[0])**2 + (float(cp[1])-pt_next[1])**2)
                if d < 0.005: break
                time.sleep(0.05)
            
            if path_interrupted: break
        
        if path_interrupted:
            replan_count += 1
            if replan_count > max_replans: raise Exception("Max replans reached")
            print(f"XBot {xbot_id}: Replanning...", flush=True)
            continue # Replan loop
            
        # If we reached here, we finished the path segment
        if rot_point:
            # We reached rotation point. Rotate.
            print(f"XBot {xbot_id}: Intermediate Rotation...", flush=True)
            if not execute_rotation(xbot_id, goal_rot): raise Exception("Rotation Failed")
            rot_point = None
            goal_rot = None
            continue # Plan next segment (curr -> goal)
        else:
            # We reached goal
            break

    # Final Rotation if needed at goal
    if goal_rot is not None:
         print(f"XBot {xbot_id}: Final Rotation...", flush=True)
         if not execute_rotation(xbot_id, goal_rot): raise Exception("Final Rotation Failed")
         
    print(f"XBot {xbot_id}: Task Complete", flush=True)
    return True

# --- Handlers ---

class PlanarSystemHandler:
    def __init__(self, sm):
        self.sm = sm
    
    def on_starting(self):
        print("System: Activating...", flush=True)
        # Activation is handled per-bot on demand or we can do bulk here
        # Original code did bulk activation on Start
        try:
            xbot.activate_xbots()
        except: pass
        
    def on_stopping(self):
        print("System: Stopping...", flush=True)
        try:
            xbot.deactivate_xbots()
            xbot.stop_motion(xbot_id=0) # 0 = all? No, check lib.
        except: pass
        
    def on_resetting(self):
        print("System: Resetting...", flush=True)
        # Clear globals?
        global ACTIVE_XBOT_IDS
        ACTIVE_XBOT_IDS.clear()

# --- Callbacks ---

def handle_xbot_motion_cmd(topic, client, message, properties, xbot_sm, xbot_id):
    """Callback for XBot CMD/XYMotion"""
    # 1. Extract Info
    print(f"XBot {xbot_id} Motion Callback triggered.", flush=True)
    uuid = message.get("Uuid")
    pos = message.get("Position") # [x, y, (rot)] in mm
    if not uuid or not pos: 
        print(f"XBot {xbot_id}: Invalid Message {message}", flush=True)
        return
    
    goal_pos = (float(pos[0]) / 1000.0, float(pos[1]) / 1000.0)  # Convert mm to m
    goal_rot = np.radians(float(pos[2])) if len(pos) > 2 else None
    
    # 2. Register (Occupy) - REMOVED
    # Logic is now: Occupy first (via CMD/Occupy), then Execute Motion
    # We rely on PackMLSimulator to verify occupation (uuids not empty)
    
    # 3. Trigger Execute
    # We define the process function
    def process_func(*args):
        # We pass self.interrupt_event if available?
        # PackMLSimulator checks signature. 
        perform_xbot_task(xbot_id, goal_pos, goal_rot, topic)
    
    # We call execute immediately. 
    # If the queue has only 1 item (this one), it will execute.
    print(f"XBot {xbot_id}: Queueing Execution for Task {uuid}", flush=True)
    
    # Note: If register_command put us in STARTING, we might need a brief sleep or retry
    # because execute_command checks for state==EXECUTE.
    # However, register_command calls transition_to(STARTING) -> starting_state -> transition_to(EXECUTE)
    # This likely happens synchronously in the main thread (or callback thread).
    # So state should be EXECUTE by now.
    
    xbot_sm.execute_command(message, topic, process_func)

def publish_positions_loop(proxy):
    """Background thread to publish XBot positions"""
    last_positions = {}
    print("Starting Position Publisher Loop...", flush=True)
    while True:
        try:
            timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            
            # We iterate 1-10. 
            # Note: Checking status for disconnected bots might timeout or fail fast.
            # We can use ACTIVE_XBOT_IDS to limit checks if performance is bad, 
            # but user might move bots manually/outside this script.
            # For now, let's try checking all keys in publishers dict.
            
            for xbot_id, publisher in XBOT_POS_PUBLISHERS.items():
                try:
                    # feedback_type=1 is POSITION (check pmc_types if available, assuming 1)
                    # Using xbot.get_xbot_status(xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
                    # We need to acquire lock? PMC calls are likely thread-safe in C++ lib but let's be careful.
                    # xbot_controller functions don't use lock except for activation in our code.
                    
                    s = xbot.get_xbot_status(xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
                    
                    # Check if valid
                    # If xbot_state is error or not connected, maybe skip?
                    # s.feedback_position_si is [x, y, z, rx, ry, rz]
                    
                    if s and hasattr(s, 'feedback_position_si'):
                        pos = s.feedback_position_si
                        x = round(float(pos[0]) * 1000.0, 3)  # Convert m to mm
                        y = round(float(pos[1]) * 1000.0, 3)  # Convert m to mm
                        theta = round(np.degrees(float(pos[5])), 3) # Convert Rad to Deg for MQTT, round to 3
                        
                        current_pos_list = [x, y, theta]
                        
                        # Check change (Threshold: 1mm, 0.1 deg)
                        last = last_positions.get(xbot_id)
                        changed = False
                        if last is None:
                            changed = True
                        elif (abs(last[0]-x) > 1.0 or  # 1mm threshold in mm units
                              abs(last[1]-y) > 1.0 or  # 1mm threshold in mm units
                              abs(last[2]-theta) > 0.1):
                            changed = True
                            
                        if changed:
                            payload = {
                                "Position": current_pos_list,
                                "TimeStamp": timestamp
                            }
                            # Publisher.publish(payload, client, retain)
                            publisher.publish(payload, proxy, False)
                            last_positions[xbot_id] = current_pos_list

                except Exception as inner_e:
                    # Often fails if bot not connected
                    pass
                    
            time.sleep(0.1) # 10Hz limit
            
        except Exception as e:
            print(f"Position Loop Error: {e}", flush=True)
            time.sleep(1)

def main():
    print("=== Planar Controller V2 (PackML) ===", flush=True)
    
    # 1. Connect PMC
    pmc_ip = os.environ.get("PMC_IP")
    if not connect_to_pmc(pmc_ip):
        print("Failed to connect to PMC", flush=True)
        return

    global WORKSPACE
    WORKSPACE = load_workspace_from_pmc(pmc_sys)
    if not WORKSPACE: return

    # 2. Setup Proxy
    # Topic list
    topics = []
    
    # 3. System SM
    # Use Empty list for initial proxy init, we will register later
    proxy = Proxy(MQTT_BROKER, MQTT_PORT, "PlanarController", [])
    
    # System Controller (No Occupation Logic)
    sys_handlers = PlanarSystemHandler(None)
    system_sm = PackMLStateMachine(
        MQTT_BASE_TOPIC, 
        proxy, 
        None, 
        config_path="planarTable.yaml",
        use_occupation_logic=False,
        custom_handlers={
            'on_starting': sys_handlers.on_starting,
            'on_stopping': sys_handlers.on_stopping,
            'on_resetting': sys_handlers.on_resetting
        }
    )
    sys_handlers.sm = system_sm
    proxy.on_ready(system_sm.register_asset)
    
    # 4. XBot SMs
    xbot_sms = {}
    
    # Dynamic detection via global function or updated lib function
    print("Scanning for detected XBots...", flush=True)
    detected_ids = get_active_xbot_ids()
    
    # Handle Case where XBot reports ID 0 (Map to 1)
    if detected_ids and 0 in detected_ids:
        print("Detected ID 0. Mapping to ID 1.", flush=True)
        detected_ids = [1 if x == 0 else x for x in detected_ids]
    
    if not detected_ids:
        print("No XBots detected! Defaulting to 1-10 scan...", flush=True)
        detected_ids = list(range(1, 11))
    else:
        print(f"Detected XBots: {detected_ids}", flush=True)
        
    for i in detected_ids: 
        xb_topic_base = f"{MQTT_BASE_TOPIC}/Xbot{i}"
        
        # XBot SM (Use Occupation Logic)
        xb_sm = PackMLStateMachine(
            xb_topic_base,
            proxy,
            None,
            config_path=f"planarShuttle{i}.yaml",
            use_occupation_logic=True
        )
        xbot_sms[i] = xb_sm
        proxy.on_ready(xb_sm.register_asset)
        
        # XBot Motion Topic
        # We need a Topic object to subscribe
        # PackMLSimulator.ResponseAsync is good
        mot_topic = ResponseAsync(
            f"{xb_topic_base}/DATA/XYMotion",
            f"{xb_topic_base}/CMD/XYMotion",
            "./MQTTSchemas/commandResponse.schema.json", # Standard PackML Response
            "./MQTTSchemas/moveToPosition.schema.json", # Command Schema
            2,
            # Callback is wrapped to include sm and id
            lambda t, c, m, p, sm=xb_sm, xid=i: handle_xbot_motion_cmd(t, c, m, p, sm, xid)
        )
        proxy.register_topic(mot_topic)
        
        # Position Publisher
        pos_topic = Publisher(
            f"{xb_topic_base}/DATA/Position",
            "./MQTTSchemas/position.schema.json",
            0
        )
        proxy.register_topic(pos_topic)
        XBOT_POS_PUBLISHERS[i] = pos_topic
        
    # 5. Position Thread
    pos_thread = threading.Thread(target=publish_positions_loop, args=(proxy,), daemon=True)
    pos_thread.start()

    # 6. Loop
    print("Starting MQTT Loop...", flush=True)
    proxy.loop_forever()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        disconnect_from_pmc()

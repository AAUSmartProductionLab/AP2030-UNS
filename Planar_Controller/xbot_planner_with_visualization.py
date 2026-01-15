import sys
import time
import json
import threading
import os
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from math import sqrt
from datetime import datetime
import paho.mqtt.client as mqtt

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
    FLYWAY_SIZE_M,
    ROBOT_SIZE_M
)
from library.astar_pathfinding import astar_search
from library.path_simplifier import simplify_path, merge_collinear_segments

matplotlib.use('TkAgg')

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_BASE_TOPIC = "NN/Nybrovej/InnoLab/Planar"

POSITION_TOLERANCE_M = 0.005

# XBot State to PackML State mapping
# Based on: https://planarmotor.atlassian.net/wiki/spaces/pmdoc/pages/131011844/XBot+State+Descriptions
XBOT_STATE_TO_PACKML = {
    pm.XBOTSTATE.XBOT_IDLE: "Idle",
    pm.XBOTSTATE.XBOT_OBSTACLE_DETECTED: "Held",
    pm.XBOTSTATE.XBOT_ERROR: "Aborted",
    pm.XBOTSTATE.XBOT_STOPPED: "Stopped",
}


class XBotTask:
    """XBot state holder with MQTT task tracking."""

    def __init__(self, xbot_id, goal_pos, uuid, goal_rotation=None):
        self.xbot_id = xbot_id
        self.goal_pos = goal_pos
        # Target rotation in radians (optional)
        self.goal_rotation = goal_rotation
        self.uuid = uuid
        self.current_path = []
        self.rotation_point = None  # Flyway center for rotation (x, y)
        self.current_waypoint_index = 0
        self.reached_goal = False
        self.current_packml_state = "Idle"
        self.last_reported_state = None


class SimpleController:
    """Simple sequential controller with MQTT integration."""

    def __init__(self, workspace, mqtt_client, enable_visualization=True):
        self.workspace = workspace
        self.xbots = {}
        self.obstacle_xbots = []  # List of (x, y) positions of obstacle XBots
        self.fig = None
        self.ax = None
        self.mqtt_client = mqtt_client
        self.enable_visualization = enable_visualization
        self.task_queue = []
        self.task_lock = threading.Lock()
        self.active_xbots = set()

    def publish_state(self, xbot_id, packml_state):
        """Publish PackML state via MQTT."""
        xbot_obj = self.xbots.get(xbot_id)
        if not xbot_obj:
            return

        # Only publish if state changed or if it's a completion state
        if packml_state == xbot_obj.last_reported_state and packml_state != "Complete":
            return

        xbot_obj.current_packml_state = packml_state
        xbot_obj.last_reported_state = packml_state

        topic = f"{MQTT_BASE_TOPIC}/Xbot{xbot_id}/DATA/State"
        payload = {
            "State": packml_state,
            "TimeStamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Only include Uuid if it's not None
        if xbot_obj.uuid is not None:
            payload["Uuid"] = xbot_obj.uuid

        try:
            self.mqtt_client.publish(topic, json.dumps(payload), qos=1)
            print(
                f"  [MQTT] Published state '{packml_state}' for XBot {xbot_id}")
        except Exception as e:
            print(f"  [MQTT] ERROR publishing state: {e}")

    def add_xbot_task(self, xbot_id, goal_pos, uuid, goal_rotation=None):
        """Add an XBot task to manage."""
        self.xbots[xbot_id] = XBotTask(xbot_id, goal_pos, uuid, goal_rotation)
        self.publish_state(xbot_id, "Idle")

    def get_flyway_centers(self):
        """
        Get all valid flyway centers (rotation points).
        Flyways are 240mm x 240mm, centers are at 120mm, 360mm, 600mm, etc.
        """
        workspace_width_m = self.workspace['width'] * FLYWAY_SIZE_M
        workspace_height_m = self.workspace['height'] * FLYWAY_SIZE_M

        centers = []
        half_flyway = FLYWAY_SIZE_M / 2  # 0.12m

        # Generate all flyway centers
        x = half_flyway
        while x < workspace_width_m:
            y = half_flyway
            while y < workspace_height_m:
                # Check if this center is in a hole
                col = int(x / FLYWAY_SIZE_M)
                row = int(y / FLYWAY_SIZE_M)

                is_hole = False
                if 'holes' in self.workspace:
                    for hole in self.workspace['holes']:
                        if hole[0] == col and hole[1] == row:
                            is_hole = True
                            break

                if not is_hole:
                    centers.append((x, y))

                y += FLYWAY_SIZE_M
            x += FLYWAY_SIZE_M

        return centers

    def select_rotation_point(self, current_pos, goal_pos):
        """
        Select the best rotation point (flyway center) considering:
        1. Must be reachable from current position (no obstacles)
        2. Goal must be reachable from rotation point (no obstacles)
        3. Minimize total distance: current -> rotation point -> goal

        Returns:
            (x, y) of selected rotation point, or None if rotation not needed
        """
        centers = self.get_flyway_centers()

        # Create grid for path checking
        grid, grid_width, grid_height = create_occupancy_grid(
            self.workspace, self.obstacle_xbots)

        best_point = None
        best_total_dist = float('inf')

        current_grid = meters_to_grid(current_pos[0], current_pos[1])
        goal_grid = meters_to_grid(goal_pos[0], goal_pos[1])

        for center in centers:
            center_grid = meters_to_grid(center[0], center[1])

            # Check if center itself is valid
            if not (0 <= center_grid[0] < grid_width and 0 <= center_grid[1] < grid_height):
                continue
            if grid[center_grid[1]][center_grid[0]] == 1:
                continue

            # Check if path exists: current -> center
            path1 = astar_search(grid, current_grid,
                                 center_grid, grid_width, grid_height)
            if not path1:
                continue

            # Check if path exists: center -> goal
            path2 = astar_search(
                grid, center_grid, goal_grid, grid_width, grid_height)
            if not path2:
                continue

            # Calculate total distance
            dist_to_center = sqrt(
                (center[0] - current_pos[0])**2 + (center[1] - current_pos[1])**2)
            dist_to_goal = sqrt(
                (goal_pos[0] - center[0])**2 + (goal_pos[1] - center[1])**2)
            total_dist = dist_to_center + dist_to_goal

            if total_dist < best_total_dist:
                best_total_dist = total_dist
                best_point = center

        return best_point

    def visualize(self, xbot_id):
        """Visualize the planning - creates new plot when replanning."""
        if not self.enable_visualization:
            return

        # Close old figure if exists
        if self.fig is not None:
            plt.close(self.fig)

        # Create new figure
        self.fig, self.ax = plt.subplots(figsize=(12, 10))

        # Calculate workspace size
        workspace_width_m = self.workspace['width'] * FLYWAY_SIZE_M
        workspace_height_m = self.workspace['height'] * FLYWAY_SIZE_M

        self.ax.set_xlim(0, workspace_width_m)
        self.ax.set_ylim(0, workspace_height_m)
        self.ax.set_aspect('equal')

        self.ax.set_xlabel('X (meters)', fontsize=12)
        self.ax.set_ylabel('Y (meters)', fontsize=12)

        # Title
        title = f'XBot {xbot_id} Planning'
        if self.obstacle_xbots:
            title += f' - {len(self.obstacle_xbots)} obstacle(s)'
        self.ax.set_title(title, fontsize=14, fontweight='bold')

        # Draw layout holes
        if 'holes' in self.workspace:
            for hole in self.workspace['holes']:
                col, row = hole
                x = col * FLYWAY_SIZE_M
                y = row * FLYWAY_SIZE_M
                hole_rect = patches.Rectangle(
                    (x, y), FLYWAY_SIZE_M, FLYWAY_SIZE_M,
                    color='gray', alpha=0.3, label='Layout Hole' if hole == self.workspace['holes'][0] else ''
                )
                self.ax.add_patch(hole_rect)

        # Draw obstacle XBots as squares
        for obs_x, obs_y in self.obstacle_xbots:
            obs_square = patches.Rectangle(
                (obs_x - ROBOT_SIZE_M/2, obs_y - ROBOT_SIZE_M/2),
                ROBOT_SIZE_M, ROBOT_SIZE_M,
                color='orange', alpha=0.7, zorder=3
            )
            self.ax.add_patch(obs_square)

            self.ax.text(obs_x, obs_y - ROBOT_SIZE_M/2 - 0.02, 'Obstacle',
                         ha='center', va='top', fontsize=9, color='orange', weight='bold')

        # Draw moving XBot as a POINT for clarity
        pos = get_xbot_position(xbot_id)
        if pos:
            robot_point = patches.Circle(
                pos, 0.015, color='blue', alpha=0.9, zorder=4
            )
            self.ax.add_patch(robot_point)
            self.ax.text(pos[0] + 0.03, pos[1] + 0.03, f'XBot {xbot_id}',
                         ha='left', va='bottom', fontsize=10, color='blue', weight='bold')

        # Draw rotation point if present
        xbot_obj = self.xbots[xbot_id]
        if xbot_obj.rotation_point:
            rot_marker = patches.Circle(
                xbot_obj.rotation_point, 0.025, color='purple', alpha=0.7, zorder=3
            )
            self.ax.add_patch(rot_marker)
            self.ax.text(xbot_obj.rotation_point[0] + 0.03, xbot_obj.rotation_point[1] + 0.03,
                         'Rotation', ha='left', va='bottom', fontsize=10, color='purple', weight='bold')

        # Draw goal marker
        goal_marker = patches.Circle(
            xbot_obj.goal_pos, 0.02, color='green', alpha=0.7, zorder=3
        )
        self.ax.add_patch(goal_marker)
        self.ax.text(xbot_obj.goal_pos[0] + 0.03, xbot_obj.goal_pos[1] + 0.03, 'Goal',
                     ha='left', va='bottom', fontsize=10, color='green', weight='bold')

        # Draw planned path
        if xbot_obj.current_path and len(xbot_obj.current_path) > 1:
            path_x = [p[0] for p in xbot_obj.current_path]
            path_y = [p[1] for p in xbot_obj.current_path]
            self.ax.plot(path_x, path_y, 'g-', linewidth=2, marker='o',
                         markersize=5, label='Planned Path', zorder=2)

            # Label waypoints
            for i, (x, y) in enumerate(xbot_obj.current_path):
                self.ax.text(x + 0.01, y + 0.01, f'{i}',
                             fontsize=8, color='green', weight='bold')

        self.ax.legend()
        plt.draw()
        plt.pause(0.01)  # Minimal pause for display

    def find_nearest_valid_position(self, position, grid, grid_width, grid_height, max_search_radius=20):
        """Find nearest valid grid position if current position is invalid."""
        start_grid_x, start_grid_y = meters_to_grid(position[0], position[1])

        # Check if current position is already valid
        if 0 <= start_grid_x < grid_width and 0 <= start_grid_y < grid_height:
            if grid[start_grid_y][start_grid_x] == 0:
                return position

        # Search in expanding squares for nearest valid cell
        for radius in range(1, max_search_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) == radius or abs(dy) == radius:  # Only check perimeter
                        check_x = start_grid_x + dx
                        check_y = start_grid_y + dy

                        if 0 <= check_x < grid_width and 0 <= check_y < grid_height:
                            if grid[check_y][check_x] == 0:
                                # Found valid position, convert back to meters
                                valid_pos = grid_to_meters(check_x, check_y)
                                print(
                                    f"  Adjusted start position from ({position[0]:.3f}, {position[1]:.3f}) to ({valid_pos[0]:.3f}, {valid_pos[1]:.3f})")
                                return valid_pos

        return None  # No valid position found

    def plan_path(self, xbot_id):
        """Plan or replan path for an XBot, including rotation if needed."""
        xbot_obj = self.xbots[xbot_id]

        current_pos = get_xbot_position(xbot_id)
        if not current_pos:
            print(f"ERROR: Cannot get position for XBot {xbot_id}")
            return False

        print(
            f"\nPlanning path for XBot {xbot_id} from ({current_pos[0]:.3f}, {current_pos[1]:.3f}) to ({xbot_obj.goal_pos[0]:.3f}, {xbot_obj.goal_pos[1]:.3f})")
        if xbot_obj.goal_rotation is not None:
            print(
                f"  Target rotation: {xbot_obj.goal_rotation:.3f} radians ({np.degrees(xbot_obj.goal_rotation):.1f}°)")
        if self.obstacle_xbots:
            print(f"  Avoiding {len(self.obstacle_xbots)} obstacle(s)")

        # If rotation is required, first check if already at target rotation
        if xbot_obj.goal_rotation is not None:
            try:
                status = xbot.get_xbot_status(
                    xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
                current_rz = float(
                    status.feedback_position_si[5])  # RZ is index 5

                # Check if already at target rotation (within 1 degree tolerance)
                rz_error = abs(current_rz - xbot_obj.goal_rotation)
                # Handle wraparound for angles
                if rz_error > np.pi:
                    rz_error = 2 * np.pi - rz_error

                if rz_error < np.radians(1.0):
                    print(
                        f"  Already at target rotation ({np.degrees(current_rz):.1f}°) - skipping rotation")
                    xbot_obj.goal_rotation = None  # Clear rotation requirement
            except Exception as e:
                print(f"  WARNING: Could not check current rotation: {e}")

        # If rotation is required, check if start or goal is at a flyway center
        if xbot_obj.goal_rotation is not None:
            flyway_centers = self.get_flyway_centers()
            rotation_point_found = False

            # Priority 1: Check if current position is at a flyway center
            for center in flyway_centers:
                dist = sqrt((current_pos[0] - center[0])
                            ** 2 + (current_pos[1] - center[1])**2)
                if dist < 0.01:  # Within 10mm of center
                    xbot_obj.rotation_point = center
                    rotation_point_found = True
                    print(
                        f"  Current position is at flyway center: ({center[0]:.3f}, {center[1]:.3f}) - will rotate here")
                    break

            # Priority 2: Check if goal position is at a flyway center
            if not rotation_point_found:
                for center in flyway_centers:
                    dist = sqrt(
                        (xbot_obj.goal_pos[0] - center[0])**2 + (xbot_obj.goal_pos[1] - center[1])**2)
                    if dist < 0.01:  # Within 10mm of center
                        xbot_obj.rotation_point = center
                        rotation_point_found = True
                        print(
                            f"  Goal position is at flyway center: ({center[0]:.3f}, {center[1]:.3f}) - will rotate there")
                        break

            # Priority 3: Find best intermediate rotation point
            if not rotation_point_found:
                rotation_point = self.select_rotation_point(
                    current_pos, xbot_obj.goal_pos)
                if not rotation_point:
                    print(f"ERROR: No valid rotation point found")
                    self.publish_state(xbot_id, "Aborted")
                    return False
                xbot_obj.rotation_point = rotation_point
                print(
                    f"  Selected intermediate rotation point: ({rotation_point[0]:.3f}, {rotation_point[1]:.3f})")

        # Create grid with obstacle XBots
        grid, grid_width, grid_height = create_occupancy_grid(
            self.workspace, self.obstacle_xbots)

        # Check if current position is valid, find nearest valid if not
        start_grid = meters_to_grid(current_pos[0], current_pos[1])
        if 0 <= start_grid[0] < grid_width and 0 <= start_grid[1] < grid_height:
            if grid[start_grid[1]][start_grid[0]] == 1:
                print(f"  WARNING: Current position is inside obstacle zone!")
                adjusted_pos = self.find_nearest_valid_position(
                    current_pos, grid, grid_width, grid_height)
                if adjusted_pos:
                    current_pos = adjusted_pos
                    start_grid = meters_to_grid(current_pos[0], current_pos[1])
                else:
                    print(f"ERROR: Cannot find valid start position")
                    self.publish_state(xbot_id, "Aborted")
                    return False

        # Plan path based on whether rotation is needed
        if xbot_obj.rotation_point:
            rotation_grid = meters_to_grid(
                xbot_obj.rotation_point[0], xbot_obj.rotation_point[1])
            goal_grid = meters_to_grid(
                xbot_obj.goal_pos[0], xbot_obj.goal_pos[1])

            # Check if rotation point is at current position
            dist_current_to_rot = sqrt(
                (current_pos[0] - xbot_obj.rotation_point[0])**2 +
                (current_pos[1] - xbot_obj.rotation_point[1])**2)

            # Check if rotation point is at goal position
            dist_rot_to_goal = sqrt(
                (xbot_obj.rotation_point[0] - xbot_obj.goal_pos[0])**2 +
                (xbot_obj.rotation_point[1] - xbot_obj.goal_pos[1])**2)

            if dist_current_to_rot < 0.01:
                # Rotation point is current position: rotate first, then move to goal
                print(f"  Path: Rotate at current position, then move to goal")
                goal_path = astar_search(
                    grid, rotation_grid, goal_grid, grid_width, grid_height)
                if not goal_path:
                    print(f"ERROR: No path from current position to goal")
                    self.publish_state(xbot_id, "Aborted")
                    return False
                simplified = simplify_path(goal_path)
                path_meters = grid_path_to_meters(simplified)

            elif dist_rot_to_goal < 0.01:
                # Rotation point is goal position: move to goal, then rotate
                print(f"  Path: Move to goal, then rotate")
                goal_path = astar_search(
                    grid, start_grid, goal_grid, grid_width, grid_height)
                if not goal_path:
                    print(f"ERROR: No path to goal")
                    self.publish_state(xbot_id, "Aborted")
                    return False
                simplified = simplify_path(goal_path)
                path_meters = grid_path_to_meters(simplified)

            else:
                # Rotation point is intermediate: current -> rotation point -> goal
                print(f"  Path: Move to rotation point, rotate, then move to goal")

                # Path segment 1: current -> rotation point
                path1 = astar_search(
                    grid, start_grid, rotation_grid, grid_width, grid_height)
                if not path1:
                    print(f"ERROR: No path to rotation point")
                    self.publish_state(xbot_id, "Aborted")
                    return False

                # Path segment 2: rotation point -> goal
                path2 = astar_search(grid, rotation_grid,
                                     goal_grid, grid_width, grid_height)
                if not path2:
                    print(f"ERROR: No path from rotation point to goal")
                    self.publish_state(xbot_id, "Aborted")
                    return False

                # Combine paths (remove duplicate rotation point)
                combined_path = path1 + path2[1:]
                simplified = simplify_path(combined_path)
                path_meters = grid_path_to_meters(simplified)

            print(f"  Planned path: {len(path_meters)} waypoints")
        else:
            # Direct path: current -> goal
            goal_grid = meters_to_grid(
                xbot_obj.goal_pos[0], xbot_obj.goal_pos[1])

            grid_path = astar_search(
                grid, start_grid, goal_grid, grid_width, grid_height)
            if not grid_path:
                print(f"ERROR: No path found for XBot {xbot_id}")
                self.publish_state(xbot_id, "Aborted")
                return False

            simplified = simplify_path(grid_path)
            path_meters = grid_path_to_meters(simplified)

            # Merge collinear segments (only if no obstacles - otherwise unsafe)
            if not self.obstacle_xbots:
                path_meters = merge_collinear_segments(
                    path_meters, self.workspace)

            print(f"  Planned path with {len(path_meters)} waypoints")

        xbot_obj.current_path = path_meters
        xbot_obj.current_waypoint_index = 0

        # Visualize
        self.visualize(xbot_id)

        return True

    def execute_rotation(self, xbot_id, target_rotation_rad):
        """
        Execute rotation at current position (must be at flyway center).
        Uses shortest angular path to target rotation.

        Args:
            xbot_id: XBot ID
            target_rotation_rad: Target rotation in radians

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current rotation
            status = xbot.get_xbot_status(
                xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
            current_rz = float(status.feedback_position_si[5])  # RZ is index 5

            # Calculate shortest angular distance
            delta = target_rotation_rad - current_rz
            # Normalize to [-pi, pi]
            while delta > np.pi:
                delta -= 2 * np.pi
            while delta < -np.pi:
                delta += 2 * np.pi

            direction_str = "CCW" if delta > 0 else "CW"
            print(
                f"    Rotating {abs(np.degrees(delta)):.1f}° {direction_str}")

            # Execute rotation command (NO_ANGLE_WRAP = shortest path)
            xbot.rotary_motion_p2p(
                cmd_label=9999,  # Special label for rotation
                xbot_id=xbot_id,
                mode=pm.ROTATIONMODE.NO_ANGLE_WRAP,  # Shortest angular path
                target_rz=target_rotation_rad,
                target_rz_vel=1.0,  # Max velocity (rad/s) ~57 deg/s
                target_rz_acc=2.0,  # Acceleration (rad/s^2)
                position_mode=pm.POSITIONMODE.ABSOLUTE
            )

            # Wait for rotation completion
            timeout = 30.0
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = xbot.get_xbot_status(
                    xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
                current_rz = float(status.feedback_position_si[5])

                # Check for errors
                if status.xbot_state == pm.XBOTSTATE.XBOT_ERROR:
                    print(f"    ERROR during rotation")
                    return False

                # Check if rotation complete (within 1 degree)
                rz_error = abs(current_rz - target_rotation_rad)
                if rz_error < np.radians(1.0):
                    print(f"    Rotation complete")
                    return True

                time.sleep(0.05)

            print(f"    ERROR: Rotation timeout")
            return False

        except Exception as e:
            print(f"    ERROR during rotation: {e}")
            return False

    def execute_xbot(self, xbot_id):
        """
        Execute a single XBot's path with collision handling and state reporting.

        Returns:
            True: Successfully reached goal
            False: Failed (no path, hardware error, etc.)
        """
        xbot_obj = self.xbots[xbot_id]
        max_replans = 5
        replan_count = 0

        # Publish starting state
        self.publish_state(xbot_id, "Execute")

        # Check if we need to rotate at the starting position
        if xbot_obj.rotation_point and xbot_obj.goal_rotation is not None:
            current_pos = get_xbot_position(xbot_id)
            if current_pos:
                dist_to_rot_point = sqrt(
                    (current_pos[0] - xbot_obj.rotation_point[0])**2 +
                    (current_pos[1] - xbot_obj.rotation_point[1])**2)

                # If rotation point is at current position, rotate first
                if dist_to_rot_point < 0.01:
                    print(
                        f"  Rotating at current position to {np.degrees(xbot_obj.goal_rotation):.1f}°")
                    if not self.execute_rotation(xbot_id, xbot_obj.goal_rotation):
                        print(f"ERROR: Rotation failed")
                        self.publish_state(xbot_id, "Aborted")
                        return False
                    # Clear rotation point so we don't rotate again
                    xbot_obj.rotation_point = None
                    xbot_obj.goal_rotation = None

        # Special case: If already at goal position and no movement needed
        if len(xbot_obj.current_path) == 1:
            current_pos = get_xbot_position(xbot_id)
            if current_pos:
                dist_to_goal = sqrt(
                    (current_pos[0] - xbot_obj.goal_pos[0])**2 +
                    (current_pos[1] - xbot_obj.goal_pos[1])**2)
                if dist_to_goal < 0.01:  # Already at goal position
                    print(f"\nXBot {xbot_id} reached goal!")
                    xbot_obj.reached_goal = True
                    self.publish_state(xbot_id, "Complete")
                    return True

        while xbot_obj.current_waypoint_index < len(xbot_obj.current_path) - 1:
            current = xbot_obj.current_path[xbot_obj.current_waypoint_index]
            target = xbot_obj.current_path[xbot_obj.current_waypoint_index + 1]

            print(
                f"  Moving to waypoint {xbot_obj.current_waypoint_index + 1}/{len(xbot_obj.current_path) - 1}: ({target[0]:.3f}, {target[1]:.3f})")

            # Move axis-aligned: X first, then Y
            current_pos = get_xbot_position(xbot_id)
            if not current_pos:
                print(f"ERROR: Cannot get position for XBot {xbot_id}")
                self.publish_state(xbot_id, "Aborted")
                return False

            dx = abs(target[0] - current_pos[0])
            dy = abs(target[1] - current_pos[1])

            collision_detected = False

            # Move X if needed
            if dx > 0.001:
                print(f"    Moving X: {current_pos[0]:.3f} -> {target[0]:.3f}")

                xbot.linear_motion_si(
                    cmd_label=xbot_obj.current_waypoint_index * 10 + 1,
                    xbot_id=xbot_id,
                    position_mode=pm.POSITIONMODE.ABSOLUTE,
                    path_type=pm.LINEARPATHTYPE.XTHENY,
                    target_xmeters=target[0],
                    target_ymeters=current_pos[1],
                    final_speed_meters_ps=0.0,
                    max_speed_meters_ps=0.5,
                    max_acceleration_meters_ps2=1.0,
                    corner_radius=0.0
                )

                # Wait for X move completion
                timeout = 30.0
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        status = xbot.get_xbot_status(
                            xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
                        pos = status.feedback_position_si
                        current_x, current_y = float(pos[0]), float(pos[1])

                        if status.xbot_state == pm.XBOTSTATE.XBOT_OBSTACLE_DETECTED:
                            print("    COLLISION DETECTED in X move!")
                            collision_detected = True
                            self.publish_state(xbot_id, "Held")
                            break

                        # Check if X move complete
                        if abs(current_x - target[0]) < POSITION_TOLERANCE_M:
                            break

                        time.sleep(0.05)

                    except KeyboardInterrupt:
                        print("\n\nInterrupted by user!")
                        xbot.stop_motion(xbot_id=xbot_id)
                        self.publish_state(xbot_id, "Stopped")
                        raise
                    except Exception as e:
                        print(f"ERROR: Exception during X move: {e}")
                        collision_detected = True
                        self.publish_state(xbot_id, "Aborted")
                        break

            # Move Y if needed (and no collision in X)
            if not collision_detected and dy > 0.001:
                current_pos = get_xbot_position(xbot_id)
                if not current_pos:
                    print(f"ERROR: Cannot get position for XBot {xbot_id}")
                    self.publish_state(xbot_id, "Aborted")
                    return False

                print(f"    Moving Y: {current_pos[1]:.3f} -> {target[1]:.3f}")

                xbot.linear_motion_si(
                    cmd_label=xbot_obj.current_waypoint_index * 10 + 2,
                    xbot_id=xbot_id,
                    position_mode=pm.POSITIONMODE.ABSOLUTE,
                    path_type=pm.LINEARPATHTYPE.XTHENY,
                    target_xmeters=target[0],
                    target_ymeters=target[1],
                    final_speed_meters_ps=0.0,
                    max_speed_meters_ps=0.5,
                    max_acceleration_meters_ps2=1.0,
                    corner_radius=0.0
                )

                # Wait for Y move completion
                timeout = 30.0
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        status = xbot.get_xbot_status(
                            xbot_id=xbot_id, feedback_type=pm.FEEDBACKOPTION.POSITION)
                        pos = status.feedback_position_si
                        current_x, current_y = float(pos[0]), float(pos[1])

                        if status.xbot_state == pm.XBOTSTATE.XBOT_OBSTACLE_DETECTED:
                            print("    COLLISION DETECTED in Y move!")
                            collision_detected = True
                            self.publish_state(xbot_id, "Held")
                            break

                        # Check if reached final target
                        dist = sqrt(
                            (current_x - target[0])**2 + (current_y - target[1])**2)
                        if dist < POSITION_TOLERANCE_M:
                            xbot_obj.current_waypoint_index += 1

                            # Check if we just reached the rotation point
                            if xbot_obj.rotation_point and xbot_obj.goal_rotation is not None:
                                rot_dist = sqrt(
                                    (current_x - xbot_obj.rotation_point[0])**2 +
                                    (current_y - xbot_obj.rotation_point[1])**2)
                                if rot_dist < 0.01:  # Within 10mm of rotation point
                                    print(
                                        f"  Reached rotation point, rotating to {np.degrees(xbot_obj.goal_rotation):.1f}°")
                                    if not self.execute_rotation(xbot_id, xbot_obj.goal_rotation):
                                        print(f"ERROR: Rotation failed")
                                        self.publish_state(xbot_id, "Aborted")
                                        return False
                                    # Clear rotation point so we don't rotate again
                                    xbot_obj.rotation_point = None

                            self.publish_state(xbot_id, "Execute")
                            break

                        time.sleep(0.05)

                    except KeyboardInterrupt:
                        print("\n\nInterrupted by user!")
                        xbot.stop_motion(xbot_id=xbot_id)
                        self.publish_state(xbot_id, "Stopped")
                        raise
                    except Exception as e:
                        print(f"ERROR: Exception during Y move: {e}")
                        collision_detected = True
                        self.publish_state(xbot_id, "Aborted")
                        break
            elif not collision_detected:
                # No Y move needed, just increment waypoint
                xbot_obj.current_waypoint_index += 1

            # Handle collision: add obstacle and replan
            if collision_detected:
                if replan_count >= max_replans:
                    print(f"ERROR: Max replans ({max_replans}) reached")
                    self.publish_state(xbot_id, "Aborted")
                    return False

                # Stop XBot
                xbot.stop_motion(xbot_id=xbot_id)
                time.sleep(0.3)

                collision_pos = get_xbot_position(xbot_id)
                if not collision_pos:
                    print("ERROR: Cannot get XBot position")
                    self.publish_state(xbot_id, "Aborted")
                    return False

                print(
                    f"  Collision at: ({collision_pos[0]:.3f}, {collision_pos[1]:.3f})")

                print(
                    f"\n  Replanning around obstacle (attempt {replan_count + 1}/{max_replans})...")

                # Find all other XBots and add as obstacles
                all_xbot_ids = get_active_xbot_ids()

                for other_id in all_xbot_ids:
                    if other_id != xbot_id:
                        other_pos = get_xbot_position(other_id)
                        if other_pos:
                            # Add to obstacle list if not already there
                            if other_pos not in self.obstacle_xbots:
                                print(
                                    f"    Adding XBot {other_id} at ({other_pos[0]:.3f}, {other_pos[1]:.3f}) as obstacle")
                                self.obstacle_xbots.append(other_pos)

                # Replan from current position
                if not self.plan_path(xbot_id):
                    print("ERROR: Replanning failed")
                    self.publish_state(xbot_id, "Aborted")
                    return False

                # Back to Execute state after successful replan
                self.publish_state(xbot_id, "Execute")
                replan_count += 1
                continue  # Start from beginning of new path

        # Reached goal position - check if rotation needed at goal
        print(f"\nXBot {xbot_id} reached goal position!")

        # Check if we need to rotate at the goal position
        if xbot_obj.rotation_point and xbot_obj.goal_rotation is not None:
            current_pos = get_xbot_position(xbot_id)
            if current_pos:
                dist_to_rot_point = sqrt(
                    (current_pos[0] - xbot_obj.rotation_point[0])**2 +
                    (current_pos[1] - xbot_obj.rotation_point[1])**2)

                # If rotation point is at current position (goal), rotate now
                if dist_to_rot_point < 0.01:
                    print(
                        f"  Rotating at goal position to {np.degrees(xbot_obj.goal_rotation):.1f}°")
                    if not self.execute_rotation(xbot_id, xbot_obj.goal_rotation):
                        print(f"ERROR: Rotation failed")
                        self.publish_state(xbot_id, "Aborted")
                        return False

        xbot_obj.reached_goal = True
        self.publish_state(xbot_id, "Complete")
        return True

    def process_task_queue(self):
        """Process tasks from the queue."""
        while True:
            with self.task_lock:
                if len(self.task_queue) == 0:
                    time.sleep(0.1)
                    continue

                # Get next task
                task = self.task_queue.pop(0)
                xbot_id = task['xbot_id']
                goal_pos = task['goal_pos']
                uuid = task['uuid']
                goal_rotation = task.get('goal_rotation', None)

            print(f"\n=== Processing task for XBot {xbot_id} ===")
            print(f"UUID: {uuid}")
            print(f"Goal: ({goal_pos[0]:.3f}, {goal_pos[1]:.3f})")
            if goal_rotation is not None:
                print(f"Rotation: {np.degrees(goal_rotation):.1f}°")

            # Check if we can get position (connection alive)
            test_pos = get_xbot_position(xbot_id)
            if test_pos is None:
                print(f"WARNING: Lost connection to PMC, attempting to reconnect...")
                disconnect_from_pmc()
                time.sleep(1)
                if not connect_to_pmc():
                    print(f"ERROR: Failed to reconnect to PMC")
                    continue
                print("Reconnected to PMC successfully")
                # Clear active xbots list since we reconnected
                self.active_xbots.clear()

            # Activate XBot if not already active
            if xbot_id not in self.active_xbots:
                try:
                    xbot.stop_motion(xbot_id=xbot_id)
                    time.sleep(0.2)
                except:
                    pass

                if not activate_xbot(xbot_id):
                    print(f"ERROR: Failed to activate XBot {xbot_id}")
                    continue

                self.active_xbots.add(xbot_id)

            # Add task
            self.add_xbot_task(xbot_id, goal_pos, uuid, goal_rotation)

            # Clear obstacle list for new task (obstacles are only for current task replanning)
            self.obstacle_xbots = []

            # Plan path
            if not self.plan_path(xbot_id):
                print(f"ERROR: Planning failed for XBot {xbot_id}")
                continue

            # Execute
            success = self.execute_xbot(xbot_id)

            if success:
                print(f"\n=== XBot {xbot_id} completed task ===")
                # After completion, publish Idle state with None UUID
                xbot_obj = self.xbots[xbot_id]
                xbot_obj.uuid = None
                xbot_obj.last_reported_state = None  # Force publish
                self.publish_state(xbot_id, "Idle")
            else:
                print(f"\n=== XBot {xbot_id} failed task ===")


def on_message(client, userdata, msg):
    """MQTT message callback."""
    controller = userdata['controller']

    try:
        payload = json.loads(msg.payload.decode())
        print(f"\n[MQTT] Received command: {msg.topic}")
        print(f"  Payload: {payload}")

        # Extract XBot ID from topic
        # Topic format: NN/Nybrovej/InnoLab/Planar/Xbot{N}/CMD/XYMotion
        topic_parts = msg.topic.split('/')
        xbot_str = topic_parts[4]  # "Xbot1", "Xbot2", etc.
        xbot_id = int(xbot_str.replace('Xbot', ''))

        # Extract command data
        uuid = payload.get('Uuid', 'unknown')
        position = payload.get('Position', [])

        if len(position) < 2 or len(position) > 3:
            print(
                f"[MQTT] ERROR: Invalid position format: {position}. Expected [x, y] or [x, y, rotation_degrees]")
            return

        goal_pos = (float(position[0]), float(position[1]))

        # Convert rotation from degrees to radians if provided (3rd element)
        goal_rotation = None
        if len(position) == 3:
            goal_rotation = np.radians(float(position[2]))

        # Add task to queue
        task = {
            'xbot_id': xbot_id,
            'goal_pos': goal_pos,
            'uuid': uuid,
            'goal_rotation': goal_rotation
        }

        with controller.task_lock:
            controller.task_queue.append(task)
            print(f"[MQTT] Task added to queue for XBot {xbot_id}")

    except Exception as e:
        print(f"[MQTT] ERROR processing message: {e}")


def on_connect(client, userdata, flags, rc):
    """MQTT connection callback."""
    if rc == 0:
        print("[MQTT] Connected successfully")
        # Subscribe to all XBot command topics
        for xbot_id in range(1, 10):  # Support XBots 1-9
            topic = f"{MQTT_BASE_TOPIC}/Xbot{xbot_id}/CMD/XYMotion"
            client.subscribe(topic, qos=1)
            print(f"[MQTT] Subscribed to: {topic}")
    else:
        print(f"[MQTT] Connection failed with code {rc}")


def main():
    """Main entry point."""
    print(f"\n=== Simple Multi-XBot Planner with MQTT ===")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Base Topic: {MQTT_BASE_TOPIC}")
    print("\nPress Ctrl+C to stop\n")

    # Parse command-line arguments
    enable_visualization = True
    if len(sys.argv) > 1 and sys.argv[1] == "--no-viz":
        enable_visualization = False
        print("Visualization DISABLED\n")

    controller = None
    mqtt_client = None

    try:
        # Connect to PMC
        pmc_ip = os.environ.get("PMC_IP")
        if not connect_to_pmc(pmc_ip):
            return False

        # Load workspace configuration from PMC
        print("\n" + "="*70)
        print("LOADING WORKSPACE CONFIGURATION FROM PMC")
        print("="*70)
        workspace = load_workspace_from_pmc(pmc_sys)
        if not workspace:
            print("ERROR: Failed to load workspace configuration")
            return False

        # Display workspace information
        workspace_width_m = workspace['width'] * FLYWAY_SIZE_M
        workspace_height_m = workspace['height'] * FLYWAY_SIZE_M
        print(f"\n✓ Workspace Configuration Loaded:")
        print(
            f"  Grid: {workspace['width']} columns × {workspace['height']} rows")
        print(f"  Total flyways: {workspace['flyway_count']}")
        print(
            f"  Flyway module size: {int(FLYWAY_SIZE_M * 1000)}mm × {int(FLYWAY_SIZE_M * 1000)}mm")
        print(
            f"  Workspace dimensions: {workspace_width_m:.3f}m × {workspace_height_m:.3f}m")

        if workspace.get('holes'):
            print(
                f"  ⚠ Holes detected: {len(workspace['holes'])} missing flyway(s)")
            print(f"  Hole locations (col, row): {workspace['holes']}")
        else:
            print(f"  ✓ No holes - continuous workspace")
        print("="*70 + "\n")

        # Setup MQTT client
        mqtt_client = mqtt.Client()
        controller = SimpleController(
            workspace, mqtt_client, enable_visualization)

        mqtt_client.user_data_set({'controller': controller})
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message

        # Connect to MQTT broker
        print(f"[MQTT] Connecting to broker...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()

        # Start task processing thread
        task_thread = threading.Thread(
            target=controller.process_task_queue, daemon=True)
        task_thread.start()

        print("\n[MQTT] Waiting for commands...\n")

        # Keep main thread alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n=== Interrupted by user ===")
        print("Stopping all XBots...")
        if controller:
            try:
                for xbot_id in controller.active_xbots:
                    xbot.stop_motion(xbot_id=xbot_id)
            except:
                pass
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        return False

    finally:
        disconnect_from_pmc()


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(1)

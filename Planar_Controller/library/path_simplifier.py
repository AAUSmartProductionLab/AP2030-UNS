"""
Path Simplification Module

Optimizes paths by:
- Removing redundant waypoints on straight lines
- Merging collinear segments
- Skipping turns when safe to do so
"""

from math import sqrt


# Constants
ROBOT_SIZE_M = 0.12
SAFETY_MARGIN_M = 0.02
FLYWAY_SIZE_M = 0.24


def simplify_path(grid_path):
    """
    Simplify grid path by removing unnecessary waypoints.
    Keep only waypoints where direction changes.

    Args:
        grid_path: List of (grid_x, grid_y) coordinates

    Returns:
        Simplified path with redundant waypoints removed
    """
    if len(grid_path) < 3:
        return grid_path

    simplified = [grid_path[0]]

    for i in range(1, len(grid_path) - 1):
        prev = grid_path[i - 1]
        curr = grid_path[i]
        next_pos = grid_path[i + 1]

        # Calculate direction vectors
        dir1 = (curr[0] - prev[0], curr[1] - prev[1])
        dir2 = (next_pos[0] - curr[0], next_pos[1] - curr[1])

        # Keep waypoint if direction changes
        if dir1 != dir2:
            simplified.append(curr)

    simplified.append(grid_path[-1])

    return simplified


def merge_collinear_segments(path_meters, workspace):
    """
    Merge consecutive segments that can be combined into longer straight lines.

    This works in two passes:
    1. Merge consecutive segments in the same direction (horizontal/vertical)
    2. Merge segments where we can skip intermediate turns if the direct path is safe

    Args:
        path_meters: List of waypoints in meters [(x, y), ...]
        workspace: Workspace configuration

    Returns:
        Optimized path with merged segments
    """
    if len(path_meters) < 3:
        return path_meters

    # Pass 1: Merge consecutive moves in the same direction
    merged = [path_meters[0]]

    for i in range(1, len(path_meters)):
        prev = merged[-1]
        curr = path_meters[i]

        # Calculate direction from previous to current
        dx = abs(curr[0] - prev[0])
        dy = abs(curr[1] - prev[1])

        # Check if this is in the same direction as the last segment
        if len(merged) >= 2:
            prev_prev = merged[-2]
            prev_dx = abs(prev[0] - prev_prev[0])
            prev_dy = abs(prev[1] - prev_prev[1])

            # If both are horizontal (dy small) or both vertical (dx small)
            same_direction = ((dx > 0.001 and dy < 0.001 and prev_dx > 0.001 and prev_dy < 0.001) or
                              (dy > 0.001 and dx < 0.001 and prev_dy > 0.001 and prev_dx < 0.001))

            if same_direction:
                # Replace last point with current (skip intermediate)
                merged[-1] = curr
                continue

        merged.append(curr)

    # Pass 2: Try to skip intermediate turns if safe
    final = [merged[0]]
    i = 1

    while i < len(merged):
        start = final[-1]

        # Try to skip as many turns as possible
        furthest = i
        for j in range(len(merged) - 1, i - 1, -1):
            end = merged[j]

            if is_direct_path_safe(start[0], start[1], end[0], end[1], workspace):
                furthest = j
                break

        final.append(merged[furthest])
        i = furthest + 1

    return final


def is_direct_path_safe(start_x, start_y, end_x, end_y, workspace):
    """
    Check if a direct path between two points is safe (no obstacles).

    For diagonal moves, uses a more conservative margin to account for
    the square robot's corners extending further from center.

    Args:
        start_x, start_y: Start position in meters
        end_x, end_y: End position in meters
        workspace: Workspace configuration with holes

    Returns:
        True if direct path is safe, False otherwise
    """
    # For square robot on diagonal paths, we need extra clearance
    half_size = ROBOT_SIZE_M / 2

    # Use a more conservative margin for diagonal moves
    dx = abs(end_x - start_x)
    dy = abs(end_y - start_y)
    is_diagonal = dx > 0.001 and dy > 0.001

    if is_diagonal:
        # For diagonal moves, increase margin to account for square corners
        # sqrt(2) * half_size ≈ 0.707 * 0.06 ≈ 0.0424m
        margin = half_size * 1.414 + SAFETY_MARGIN_M
    else:
        margin = half_size + SAFETY_MARGIN_M

    for hole_col, hole_row in workspace['holes']:
        # Get hole bounds
        hole_x_min = hole_col * FLYWAY_SIZE_M - margin
        hole_x_max = (hole_col + 1) * FLYWAY_SIZE_M + margin
        hole_y_min = hole_row * FLYWAY_SIZE_M - margin
        hole_y_max = (hole_row + 1) * FLYWAY_SIZE_M + margin

        # For diagonal paths, check if the line comes too close to obstacles
        if is_diagonal:
            # Sample points along the diagonal path
            num_samples = 20
            for i in range(num_samples + 1):
                t = i / num_samples
                sample_x = start_x + t * (end_x - start_x)
                sample_y = start_y + t * (end_y - start_y)

                # Check if this sample point (with margin) overlaps the hole
                if (hole_x_min < sample_x < hole_x_max and
                        hole_y_min < sample_y < hole_y_max):
                    return False
        else:
            # For straight paths, simple bounding box check is sufficient
            path_x_min = min(start_x, end_x)
            path_x_max = max(start_x, end_x)
            path_y_min = min(start_y, end_y)
            path_y_max = max(start_y, end_y)

            # Check for overlap
            if not (path_x_max < hole_x_min or path_x_min > hole_x_max or
                    path_y_max < hole_y_min or path_y_min > hole_y_max):
                return False

    return True

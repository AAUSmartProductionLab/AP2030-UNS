"""
A* Pathfinding Algorithm

Simple approach: Robot is treated as a POINT.
Obstacles are already inflated in the grid (Minkowski sum applied).
Just check if the single grid cell is valid.
"""

import heapq


def heuristic(pos1, pos2):
    """Manhattan distance heuristic (optimal for 4-connected grids)."""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])


def astar_search(grid, start_pos, goal_pos, grid_width, grid_height, turning_cost=0.3):
    """
    Optimized A* pathfinding using tuples and sets.
    """
    # Check bounds and obstacles
    if not (0 <= start_pos[0] < grid_width and 0 <= start_pos[1] < grid_height) or grid[start_pos[1]][start_pos[0]] == 1:
        print(f"ERROR: Start position {start_pos} invalid")
        return None

    if not (0 <= goal_pos[0] < grid_width and 0 <= goal_pos[1] < grid_height) or grid[goal_pos[1]][goal_pos[0]] == 1:
        print(f"ERROR: Goal position {goal_pos} invalid")
        return None

    # Priority queue stores (f_score, g_score, x, y, parent)
    # parent is (parent_x, parent_y)
    # Using (-1, -1) as sentinel for No Parent to ensure type consistency in heap
    no_parent = (-1, -1)
    start_tuple = (0.0 + float(heuristic(start_pos, goal_pos)),
                   0.0, start_pos, no_parent)

    open_set = [start_tuple]

    # Track best g_score for each position
    g_scores = {start_pos: 0.0}

    # Track came_from for path reconstruction
    came_from = {}

    goal_reached = False

    while open_set:
        # Get node with lowest f_score
        current_f, current_g, current_pos, parent_pos = heapq.heappop(open_set)

        # Check if we found a better path to this node already (lazy deletion)
        if current_g > g_scores.get(current_pos, float('inf')):
            continue

        # Record parent
        if parent_pos != no_parent:
            came_from[current_pos] = parent_pos

        # Goal reached
        if current_pos == goal_pos:
            goal_reached = True
            break

        x, y = current_pos

        # Neighbors (4-connected)
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy

            # Bounds check
            if 0 <= nx < grid_width and 0 <= ny < grid_height:
                # Obstacle check
                if grid[ny][nx] == 0:
                    neighbor_pos = (nx, ny)

                    # Calculate cost
                    step_cost = 1.0
                    turn_penalty = 0.0

                    # Turning cost logic
                    if parent_pos != no_parent:
                        px, py = parent_pos
                        prev_dx, prev_dy = x - px, y - py

                        if (prev_dx, prev_dy) != (dx, dy):
                            turn_penalty = turning_cost

                    new_g = current_g + step_cost + turn_penalty

                    # If this path is better than any previous one
                    if new_g < g_scores.get(neighbor_pos, float('inf')):
                        g_scores[neighbor_pos] = new_g
                        h = heuristic(neighbor_pos, goal_pos)
                        f = new_g + h
                        heapq.heappush(
                            open_set, (f, new_g, neighbor_pos, current_pos))

    if goal_reached:
        path = []
        curr = goal_pos
        path.append(curr)
        while curr in came_from:
            curr = came_from[curr]
            path.append(curr)
        return path[::-1]  # Reverse

    print("ERROR: No path found")
    return None

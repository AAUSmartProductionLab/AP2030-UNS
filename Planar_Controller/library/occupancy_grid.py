"""
Occupancy Grid Module

Simple approach:
- Layout holes/boundaries: Shrink by 10mm (robot can go over edge), then inflate by 60mm
- XBot obstacles: Add as 120mm×120mm squares, then inflate by 60mm (Minkowski sum)
- Moving robot: Treated as point in pathfinding (obstacles already account for robot size)
"""

from scipy.ndimage import binary_dilation
import numpy as np
import xml.etree.ElementTree as ET
import os


# Constants
GRID_CELL_SIZE_M = 0.005  # 5mm cells
FLYWAY_SIZE_M = 0.24  # 240mm per flyway

# Robot parameters
ROBOT_SIZE_M = 0.12  # 120mm square robot
ROBOT_RADIUS_M = 0.06  # 60mm from center to corner
ROBOT_RADIUS_CELLS = int(
    np.ceil(ROBOT_RADIUS_M / GRID_CELL_SIZE_M))  # 12 cells

# Boundary tolerance (robot can extend 10mm over layout edges)
BOUNDARY_TOLERANCE_M = 0.010  # 10mm
BOUNDARY_TOLERANCE_CELLS = int(
    np.ceil(BOUNDARY_TOLERANCE_M / GRID_CELL_SIZE_M))  # 2 cells


def meters_to_grid(x_m, y_m):
    """Convert meters to grid coordinates."""
    grid_x = int(round(x_m / GRID_CELL_SIZE_M))
    grid_y = int(round(y_m / GRID_CELL_SIZE_M))
    return grid_x, grid_y


def grid_to_meters(grid_x, grid_y):
    """Convert grid coordinates to meters (center of cell)."""
    x_m = grid_x * GRID_CELL_SIZE_M
    y_m = grid_y * GRID_CELL_SIZE_M
    return x_m, y_m


def inflate_obstacles(grid, radius_cells):
    """
    Inflate all obstacles in grid using fast binary dilation.
    """
    # Create square structure element (kernel) for square inflation
    size = 2 * radius_cells + 1
    structure = np.ones((size, size))

    # Use scipy's optimized binary dilation
    inflated = binary_dilation(grid, structure=structure).astype(int)

    return inflated


def create_occupancy_grid(workspace, xbot_obstacles=None):
    """
    Create occupancy grid from workspace and optional XBot obstacles.

    Simple workflow:
    1. Mark layout holes (shrunk by 2 cells = 10mm) as obstacles
    2. Add XBot obstacles as 120mm×120mm squares (24×24 cells)
    3. Inflate all obstacles by 12 cells (60mm) for moving robot - Minkowski sum

    Result: Moving robot (treated as point) will maintain proper clearance from all obstacles.

    Args:
        workspace: Dictionary with 'width', 'height', 'holes'
        xbot_obstacles: List of (x, y) positions in meters for XBot obstacles

    Returns:
        Tuple of (grid, grid_width, grid_height)
    """
    # Calculate grid dimensions
    workspace_width_m = workspace['width'] * FLYWAY_SIZE_M
    workspace_height_m = workspace['height'] * FLYWAY_SIZE_M

    grid_width = int(round(workspace_width_m / GRID_CELL_SIZE_M))
    grid_height = int(round(workspace_height_m / GRID_CELL_SIZE_M))

    # Initialize empty grid
    grid = np.zeros((grid_height, grid_width), dtype=int)

    # Add layout holes (shrunk by boundary tolerance)
    holes = workspace.get('holes', [])
    cells_per_flyway = int(FLYWAY_SIZE_M / GRID_CELL_SIZE_M)  # 48 cells

    for hole_col, hole_row in holes:
        start_x = hole_col * cells_per_flyway
        start_y = hole_row * cells_per_flyway

        # Shrink by 2 cells (10mm) on each side - robot can extend over edge
        for dx in range(BOUNDARY_TOLERANCE_CELLS, cells_per_flyway - BOUNDARY_TOLERANCE_CELLS):
            for dy in range(BOUNDARY_TOLERANCE_CELLS, cells_per_flyway - BOUNDARY_TOLERANCE_CELLS):
                grid_x = start_x + dx
                grid_y = start_y + dy
                if 0 <= grid_x < grid_width and 0 <= grid_y < grid_height:
                    grid[grid_y][grid_x] = 1

    # Add XBot obstacles if provided (as 120mm×120mm squares)
    if xbot_obstacles:
        # For 120mm robot: 60mm radius = 12 cells from center
        # Mark cells from -11 to +11 (inclusive) = 23 cells, but we want 24
        # So use -12 to +11 which is asymmetric but gives 24 cells
        # Better: mark the actual footprint area
        robot_half_size_m = ROBOT_SIZE_M / 2  # 60mm
        robot_half_size_cells = int(
            robot_half_size_m / GRID_CELL_SIZE_M)  # 12 cells

        for xbot_x, xbot_y in xbot_obstacles:
            # Mark the 120mm×120mm square footprint
            # From -59.5mm to +59.5mm = 119mm ≈ 120mm
            x_min = xbot_x - robot_half_size_m
            x_max = xbot_x + robot_half_size_m
            y_min = xbot_y - robot_half_size_m
            y_max = xbot_y + robot_half_size_m

            x_min_cell, y_min_cell = meters_to_grid(x_min, y_min)
            x_max_cell, y_max_cell = meters_to_grid(x_max, y_max)

            # Fill the rectangle
            for gx in range(x_min_cell, x_max_cell + 1):
                for gy in range(y_min_cell, y_max_cell + 1):
                    if 0 <= gx < grid_width and 0 <= gy < grid_height:
                        grid[gy][gx] = 1

    # Inflate all obstacles by robot radius (60mm) for moving robot (Minkowski sum)
    inflated_grid = inflate_obstacles(grid, ROBOT_RADIUS_CELLS)

    return inflated_grid, grid_width, grid_height


def grid_path_to_meters(grid_path):
    """Convert a list of grid coordinates to meters."""
    meter_path = []
    for grid_x, grid_y in grid_path:
        x_m, y_m = grid_to_meters(grid_x, grid_y)
        meter_path.append((x_m, y_m))
    return meter_path


def parse_pmc_config(config_path):
    """Parse PMC configuration XML to extract workspace layout and holes."""
    try:
        with open(config_path, 'rb') as f:
            xml_content = f.read()

        xml_content = xml_content.replace(
            b'\x00', b'').decode('ISO-8859-1').strip()
        root = ET.fromstring(xml_content)

        layout = root.find('.//flw/layout')
        if layout is not None:
            mcol_elem = layout.find('mcol')
            mrow_elem = layout.find('mrow')
            flw_count_elem = layout.find('flwCount')

            if mcol_elem is None or mcol_elem.text is None or \
               mrow_elem is None or mrow_elem.text is None or \
               flw_count_elem is None or flw_count_elem.text is None:
                return None

            mcol = int(mcol_elem.text)
            mrow = int(mrow_elem.text)
            flw_count = int(flw_count_elem.text)

            # Parse flyway mapping
            mapping = layout.find('mapping')
            present_flyways = set()

            if mapping is not None:
                col_elem = mapping.find('col')
                row_elem = mapping.find('row')

                if col_elem is not None and row_elem is not None:
                    col_values = [int(v.text) for v in col_elem.findall(
                        'value') if v.text is not None]
                    row_values = [int(v.text) for v in row_elem.findall(
                        'value') if v.text is not None]

                    for col, row in zip(col_values, row_values):
                        present_flyways.add((col, row))

            # Detect holes
            holes = []
            for col in range(mcol):
                for row in range(mrow):
                    if (col, row) not in present_flyways:
                        holes.append((col, row))

            return {
                'width': mcol,
                'height': mrow,
                'flyway_count': flw_count,
                'holes': holes
            }
        return None
    except Exception as e:
        print(f"ERROR: Config parsing failed: {e}")
        return None


def load_workspace_from_pmc(sys_commands, config_path="pmc_config.xml"):
    """
    Load workspace configuration from PMC.

    Args:
        sys_commands: PMC system commands module
        config_path: Path to save/load config file

    Returns:
        Workspace dictionary with width, height, and holes
    """
    config_path = os.path.abspath(config_path)

    try:
        sys_commands.save_pmc_config_xml_file(config_path)
    except Exception as e:
        print(f"ERROR: Could not update config from PMC: {e}")
        if not os.path.exists(config_path):
            print("ERROR: Config file not found")
            return None

    workspace = parse_pmc_config(config_path)
    if not workspace:
        print("ERROR: Failed to parse workspace configuration")
        return None

    return workspace

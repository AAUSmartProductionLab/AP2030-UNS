"""
Extract PMC System Layout

This script connects to the PMC and extracts:
- Workspace dimensions from PMC configuration
- Flyway layout (grid configuration)
- System status
"""

from pmclib import system_commands as sys
from pmclib import pmc_types as pm
import time
import xml.etree.ElementTree as ET
import os


def connect_to_pmc(pmc_ip=None):
    """Connect to PMC system."""
    try:
        if pmc_ip:
            print(f"Connecting to PMC at {pmc_ip}...")
            success = sys.connect_to_specific_pmc(pmc_ip)
        else:
            print("Auto-searching for PMC...")
            success = sys.auto_search_and_connect_to_pmc()

        if not success:
            print("❌ Failed to connect to PMC")
            return False

        print("✓ Connected to PMC")

        # Gain mastership
        sys.gain_mastership()
        print("✓ Mastership acquired")

        # Wait for PMC to be ready
        for _ in range(50):
            status = sys.get_pmc_status()
            if status in (pm.PMCSTATUS.PMC_FULLCTRL, pm.PMCSTATUS.PMC_INTELLIGENTCTRL):
                print(f"✓ PMC ready (Status: {status})")
                return True
            time.sleep(0.2)

        print("⚠ PMC not fully ready, but continuing...")
        return True

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def parse_pmc_config(config_path):
    """Parse PMC configuration XML to extract workspace dimensions.

    Each flyway module is 240mm × 240mm (standard PMC module size).
    Workspace dimensions = mcol × 240mm by mrow × 240mm.

    Args:
        config_path: Path to pmc_config.xml file

    Returns:
        dict with workspace information or None if parsing fails
    """
    try:
        # Read and clean the XML file to handle trailing whitespace and null bytes
        with open(config_path, 'rb') as f:  # Read as binary
            xml_content = f.read()

        # Remove null bytes and decode
        xml_content = xml_content.replace(
            b'\x00', b'').decode('ISO-8859-1').strip()

        # Parse the cleaned XML
        root = ET.fromstring(xml_content)

        # Get flyway layout
        layout = root.find('.//flw/layout')
        if layout is not None:
            # Safely extract integer values with null checks
            mcol_elem = layout.find('mcol')
            mrow_elem = layout.find('mrow')
            flw_count_elem = layout.find('flwCount')

            if mcol_elem is None or mcol_elem.text is None:
                raise ValueError("Missing 'mcol' element in layout")
            if mrow_elem is None or mrow_elem.text is None:
                raise ValueError("Missing 'mrow' element in layout")
            if flw_count_elem is None or flw_count_elem.text is None:
                raise ValueError("Missing 'flwCount' element in layout")

            mcol = int(mcol_elem.text)
            mrow = int(mrow_elem.text)
            flw_count = int(flw_count_elem.text)

            # Parse flyway mapping to detect holes
            mapping = layout.find('mapping')
            present_flyways = set()

            if mapping is not None:
                col_mapping = mapping.find('col')
                row_mapping = mapping.find('row')

                if col_mapping is not None and row_mapping is not None:
                    col_values = []
                    for v in col_mapping.findall('value'):
                        if v.text is not None:
                            col_values.append(int(v.text))

                    row_values = []
                    for v in row_mapping.findall('value'):
                        if v.text is not None:
                            row_values.append(int(v.text))

                    # Build set of present flyway positions
                    for col, row in zip(col_values, row_values):
                        present_flyways.add((col, row))

            # Detect holes (missing flyways in the grid)
            holes = []
            for col in range(mcol):
                for row in range(mrow):
                    if (col, row) not in present_flyways:
                        holes.append((col, row))

            # Each flyway module is 240mm × 240mm
            FLYWAY_SIZE_MM = 240
            workspace_width_mm = mcol * FLYWAY_SIZE_MM
            workspace_height_mm = mrow * FLYWAY_SIZE_MM

            return {
                'columns': mcol,
                'rows': mrow,
                'flyway_count': flw_count,
                'flyway_size_mm': FLYWAY_SIZE_MM,
                'workspace_width_mm': workspace_width_mm,
                'workspace_height_mm': workspace_height_mm,
                'workspace_width_m': workspace_width_mm / 1000.0,
                'workspace_height_m': workspace_height_mm / 1000.0,
                'holes': holes,
                'has_holes': len(holes) > 0
            }
        return None
    except ET.ParseError as e:
        print(f"⚠ XML parsing error: {e}")
        print(
            f"⚠ Tip: Check for trailing spaces or invalid characters in {config_path}")
        return None
    except Exception as e:
        print(f"⚠ Error reading config: {e}")
        return None


def extract_system_layout():
    """Main function to extract workspace layout from PMC."""
    print("="*70)
    print("PMC WORKSPACE LAYOUT ANALYZER")
    print("="*70)
    print()

    # Connect to PMC
    pmc_ip = os.environ.get("PMC_IP")
    if not connect_to_pmc(pmc_ip):
        return

    print()
    print("="*70)
    print("SYSTEM STATUS")
    print("="*70)

    # Get PMC status
    try:
        pmc_status = sys.get_pmc_status()
        print(f"PMC Status: {pmc_status}")
    except Exception as e:
        print(f"⚠ Could not get PMC status: {e}")

    # Try to save PMC configuration to XML file
    print("\nSaving PMC configuration...")
    config_path = os.path.abspath("pmc_config.xml")
    try:
        sys.save_pmc_config_xml_file(config_path)
        print(f"✓ Configuration saved to: {config_path}")
    except Exception as e:
        print(f"⚠ Configuration save failed: {e}")
        if not os.path.exists(config_path):
            print(f"⚠ Config file not found, cannot determine exact workspace dimensions")
            config_path = None

    # Parse configuration to get exact workspace dimensions
    workspace_info = None
    if config_path and os.path.exists(config_path):
        print("\nParsing workspace configuration...")
        workspace_info = parse_pmc_config(config_path)

        if workspace_info:
            print()
            print("="*70)
            print("WORKSPACE CONFIGURATION")
            print("="*70)
            print(f"\nFlyway Layout:")
            print(
                f"  Grid: {workspace_info['columns']} columns × {workspace_info['rows']} rows")
            print(f"  Total flyways: {workspace_info['flyway_count']}")
            print(
                f"  Flyway module size: {workspace_info['flyway_size_mm']}mm × {workspace_info['flyway_size_mm']}mm")
            print(f"\nWorkspace Dimensions:")
            print(
                f"  Width:  {workspace_info['workspace_width_mm']}mm ({workspace_info['workspace_width_m']:.3f}m)")
            print(
                f"  Height: {workspace_info['workspace_height_mm']}mm ({workspace_info['workspace_height_m']:.3f}m)")

            # Display holes if present
            if workspace_info['has_holes']:
                print(
                    f"\n⚠ Holes Detected: {len(workspace_info['holes'])} missing flyway(s)")
                print(f"  Hole locations (col, row):")
                for col, row in workspace_info['holes']:
                    x_mm = col * workspace_info['flyway_size_mm']
                    y_mm = row * workspace_info['flyway_size_mm']
                    print(
                        f"    - Column {col}, Row {row} (at {x_mm}mm, {y_mm}mm)")

                # Visual grid representation
                print(f"\n  Grid visualization (X = flyway, O = hole):")
                # Print from top row to bottom row for intuitive view
                for row in reversed(range(workspace_info['rows'])):
                    line = "    "
                    for col in range(workspace_info['columns']):
                        if (col, row) in workspace_info['holes']:
                            line += "O "
                        else:
                            line += "X "
                    print(line)
            else:
                print(f"\n✓ No holes detected - continuous workspace")
        else:
            print("⚠ Could not parse workspace dimensions from config")

    print()
    print("="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)

    # Disconnect
    disconnect_from_pmc()


def disconnect_from_pmc():
    """Disconnect from PMC."""
    try:
        sys.release_mastership()
        sys.disconnect_from_pmc()
        print("\n✓ Disconnected from PMC")
    except Exception as e:
        print(f"\n⚠ Disconnect error: {e}")


if __name__ == "__main__":
    extract_system_layout()

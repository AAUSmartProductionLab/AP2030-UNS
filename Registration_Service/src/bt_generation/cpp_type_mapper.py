"""
Maps JSON Schema types to C++ types for BehaviorTree.CPP port definitions.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from dataclasses import field


@dataclass
class CppPortInfo:
    """Information about a C++ port derived from JSON Schema."""
    name: str
    cpp_type: str
    json_type: str
    description: str
    default_value: Optional[str] = None
    is_required: bool = True
    is_array_element: bool = False
    array_name: Optional[str] = None
    array_index: Optional[int] = None


class CppTypeMapper:
    """
    Maps JSON Schema types to C++ types for BehaviorTree.CPP.

    Handles:
    - Primitive types (string, number, integer, boolean)
    - Array types with prefixItems (Position arrays)
    - Nested objects
    - $ref resolution (assumes already resolved)
    """

    # JSON Schema type -> (C++ type, default value)
    TYPE_MAP = {
        "string": ("std::string", '""'),
        "number": ("double", "0.0"),
        "integer": ("int", "0"),
        "boolean": ("bool", "false"),
        "object": ("nlohmann::json", "'{}'"),
        "array": ("nlohmann::json", "'[]'"),
    }

    def __init__(self):
        pass

    def extract_ports_from_schema(
        self,
        schema: Dict[str, Any],
        required_fields: Optional[List[str]] = None
    ) -> List[CppPortInfo]:
        """
        Extract port definitions from a resolved JSON schema.

        Args:
            schema: Resolved JSON schema (all $refs expanded)
            required_fields: List of required field names

        Returns:
            List of CppPortInfo for each port
        """
        ports = []
        required_fields = required_fields or schema.get("required", [])
        properties = schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            # Skip Uuid - it's auto-generated
            if prop_name.lower() == "uuid":
                continue

            prop_type = prop_def.get("type", "string")

            # Handle array with prefixItems (like Position: [x, y, theta])
            if prop_type == "array" and "prefixItems" in prop_def:
                array_ports = self._extract_array_ports(
                    prop_name, prop_def, prop_name in required_fields
                )
                ports.extend(array_ports)
            else:
                # Simple property
                cpp_type, default = self.TYPE_MAP.get(
                    prop_type, ("std::string", '""'))
                ports.append(CppPortInfo(
                    name=prop_name,
                    cpp_type=cpp_type,
                    json_type=prop_type,
                    description=prop_def.get(
                        "description", f"{prop_name} parameter"),
                    default_value=default,
                    is_required=prop_name in required_fields,
                ))

        return ports

    def _extract_array_ports(
        self,
        array_name: str,
        array_def: Dict[str, Any],
        is_required: bool
    ) -> List[CppPortInfo]:
        """
        Extract individual ports from an array with prefixItems.

        For Position: [x, y, theta], creates ports: x, y, yaw
        """
        ports = []
        prefix_items = array_def.get("prefixItems", [])
        min_items = array_def.get("minItems", len(prefix_items))

        for idx, item_def in enumerate(prefix_items):
            item_type = item_def.get("type", "number")
            cpp_type, default = self.TYPE_MAP.get(item_type, ("double", "0.0"))

            # Use title as port name, fall back to index
            port_name = item_def.get("title", f"{array_name}_{idx}")
            # Normalize: "Theta" -> "yaw" for conventional naming
            if port_name.lower() == "theta":
                port_name = "yaw"

            ports.append(CppPortInfo(
                name=port_name.lower(),
                cpp_type=cpp_type,
                json_type=item_type,
                description=item_def.get("description", f"{port_name} value"),
                default_value=default,
                is_required=is_required and idx < min_items,
                is_array_element=True,
                array_name=array_name,
                array_index=idx,
            ))

        return ports

    def generate_port_declaration(self, port: CppPortInfo) -> str:
        """Generate C++ port declaration for providedPorts()."""
        if port.is_required and port.default_value:
            return (
                f'BT::InputPort<{port.cpp_type}>("{port.name}", '
                f'"{port.description}")'
            )
        elif port.default_value:
            return (
                f'BT::InputPort<{port.cpp_type}>("{port.name}", '
                f'{port.default_value}, "{port.description}")'
            )
        else:
            return (
                f'BT::InputPort<{port.cpp_type}>("{port.name}", '
                f'"{port.description}")'
            )

    def generate_message_assignment(self, port: CppPortInfo) -> str:
        """Generate C++ code to add this port's value to the JSON message."""
        if port.is_array_element:
            # Will be handled by array assembly
            return f'auto {port.name}_val = getInput<{port.cpp_type}>("{port.name}");'
        else:
            return (
                f'if (auto val = getInput<{port.cpp_type}>("{port.name}"); val.has_value()) {{\n'
                f'    message["{port.name}"] = val.value();\n'
                f'}}'
            )

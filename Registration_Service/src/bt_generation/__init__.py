"""
BehaviorTree.CPP Node Generation from AAS Descriptions

This module generates BT plugin nodes from Asset Administration Shell
interface descriptions, including:
- C++ header and source files
- Plugin manifest XML for Groot2
- CMakeLists.txt for building the plugin library

Uses schema-based approach: one plugin per unique JSON schema,
avoiding code duplication when multiple assets share the same schemas.
"""

from .cpp_type_mapper import CppTypeMapper
from .plugin_registry import PluginRegistry
from .schema_based_generator import SchemaBasedGenerator

__all__ = [
    'CppTypeMapper',
    'PluginRegistry',
    'SchemaBasedGenerator'
]

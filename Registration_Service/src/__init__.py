"""
Registration Service Package

Unified AAS registration service for BaSyx.

Supports:
- Config-based registration from JSON files (ResourceTypeAAS schema)
- Operation Delegation topics.json generation
- DataBridge configuration from configs
- AAS generation via Pydantic + aas_pydantic → BaSyx pipeline
"""

from .config import BaSyxConfig
from .utils import save_json_file, load_json_file, ensure_directory

# Core utilities
from .core import (
    HTTPClient,
    HTTPError,
    DockerService,
    DockerError,
    DEFAULT_MQTT_BROKER,
    DEFAULT_MQTT_PORT,
    DEFAULT_BASYX_URL,
    DEFAULT_DELEGATION_URL,
    ModelType,
    HTTPStatus,
    ContainerNames,
    MQTTDefaults,
    BaSyxEndpoints,
)

# Utility functions
from .utils import (
    encode_aas_id,
    sanitize_id,
    topic_to_id,
)

# Config parsing
from .config_parser import (
    parse_config_file, parse_config_data,
    extract_operation_delegation_entry, extract_databridge_property_mappings,
)

# Topics generation
from .topics_generator import TopicsGenerator, generate_topics_from_configs, generate_topics_from_directory

# DataBridge generation
from .databridge_from_config import DataBridgeFromConfig, generate_databridge_from_configs, generate_databridge_from_directory

# Unified service
from .unified_service import UnifiedRegistrationService
from .mqtt_config_registration import MQTTConfigRegistrationService

# AAS Generation — IDTA-compliant via aas_pydantic
from .aas_idta import (
    build_from_dict, build_from_json, build_resource_type_aas,
    generate_station_template, inject_ids,
    ResourceTypeAAS, templates as idta_templates,
)

# Operation Delegation (MQTT bridge)
from .mqtt_operation_bridge import MQTTOperationBridge
from .operation_delegation_api import (
    app as delegation_app,
    get_topic_config, update_topic_config, set_full_topic_config,
    get_mqtt_bridge, init_mqtt_bridge,
    start_delegation_api, start_delegation_api_background,
)

__all__ = [
    # Core
    'BaSyxConfig',
    'save_json_file', 'load_json_file', 'ensure_directory',
    # Core utilities
    'HTTPClient', 'HTTPError', 'DockerService', 'DockerError',
    'DEFAULT_MQTT_BROKER', 'DEFAULT_MQTT_PORT', 'DEFAULT_BASYX_URL',
    'DEFAULT_DELEGATION_URL',
    'ModelType', 'HTTPStatus', 'ContainerNames', 'MQTTDefaults', 'BaSyxEndpoints',
    # Utility functions
    'encode_aas_id', 'sanitize_id', 'topic_to_id',
    # Config parsing
    'parse_config_file', 'parse_config_data',
    'extract_operation_delegation_entry', 'extract_databridge_property_mappings',
    # Topics generation
    'TopicsGenerator',
    'generate_topics_from_configs', 'generate_topics_from_directory',
    # DataBridge generation
    'DataBridgeFromConfig',
    'generate_databridge_from_configs', 'generate_databridge_from_directory',
    # Unified service
    'UnifiedRegistrationService',
    'MQTTConfigRegistrationService',
    # AAS Generation
    'build_from_dict', 'build_from_json',
    'build_resource_type_aas', 'generate_station_template', 'inject_ids',
    'ResourceTypeAAS', 'idta_templates',
    # Operation Delegation
    'MQTTOperationBridge',
    'delegation_app',
    'get_topic_config', 'update_topic_config', 'set_full_topic_config',
    'get_mqtt_bridge', 'init_mqtt_bridge',
    'start_delegation_api', 'start_delegation_api_background',
]

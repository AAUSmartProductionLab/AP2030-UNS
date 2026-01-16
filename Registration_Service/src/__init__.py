"""
Registration Service Package

Unified AAS registration service for BaSyx.

Supports:
- Config-based registration from YAML files
- Operation Delegation topics.json generation
- DataBridge configuration from configs
- AAS generation and BaSyx registration
"""

from .config import BaSyxConfig
from .utils import save_json_file, load_json_file, ensure_directory

# Unified modules
from .config_parser import ConfigParser, parse_config_file, parse_config_data
from .topics_generator import TopicsGenerator, generate_topics_from_configs, generate_topics_from_directory
from .databridge_from_config import DataBridgeFromConfig, generate_databridge_from_configs, generate_databridge_from_directory
from .unified_service import UnifiedRegistrationService
from .mqtt_config_registration import MQTTConfigRegistrationService
from .generate_aas import AASGenerator
from .aas_validator import AASValidator

__all__ = [
    # Core
    'BaSyxConfig',
    'save_json_file',
    'load_json_file',
    'ensure_directory',
    # Config parsing
    'ConfigParser',
    'parse_config_file',
    'parse_config_data',
    # Topics generation
    'TopicsGenerator',
    'generate_topics_from_configs',
    'generate_topics_from_directory',
    # DataBridge generation
    'DataBridgeFromConfig',
    'generate_databridge_from_configs',
    'generate_databridge_from_directory',
    # Unified service
    'UnifiedRegistrationService',
    'MQTTConfigRegistrationService',
    # AAS Generation
    'AASGenerator',
    'AASValidator',
]

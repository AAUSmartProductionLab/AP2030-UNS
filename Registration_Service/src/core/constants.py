"""
Constants and configuration values for the Registration Service.

Centralizes magic strings, default values, and configuration constants.
"""

from enum import Enum
from typing import Final
import os

from ..aas_generation.semantic_ids import SemanticIdCatalog


# Default network configuration
# These defaults are for running outside Docker (e.g., register_all_assets.py)
# Docker containers have MQTT_BROKER hardcoded to hivemq-broker in docker-compose.yml
DEFAULT_MQTT_BROKER: Final[str] = os.environ.get(
    "MQTT_BROKER", "localhost")
DEFAULT_MQTT_PORT: Final[int] = int(os.environ.get("MQTT_PORT", "1883"))
DEFAULT_BASYX_URL: Final[str] = os.environ.get(
    "BASYX_URL", "http://aas-env:8081")
DEFAULT_BASYX_INTERNAL_URL: Final[str] = os.environ.get(
    "BASYX_INTERNAL_URL", "http://aas-env:8081")
DEFAULT_DELEGATION_URL: Final[str] = os.environ.get(
    "DELEGATION_SERVICE_URL", "http://registration-service:8087")
DEFAULT_GITHUB_PAGES_URL: Final[str] = "https://aausmartproductionlab.github.io/AP2030-UNS"

# Registry URLs (for descriptor registration when running outside Docker)
DEFAULT_AAS_REGISTRY_URL: Final[str] = os.environ.get(
    "BASYX_AAS_REGISTRY_URL", "http://aas-registry:8080")
DEFAULT_SM_REGISTRY_URL: Final[str] = os.environ.get(
    "BASYX_SM_REGISTRY_URL", "http://sm-registry:8080")

# External URL for registry descriptors (used for URLs that need to be accessed from outside Docker)
EXTERNAL_BASYX_HOST: Final[str] = os.environ.get("EXTERNAL_HOST", "localhost")


class ModelType(str, Enum):
    """AAS model types."""
    AAS = "AssetAdministrationShell"
    SUBMODEL = "Submodel"
    CONCEPT_DESCRIPTION = "ConceptDescription"
    PROPERTY = "Property"
    FILE = "File"
    OPERATION = "Operation"
    SUBMODEL_COLLECTION = "SubmodelElementCollection"
    SUBMODEL_LIST = "SubmodelElementList"


class HTTPStatus(int, Enum):
    """Common HTTP status codes."""
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    NOT_FOUND = 404
    CONFLICT = 409


class ContainerNames:
    """Docker container names."""
    DATABRIDGE: Final[str] = "databridge"
    OPERATION_DELEGATION: Final[str] = "registration-service"
    AAS_ENV: Final[str] = "aas-env"
    AAS_REGISTRY: Final[str] = "aas-registry"
    SUBMODEL_REGISTRY: Final[str] = "submodel-registry"


class MQTTDefaults:
    """MQTT default values."""
    QOS_PROPERTY: Final[int] = 0
    QOS_ACTION: Final[int] = 2
    RETAIN_FALSE: Final[bool] = False
    RETAIN_TRUE: Final[bool] = True


class BaSyxEndpoints:
    """BaSyx endpoint paths."""
    SHELLS: Final[str] = "/shells"
    SUBMODELS: Final[str] = "/submodels"
    CONCEPT_DESCRIPTIONS: Final[str] = "/concept-descriptions"
    SHELL_DESCRIPTORS: Final[str] = "/shell-descriptors"
    SUBMODEL_DESCRIPTORS: Final[str] = "/submodel-descriptors"


class BaSyxPorts:
    """BaSyx service ports."""
    AAS_ENV: Final[int] = 8081
    AAS_REGISTRY: Final[int] = 8082
    SUBMODEL_REGISTRY: Final[int] = 8083


class SemanticIds:
    """Common semantic IDs."""
    # IDTA submodels
    ASSET_INTERFACES: Final[str] = SemanticIdCatalog.IDTA_ASSET_INTERFACES
    NAMEPLATE: Final[str] = SemanticIdCatalog.IDTA_NAMEPLATE
    TECHNICAL_DATA: Final[str] = SemanticIdCatalog.IDTA_TECHNICAL_DATA
    HIERARCHICAL_STRUCTURES_1_0: Final[str] = SemanticIdCatalog.IDTA_HIERARCHICAL_STRUCTURES_1_0
    HIERARCHICAL_STRUCTURES_1_1: Final[str] = SemanticIdCatalog.IDTA_HIERARCHICAL_STRUCTURES_1_1
    CARBON_FOOTPRINT: Final[str] = SemanticIdCatalog.IDTA_CARBON_FOOTPRINT

    # Custom submodels
    VARIABLES: Final[str] = SemanticIdCatalog.LEGACY_VARIABLES_SUBMODEL
    PARAMETERS: Final[str] = SemanticIdCatalog.LEGACY_PARAMETERS_SUBMODEL
    SKILLS: Final[str] = SemanticIdCatalog.LEGACY_SKILLS_SUBMODEL
    CAPABILITIES: Final[str] = SemanticIdCatalog.LEGACY_CAPABILITIES_SUBMODEL

    # W3C Thing Description
    WOT_ACTION: Final[str] = SemanticIdCatalog.WOT_ACTION
    WOT_PROPERTY: Final[str] = SemanticIdCatalog.WOT_PROPERTY
    WOT_INTERACTION: Final[str] = SemanticIdCatalog.WOT_INTERACTION


class DataTypes:
    """AAS data type prefixes."""
    XS_STRING: Final[str] = "xs:string"
    XS_INT: Final[str] = "xs:int"
    XS_DOUBLE: Final[str] = "xs:double"
    XS_BOOLEAN: Final[str] = "xs:boolean"


class PathDefaults:
    """Default paths for configuration files."""
    TOPICS_JSON: Final[str] = "config/topics.json"
    DATABRIDGE_DIR: Final[str] = "databridge"
    DATABRIDGE_QUERIES: Final[str] = "databridge/queries"
    CONFIG_DIR: Final[str] = "AASDescriptions/Resource/configs"
    PRODUCT_CONFIG_DIR: Final[str] = "AASDescriptions/Product/configs"


class MQTTTopics:
    """Default MQTT topics."""
    # Single registration topic - asset identity is determined from YAML payload
    REGISTRATION_CONFIG: Final[str] = "NN/Nybrovej/InnoLab/Registration/Config"
    REGISTRATION_RESPONSE: Final[str] = "NN/Nybrovej/InnoLab/Registration/Response"


class TimeoutDefaults:
    """Default timeout values in seconds."""
    DOCKER_RESTART: Final[int] = 30
    HTTP_REQUEST: Final[int] = 10
    MQTT_CONNECT: Final[int] = 60

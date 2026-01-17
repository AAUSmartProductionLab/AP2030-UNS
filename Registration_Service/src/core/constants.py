"""
Constants and configuration values for the Registration Service.

Centralizes magic strings, default values, and configuration constants.
"""

from enum import Enum
from typing import Final
import os


# Default network configuration
# These defaults assume the service runs within Docker (the primary deployment method)
# Override via command-line arguments or environment variables when running outside Docker
DEFAULT_MQTT_BROKER: Final[str] = os.environ.get(
    "MQTT_BROKER", "hivemq-broker")
DEFAULT_MQTT_PORT: Final[int] = int(os.environ.get("MQTT_PORT", "1883"))
DEFAULT_BASYX_URL: Final[str] = os.environ.get(
    "BASYX_URL", "http://aas-env:8081")
DEFAULT_BASYX_INTERNAL_URL: Final[str] = os.environ.get(
    "BASYX_INTERNAL_URL", "http://aas-env:8081")
DEFAULT_DELEGATION_URL: Final[str] = os.environ.get(
    "DELEGATION_SERVICE_URL", "http://operation-delegation:8087")
DEFAULT_GITHUB_PAGES_URL: Final[str] = "https://aausmartproductionlab.github.io/AP2030-UNS"

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
    OPERATION_DELEGATION: Final[str] = "operation-delegation"
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
    ASSET_INTERFACES: Final[str] = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0"
    NAMEPLATE: Final[str] = "https://admin-shell.io/zvei/nameplate/1/0/Nameplate"
    TECHNICAL_DATA: Final[str] = "https://admin-shell.io/ZVEI/TechnicalData/Submodel/1/2"
    HIERARCHICAL_STRUCTURES_1_0: Final[str] = "https://admin-shell.io/idta/HierarchicalStructures/1/0/Submodel"
    HIERARCHICAL_STRUCTURES_1_1: Final[str] = "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel"
    CARBON_FOOTPRINT: Final[str] = "https://admin-shell.io/idta/CarbonFootprint/0/9/ProductCarbonFootprint"

    # Custom submodels
    VARIABLES: Final[str] = "http://smartproductionlab.aau.dk/submodels/Variables/1/0"
    PARAMETERS: Final[str] = "http://smartproductionlab.aau.dk/submodels/Parameters/1/0"
    SKILLS: Final[str] = "http://smartproductionlab.aau.dk/submodels/Skills/1/0"
    CAPABILITIES: Final[str] = "http://smartproductionlab.aau.dk/submodels/OfferedCapabilitiyDescription/1/0"

    # W3C Thing Description
    WOT_ACTION: Final[str] = "https://www.w3.org/2019/wot/td#ActionAffordance"
    WOT_PROPERTY: Final[str] = "https://www.w3.org/2019/wot/td#PropertyAffordance"
    WOT_INTERACTION: Final[str] = "https://www.w3.org/2019/wot/td#InteractionAffordance"


class DataTypes:
    """AAS data type prefixes."""
    XS_STRING: Final[str] = "xs:string"
    XS_INT: Final[str] = "xs:int"
    XS_DOUBLE: Final[str] = "xs:double"
    XS_BOOLEAN: Final[str] = "xs:boolean"


class PathDefaults:
    """Default paths for configuration files."""
    TOPICS_JSON: Final[str] = "OperationDelegation/config/topics.json"
    DATABRIDGE_DIR: Final[str] = "databridge"
    DATABRIDGE_QUERIES: Final[str] = "databridge/queries"
    CONFIG_DIR: Final[str] = "AASDescriptions/Resource/configs"


class MQTTTopics:
    """Default MQTT topics."""
    REGISTRATION_CONFIG: Final[str] = "NN/Nybrovej/InnoLab/Registration/Config"
    REGISTRATION_LEGACY: Final[str] = "NN/Nybrovej/InnoLab/Registration/Request"
    REGISTRATION_RESPONSE: Final[str] = "NN/Nybrovej/InnoLab/Registration/Response"


class TimeoutDefaults:
    """Default timeout values in seconds."""
    DOCKER_RESTART: Final[int] = 30
    HTTP_REQUEST: Final[int] = 10
    MQTT_CONNECT: Final[int] = 60

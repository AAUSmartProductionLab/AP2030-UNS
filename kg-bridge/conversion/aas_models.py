"""Replacement AAS Pydantic models — lightweight local alternative to py-aas-rdf.

Only includes the fields and types that the kg-bridge runtime actually accesses.
No ``to_rdf()``, no ``RDFiable``, no rdflib — pure Pydantic data containers.

Encoding utilities (``url_encode``, ``base_64_url_encode``) are inlined here
so that ``iri.py`` and ``projection.py`` remain unchanged beyond the import path.
"""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from enum import Enum
from typing import Any, List, Literal, Optional, Union
from urllib.parse import quote, unquote

from pydantic import BaseModel, Field, conlist, constr

import rdflib


# ── Encoding utilities (formerly from py_aas_rdf.models) ────────────────────

def url_encode(data: str) -> str:
    return quote(data, safe="")


def base_64_url_encode(data: str) -> str:
    return urlsafe_b64encode(data.encode("utf-8")).rstrip(b"=").decode("utf-8")


def url_decode(data: str) -> str:
    return unquote(data)


def base_64_url_decode(data: str) -> str:
    padding = 4 - len(data) % 4
    return urlsafe_b64decode(data + "=" * padding).decode("utf-8")


# ── Enums ────────────────────────────────────────────────────────────────────

class ReferenceTypes(Enum):
    ExternalReference = "ExternalReference"
    ModelReference = "ModelReference"


class KeyTypes(Enum):
    AnnotatedRelationshipElement = "AnnotatedRelationshipElement"
    AssetAdministrationShell = "AssetAdministrationShell"
    BasicEventElement = "BasicEventElement"
    Blob = "Blob"
    Capability = "Capability"
    ConceptDescription = "ConceptDescription"
    DataElement = "DataElement"
    Entity = "Entity"
    EventElement = "EventElement"
    File = "File"
    FragmentReference = "FragmentReference"
    GlobalReference = "GlobalReference"
    Identifiable = "Identifiable"
    MultiLanguageProperty = "MultiLanguageProperty"
    Operation = "Operation"
    Property = "Property"
    Range = "Range"
    Referable = "Referable"
    ReferenceElement = "ReferenceElement"
    RelationshipElement = "RelationshipElement"
    Submodel = "Submodel"
    SubmodelElement = "SubmodelElement"
    SubmodelElementCollection = "SubmodelElementCollection"
    SubmodelElementList = "SubmodelElementList"


class ModelType(Enum):
    AnnotatedRelationshipElement = "AnnotatedRelationshipElement"
    AssetAdministrationShell = "AssetAdministrationShell"
    BasicEventElement = "BasicEventElement"
    Blob = "Blob"
    Capability = "Capability"
    ConceptDescription = "ConceptDescription"
    DataSpecificationIec61360 = "DataSpecificationIec61360"
    Entity = "Entity"
    File = "File"
    MultiLanguageProperty = "MultiLanguageProperty"
    Operation = "Operation"
    Property = "Property"
    Range = "Range"
    ReferenceElement = "ReferenceElement"
    RelationshipElement = "RelationshipElement"
    Submodel = "Submodel"
    SubmodelElementCollection = "SubmodelElementCollection"
    SubmodelElementList = "SubmodelElementList"


class AssetKind(Enum):
    Instance = "Instance"
    Type = "Type"


class ModellingKind(Enum):
    Instance = "Instance"
    Template = "Template"


class DataTypeDefXsd(Enum):
    AnyUri = "xs:anyURI"
    Base64Binary = "xs:base64Binary"
    Boolean = "xs:boolean"
    Byte = "xs:byte"
    Date = "xs:date"
    DateTime = "xs:dateTime"
    Decimal = "xs:decimal"
    Double = "xs:double"
    Duration = "xs:duration"
    Float = "xs:float"
    GDay = "xs:gDay"
    GMonth = "xs:gMonth"
    GMonthDay = "xs:gMonthDay"
    GYear = "xs:gYear"
    GYearMonth = "xs:gYearMonth"
    HexBinary = "xs:hexBinary"
    Int = "xs:int"
    Integer = "xs:integer"
    Long = "xs:long"
    NegativeInteger = "xs:negativeInteger"
    NonNegativeInteger = "xs:nonNegativeInteger"
    NonPositiveInteger = "xs:nonPositiveInteger"
    PositiveInteger = "xs:positiveInteger"
    Short = "xs:short"
    String = "xs:string"
    Time = "xs:time"
    UnsignedByte = "xs:unsignedByte"
    UnsignedInt = "xs:unsignedInt"
    UnsignedLong = "xs:unsignedLong"
    UnsignedShort = "xs:unsignedShort"


class AasSubmodelElements(Enum):
    AnnotatedRelationshipElement = "AnnotatedRelationshipElement"
    BasicEventElement = "BasicEventElement"
    Blob = "Blob"
    Capability = "Capability"
    DataElement = "DataElement"
    Entity = "Entity"
    EventElement = "EventElement"
    File = "File"
    MultiLanguageProperty = "MultiLanguageProperty"
    Operation = "Operation"
    Property = "Property"
    Range = "Range"
    ReferenceElement = "ReferenceElement"
    RelationshipElement = "RelationshipElement"
    SubmodelElement = "SubmodelElement"
    SubmodelElementCollection = "SubmodelElementCollection"
    SubmodelElementList = "SubmodelElementList"


# ── Reference / Key ─────────────────────────────────────────────────────────

class Key(BaseModel):
    type: KeyTypes
    value: constr(min_length=1, max_length=2000)


class Reference(BaseModel):
    type: ReferenceTypes
    keys: conlist(Key, min_length=1)


# ── AssetInformation ────────────────────────────────────────────────────────

class SpecificAssetId(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    externalSubjectId: Optional[Reference] = None


class Resource(BaseModel):
    path: Optional[str] = None
    contentType: Optional[str] = None


class AssetInformation(BaseModel):
    assetKind: AssetKind
    globalAssetId: Optional[constr(min_length=1, max_length=2000)] = None
    specificAssetIds: Optional[List[SpecificAssetId]] = Field(None, min_length=0)
    assetType: Optional[constr(min_length=1, max_length=2000)] = None
    defaultThumbnail: Optional[Resource] = None


# ── Mixin base classes (thin wrappers for structural compatibility) ─────────

class Extension(BaseModel):
    name: str
    valueType: Optional[str] = None
    value: Optional[str] = None
    refersTo: Optional[List[Reference]] = None
    modelType: Optional[str] = None


class HasExtensions(BaseModel):
    extensions: Optional[List[Extension]] = Field(None, min_length=0)


class HasSemantics(BaseModel):
    semanticId: Optional[Reference] = None
    supplementalSemanticIds: Optional[List[Reference]] = Field(None, min_length=0)


class Qualifier(BaseModel):
    type: str
    valueType: DataTypeDefXsd
    value: Optional[str] = None
    valueId: Optional[Reference] = None
    semanticId: Optional[Reference] = None
    supplementalSemanticIds: Optional[List[Reference]] = None


class Qualifiable(BaseModel):
    qualifiers: Optional[List[Qualifier]] = Field(None, min_length=0)


class EmbeddedDataSpecification(BaseModel):
    dataSpecification: Optional[Reference] = None
    dataSpecificationContent: Optional[Any] = None


class HasDataSpecification(BaseModel):
    embeddedDataSpecifications: Optional[List[EmbeddedDataSpecification]] = Field(None, min_length=0)


class Referable(HasExtensions):
    category: Optional[constr(min_length=1, max_length=128, strip_whitespace=True)] = None
    idShort: Optional[constr(min_length=1, max_length=128, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")] = None
    displayName: Optional[List[Any]] = Field(None, min_length=0)
    description: Optional[List[Any]] = Field(None, min_length=0)


class AdministrativeInformation(HasDataSpecification):
    version: Optional[str] = None
    revision: Optional[str] = None
    creator: Optional[Reference] = None
    templateId: Optional[str] = None


class Identifiable(Referable):
    id: constr(min_length=1, max_length=2000)
    administration: Optional[AdministrativeInformation] = None


# ── SubmodelElement hierarchy ────────────────────────────────────────────────

class SubmodelElement(Referable, HasSemantics, Qualifiable, HasDataSpecification):
    """Base for all SubmodelElement types. No extra fields — the union
    discriminator (``modelType``) is set by each concrete subclass."""


# ── DataElement (intermediate, not directly instantiated) ────────────────────

class DataElement(SubmodelElement):
    """Marker base — no extra fields beyond SubmodelElement."""


# ── Concrete element types used at runtime ───────────────────────────────────

class Property(DataElement):
    valueType: DataTypeDefXsd
    value: Optional[str] = None
    valueId: Optional[Reference] = None
    modelType: Literal["Property"] = ModelType.Property.value


class ReferenceElement(DataElement):
    value: Optional[Reference] = None
    modelType: Literal["ReferenceElement"] = ModelType.ReferenceElement.value


class SubmodelElementCollection(SubmodelElement):
    value: Optional[List["SubmodelElementChoice"]] = Field(None, min_length=0)
    modelType: Literal["SubmodelElementCollection"] = ModelType.SubmodelElementCollection.value


class SubmodelElementList(SubmodelElement):
    orderRelevant: Optional[bool] = None
    semanticIdListElement: Optional[Reference] = None
    typeValueListElement: Optional[AasSubmodelElements] = None
    valueTypeListElement: Optional[DataTypeDefXsd] = None
    value: Optional[List["SubmodelElementChoice"]] = Field(None, min_length=0)
    modelType: Literal["SubmodelElementList"] = ModelType.SubmodelElementList.value


# ── Unused element types (stubs for the discriminated union) ─────────────────

class RelationshipElement(SubmodelElement):
    first: Optional[Reference] = None
    second: Optional[Reference] = None
    # ── Unused element types (stubs for the union) ─────────────────
    modelType: Literal["RelationshipElement"] = ModelType.RelationshipElement.value


class AnnotatedRelationshipElement(SubmodelElement):
    first: Optional[Reference] = None
    second: Optional[Reference] = None
    annotations: Optional[List[DataElement]] = None
    modelType: Literal["AnnotatedRelationshipElement"] = ModelType.AnnotatedRelationshipElement.value


class BasicEventElement(SubmodelElement):
    observed: Optional[Reference] = None
    direction: Optional[str] = None
    state: Optional[str] = None
    messageTopic: Optional[str] = None
    messageBroker: Optional[Reference] = None
    lastUpdate: Optional[str] = None
    minInterval: Optional[str] = None
    maxInterval: Optional[str] = None
    modelType: Literal["BasicEventElement"] = ModelType.BasicEventElement.value


class Blob(DataElement):
    value: Optional[str] = None
    contentType: str = "application/octet-stream"
    modelType: Literal["Blob"] = ModelType.Blob.value


class File(DataElement):
    value: Optional[str] = None
    contentType: str = "application/octet-stream"
    modelType: Literal["File"] = ModelType.File.value


class MultiLanguageProperty(DataElement):
    value: Optional[List[Any]] = None
    valueId: Optional[Reference] = None
    modelType: Literal["MultiLanguageProperty"] = ModelType.MultiLanguageProperty.value


class Range(DataElement):
    valueType: Optional[DataTypeDefXsd] = None
    min: Optional[str] = None
    max: Optional[str] = None
    modelType: Literal["Range"] = ModelType.Range.value


class Entity(SubmodelElement):
    statements: Optional[List["SubmodelElementChoice"]] = None
    entityType: Optional[str] = None
    globalAssetId: Optional[str] = None
    specificAssetIds: Optional[List[SpecificAssetId]] = None
    modelType: Literal["Entity"] = ModelType.Entity.value


class Capability(SubmodelElement):
    modelType: Literal["Capability"] = ModelType.Capability.value


class Operation(SubmodelElement):
    inputVariables: Optional[List[Property]] = None
    outputVariables: Optional[List[Property]] = None
    inoutputVariables: Optional[List[Property]] = None
    modelType: Literal["Operation"] = ModelType.Operation.value


# ── SubmodelElementChoice (plain union — each member has a unique modelType literal
#    so Pydantic can pick the correct variant without an explicit discriminator) ──

SubmodelElementChoice = Union[
    RelationshipElement,
    AnnotatedRelationshipElement,
    BasicEventElement,
    Blob,
    File,
    MultiLanguageProperty,
    Property,
    Range,
    ReferenceElement,
    SubmodelElementCollection,
    SubmodelElementList,
    Entity,
    Capability,
    Operation,
]


# ── Top-level AAS models ─────────────────────────────────────────────────────

class HasKind(BaseModel):
    kind: Optional[ModellingKind] = None


class Submodel(Identifiable, HasKind, HasSemantics, Qualifiable, HasDataSpecification):
    submodelElements: Optional[List[SubmodelElementChoice]] = None
    modelType: str = ModelType.Submodel.value


class AssetAdministrationShell(Identifiable, HasDataSpecification):
    derivedFrom: Optional[Reference] = None
    assetInformation: Optional[AssetInformation] = None
    submodels: Optional[List[Reference]] = Field(None, min_length=0)
    modelType: str = ModelType.AssetAdministrationShell.value


# ── py-aas-rdf compatibility exports (used by sparql.py, dispatcher.py) ──────

class AASNameSpace:
    """Mirrors py_aas_rdf.models.aas_namespace.AASNameSpace for the AAS RDF namespace."""
    AAS = rdflib.Namespace("https://admin-shell.io/aas/3/1/")



# Resolve forward references (string annotations for circular types).
SubmodelElementCollection.model_rebuild()
SubmodelElementList.model_rebuild()
Entity.model_rebuild()

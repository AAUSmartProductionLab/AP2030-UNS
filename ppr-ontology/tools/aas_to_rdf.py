"""aas_to_rdf — generic AAS JSON → RDF serializer aligned to CSSx_AAS.ttl.

Input  : full AAS JSON (assetAdministrationShells + submodels + conceptDescriptions)
Output : Turtle RDF using
         - AAS  = https://admin-shell.io/aas/3/1/
         - CSS  = https://w3id.org/2025/css#
         - CSSX = https://w3id.org/2025/cssx#

Typing strategy:
- Every AAS-JSON object is rdf:typed as the official AAS class for its `modelType`.
- When a known IDTA `semanticId` is present, the object additionally gets the
  matching cssx: subclass (e.g. `cssx:DigitalNameplateSubmodel`,
  `cssx:ManufacturerNameMLP`). Unknown semanticIds → only the bare AAS class type,
  so structural validation still fires but domain constraints don't apply.
- Containment uses the official AAS property IRIs
  (`aas:Submodel/submodelElements`, `aas:SubmodelElementCollection/value`,
   `aas:HasSemantics/semanticId`, `aas:Property/value`, `aas:Property/valueType`,
   `aas:Entity/statements`).

Public API:
    convert(aas_json_path: Path, output_ttl_path: Path) -> None
    serialize(document: dict) -> rdflib.Graph
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD


# Make `from generation.v2...` imports work when this file is run from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from generation.v2.AAS_generation_v2.core.semantic_ids import (  # noqa: E402
    SM_NAMEPLATE,
    SM_HIERARCHICAL_STRUCTURES,
    SM_ASSET_INTERFACES,
    SM_CAPABILITIES,
    SM_SKILLS,
    SM_OPERATIONAL_DATA,
    SM_PARAMETERS,
    NP_MANUFACTURER_NAME,
    NP_MANUFACTURER_PRODUCT_DESIGNATION,
    NP_CONTACT_INFORMATION,
    NP_ORDER_CODE_OF_MANUFACTURER,
    HS_ARCHETYPE,
    HS_ENTRY_NODE,
    AID_INTERFACE,
    AID_ENDPOINT_METADATA,
    AID_INTERACTION_METADATA,
)


AAS  = Namespace("https://admin-shell.io/aas/3/1/")
CSS  = Namespace("https://w3id.org/2025/css#")
CSSX = Namespace("https://w3id.org/2025/cssx#")


# --- AAS modelType → official AAS class IRI ---
_AAS_CLASS_BY_MODEL_TYPE: dict[str, URIRef] = {
    "AssetAdministrationShell":     AAS.AssetAdministrationShell,
    "Submodel":                     AAS.Submodel,
    "Property":                     AAS.Property,
    "MultiLanguageProperty":        AAS.MultiLanguageProperty,
    "SubmodelElementCollection":    AAS.SubmodelElementCollection,
    "SubmodelElementList":          AAS.SubmodelElementList,
    "ReferenceElement":             AAS.ReferenceElement,
    "RelationshipElement":          AAS.RelationshipElement,
    "AnnotatedRelationshipElement": AAS.AnnotatedRelationshipElement,
    "Entity":                       AAS.Entity,
    "File":                         AAS.File,
    "Blob":                         AAS.Blob,
    "Range":                        AAS.Range,
    "Operation":                    AAS.Operation,
    "BasicEventElement":            AAS.BasicEventElement,
    "Capability":                   AAS.Capability,
}


# --- Submodel-level semanticId → cssx subclass ---
SUBMODEL_TYPE_BY_SEMANTIC_ID: dict[str, URIRef] = {
    SM_NAMEPLATE:               CSSX.DigitalNameplateSubmodel,
    SM_HIERARCHICAL_STRUCTURES: CSSX.HierarchicalStructuresSubmodel,
    SM_ASSET_INTERFACES:        CSSX.AIDSubmodel,
    SM_CAPABILITIES:            CSSX.CapabilitiesSubmodel,
    SM_SKILLS:                  CSSX.SkillsSubmodel,
    SM_OPERATIONAL_DATA:        CSSX.OperationalDataSubmodel,
    SM_PARAMETERS:              CSSX.ParametersSubmodel,
}

# --- SME-level semanticId → cssx subclass ---
SME_TYPE_BY_SEMANTIC_ID: dict[str, URIRef] = {
    NP_MANUFACTURER_NAME:                CSSX.ManufacturerNameMLP,
    NP_MANUFACTURER_PRODUCT_DESIGNATION: CSSX.ManufacturerProductDesignationMLP,
    NP_CONTACT_INFORMATION:              CSSX.ContactInformationSMC,
    NP_ORDER_CODE_OF_MANUFACTURER:       CSSX.OrderCodeProperty,
    HS_ARCHETYPE:                        CSSX.ArcheTypeProperty,
    HS_ENTRY_NODE:                       CSSX.BomEntity,
    AID_INTERFACE:                       CSSX.InterfaceSMC,
    AID_ENDPOINT_METADATA:               CSSX.EndpointMetadataSMC,
    AID_INTERACTION_METADATA:            CSSX.InteractionMetadataSMC,
}

# --- Submodel subclass → typed-link property on AAS shell (drives OWL cross-SM constraints) ---
_TYPED_LINK_BY_SUBTYPE: dict[URIRef, URIRef] = {
    CSSX.DigitalNameplateSubmodel:      CSSX.hasDigitalNameplateSubmodel,
    CSSX.HierarchicalStructuresSubmodel: CSSX.hasHierarchicalStructuresSubmodel,
    CSSX.AIDSubmodel:                   CSSX.hasAIDSubmodel,
    CSSX.CapabilitiesSubmodel:          CSSX.hasCapabilitiesSubmodel,
    CSSX.SkillsSubmodel:                CSSX.hasSkillsSubmodel,
    CSSX.OperationalDataSubmodel:       CSSX.hasOperationalDataSubmodel,
    CSSX.ParametersSubmodel:            CSSX.hasParametersSubmodel,
}


# --- Property IRIs (AAS metamodel) used for containment / values ---
P_SUBMODEL_ELEMENTS = AAS["Submodel/submodelElements"]
P_SMC_VALUE         = AAS["SubmodelElementCollection/value"]
P_SML_VALUE         = AAS["SubmodelElementList/value"]
P_ENTITY_STATEMENTS = AAS["Entity/statements"]
P_ENTITY_TYPE       = AAS["Entity/entityType"]
P_ENTITY_GLOBAL_ID  = AAS["Entity/globalAssetId"]
P_HAS_SEMANTIC_ID   = AAS["HasSemantics/semanticId"]
P_HAS_SUPPL_SEMANTIC_ID = AAS["HasSemantics/supplementalSemanticIds"]
P_PROP_VALUE        = AAS["Property/value"]
P_PROP_VALUE_TYPE   = AAS["Property/valueType"]
P_MLP_VALUE         = AAS["MultiLanguageProperty/value"]
P_RANGE_MIN         = AAS["Range/min"]
P_RANGE_MAX         = AAS["Range/max"]
P_FILE_VALUE        = AAS["File/value"]
P_FILE_CONTENT_TYPE = AAS["File/contentType"]
P_REL_FIRST         = AAS["RelationshipElement/first"]
P_REL_SECOND        = AAS["RelationshipElement/second"]
P_REF_ELEM_VALUE    = AAS["ReferenceElement/value"]
P_REFERABLE_ID_SHORT = AAS["Referable/idShort"]
P_IDENTIFIABLE_ID    = AAS["Identifiable/id"]
P_AAS_ASSET_INFO     = AAS["AssetAdministrationShell/assetInformation"]
P_AAS_SUBMODELS      = AAS["AssetAdministrationShell/submodels"]
P_AAS_DERIVED_FROM   = AAS["AssetAdministrationShell/derivedFrom"]

# AssetInformation properties
P_AI_ASSET_KIND       = AAS["AssetInformation/assetKind"]
P_AI_GLOBAL_ASSET_ID  = AAS["AssetInformation/globalAssetId"]
P_AI_SPECIFIC_IDS     = AAS["AssetInformation/specificAssetIds"]
P_AI_ASSET_TYPE       = AAS["AssetInformation/assetType"]

# SpecificAssetId properties
P_SAI_NAME       = AAS["SpecificAssetId/name"]
P_SAI_VALUE      = AAS["SpecificAssetId/value"]
P_SAI_EXTERNAL   = AAS["SpecificAssetId/externalSubjectId"]

# Reference + Key
P_REF_TYPE = AAS["Reference/type"]
P_REF_KEYS = AAS["Reference/keys"]
P_KEY_TYPE  = AAS["Key/type"]
P_KEY_VALUE = AAS["Key/value"]

# LangString
P_LS_LANGUAGE = AAS["AbstractLangString/language"]
P_LS_TEXT     = AAS["AbstractLangString/text"]
P_LS_TEXT_TYPED = AAS["LangStringTextType/text"]

# Administration
P_ADMIN_VERSION  = AAS["AdministrativeInformation/version"]
P_ADMIN_REVISION = AAS["AdministrativeInformation/revision"]
P_HAS_ADMIN      = AAS["Identifiable/administration"]


# Enum-value IRI builders. These match the AAS spec where each enum value is a
# named individual at <ns>/<EnumName>/<MemberName>.
def _enum_iri(enum_class: str, member: str) -> URIRef:
    return AAS[f"{enum_class}/{member}"]


# --- xsd valueType strings used in AAS JSON ---
_VALUE_TYPE_TO_AAS_DATATYPE: dict[str, URIRef] = {
    # Common forms found in basyx-emitted JSON
    "xs:string":  AAS["DataTypeDefXsd/String"],
    "xs:boolean": AAS["DataTypeDefXsd/Boolean"],
    "xs:int":     AAS["DataTypeDefXsd/Int"],
    "xs:integer": AAS["DataTypeDefXsd/Integer"],
    "xs:double":  AAS["DataTypeDefXsd/Double"],
    "xs:float":   AAS["DataTypeDefXsd/Float"],
    "xs:decimal": AAS["DataTypeDefXsd/Decimal"],
    "xs:date":    AAS["DataTypeDefXsd/Date"],
    "xs:dateTime": AAS["DataTypeDefXsd/DateTime"],
    "xs:long":    AAS["DataTypeDefXsd/Long"],
    "xs:short":   AAS["DataTypeDefXsd/Short"],
    "xs:byte":    AAS["DataTypeDefXsd/Byte"],
    # Lowercase variants seen in some serializers
    "string":  AAS["DataTypeDefXsd/String"],
    "boolean": AAS["DataTypeDefXsd/Boolean"],
}


# ------------------------------------------------------------------ helpers


def _safe_local(text: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return safe or "x"


def _semantic_ids(node: dict) -> list[str]:
    """Return the list of semanticId key values, preserving order."""
    out: list[str] = []
    semantic = node.get("semanticId") if isinstance(node, dict) else None
    if isinstance(semantic, dict):
        for key in semantic.get("keys", []) or []:
            value = key.get("value") if isinstance(key, dict) else None
            if value:
                out.append(str(value))
    return out


def _first_semantic_id(node: dict) -> str | None:
    ids = _semantic_ids(node)
    return ids[0] if ids else None


def _mint_child_uri(parent: URIRef, idshort: str | None, index: int) -> URIRef:
    seg = _safe_local(idshort) if idshort else f"item-{index}"
    sep = "/" if "#" in str(parent) else "#"
    return URIRef(f"{parent}{sep}{seg}")


# ------------------------------------------------------------------ emitters


# Counter to mint unique URIs for blank-node-equivalent Reference / LangString /
# AssetInformation resources. Module-global is fine because each `serialize`
# call rebuilds the graph from scratch and the counter only needs uniqueness
# within a single graph.
_BNODE_COUNTER = [0]


def _next_anon(parent: URIRef, kind: str) -> URIRef:
    _BNODE_COUNTER[0] += 1
    sep = "/" if "#" in str(parent) else "#"
    return URIRef(f"{parent}{sep}_{kind}-{_BNODE_COUNTER[0]}")


def _emit_referable(g: Graph, node_uri: URIRef, node: dict) -> None:
    idshort = node.get("idShort")
    if idshort:
        g.add((node_uri, P_REFERABLE_ID_SHORT, Literal(str(idshort), datatype=XSD.string)))
        g.add((node_uri, RDFS.label, Literal(str(idshort))))


def _emit_reference(g: Graph, parent_uri: URIRef, predicate: URIRef, ref: dict | None) -> URIRef | None:
    """Mint a typed `aas:Reference` resource and link it via `predicate`.

    Reference dict shape:
      { "type": "ModelReference"|"ExternalReference",
        "keys": [{ "type": "<KeyType>", "value": "<str>" }, ...] }
    """
    if not isinstance(ref, dict):
        return None
    keys = ref.get("keys") or []
    if not keys:
        return None

    ref_uri = _next_anon(parent_uri, "ref")
    g.add((parent_uri, predicate, ref_uri))
    g.add((ref_uri, RDF.type, AAS.Reference))

    ref_type = ref.get("type") or "ExternalReference"
    g.add((ref_uri, P_REF_TYPE, _enum_iri("ReferenceTypes", str(ref_type))))

    for key in keys:
        if not isinstance(key, dict):
            continue
        key_type = key.get("type")
        key_value = key.get("value")
        if key_value is None:
            continue
        key_uri = _next_anon(ref_uri, "key")
        g.add((ref_uri, P_REF_KEYS, key_uri))
        g.add((key_uri, RDF.type, AAS.Key))
        if key_type:
            g.add((key_uri, P_KEY_TYPE, _enum_iri("KeyTypes", str(key_type))))
        g.add((key_uri, P_KEY_VALUE, Literal(str(key_value), datatype=XSD.string)))
    return ref_uri


def _emit_semantic_id(g: Graph, node_uri: URIRef, node: dict) -> None:
    semantic = node.get("semanticId") if isinstance(node, dict) else None
    if isinstance(semantic, dict):
        _emit_reference(g, node_uri, P_HAS_SEMANTIC_ID, semantic)
    for suppl in node.get("supplementalSemanticIds", []) or []:
        if isinstance(suppl, dict):
            _emit_reference(g, node_uri, P_HAS_SUPPL_SEMANTIC_ID, suppl)
    # Also emit any cssx subclass typing recognised from the semanticId values.
    for sid in _semantic_ids(node):
        sme_subtype = SME_TYPE_BY_SEMANTIC_ID.get(sid)
        if sme_subtype is not None:
            g.add((node_uri, RDF.type, sme_subtype))


def _emit_property_value(g: Graph, node_uri: URIRef, node: dict) -> None:
    value = node.get("value")
    value_type = node.get("valueType")
    xsd_dt: URIRef | None = None
    if value_type:
        dt = _VALUE_TYPE_TO_AAS_DATATYPE.get(str(value_type))
        if dt is not None:
            g.add((node_uri, P_PROP_VALUE_TYPE, dt))
        else:
            g.add((node_uri, P_PROP_VALUE_TYPE, Literal(str(value_type))))
        # Map AAS valueType to xsd datatype for the literal itself.
        vt = str(value_type).lower()
        if "string" in vt:
            xsd_dt = XSD.string
        elif "boolean" in vt:
            xsd_dt = XSD.boolean
        elif "int" in vt or "long" in vt or "short" in vt or "byte" in vt:
            xsd_dt = XSD.integer
        elif "double" in vt or "float" in vt or "decimal" in vt:
            xsd_dt = XSD.decimal
        elif "datetime" in vt:
            xsd_dt = XSD.dateTime
    if value is not None and value != "":
        if xsd_dt is not None:
            g.add((node_uri, P_PROP_VALUE, Literal(str(value), datatype=xsd_dt)))
        else:
            g.add((node_uri, P_PROP_VALUE, Literal(str(value), datatype=XSD.string)))


def _emit_mlp_value(g: Graph, node_uri: URIRef, node: dict) -> None:
    """Each entry becomes an `aas:LangStringTextType` resource with language+text."""
    value = node.get("value")
    if not isinstance(value, list):
        return
    for entry in value:
        if not isinstance(entry, dict):
            continue
        text = entry.get("text")
        if not text:
            continue
        lang = entry.get("language") or "en"
        ls_uri = _next_anon(node_uri, "lang")
        g.add((node_uri, P_MLP_VALUE, ls_uri))
        g.add((ls_uri, RDF.type, AAS.LangStringTextType))
        g.add((ls_uri, P_LS_LANGUAGE, Literal(str(lang), datatype=XSD.string)))
        g.add((ls_uri, P_LS_TEXT, Literal(str(text), datatype=XSD.string)))
        g.add((ls_uri, P_LS_TEXT_TYPED, Literal(str(text), datatype=XSD.string)))


def _emit_range_value(g: Graph, node_uri: URIRef, node: dict) -> None:
    if "min" in node and node["min"] is not None:
        g.add((node_uri, P_RANGE_MIN, Literal(str(node["min"]), datatype=XSD.string)))
    if "max" in node and node["max"] is not None:
        g.add((node_uri, P_RANGE_MAX, Literal(str(node["max"]), datatype=XSD.string)))
    value_type = node.get("valueType")
    if value_type:
        dt = _VALUE_TYPE_TO_AAS_DATATYPE.get(str(value_type))
        if dt is not None:
            g.add((node_uri, P_PROP_VALUE_TYPE, dt))


def _emit_file_value(g: Graph, node_uri: URIRef, node: dict) -> None:
    value = node.get("value")
    if value:
        g.add((node_uri, P_FILE_VALUE, Literal(str(value), datatype=XSD.string)))
    content_type = node.get("contentType")
    if content_type:
        g.add((node_uri, P_FILE_CONTENT_TYPE, Literal(str(content_type), datatype=XSD.string)))


def _emit_relationship(g: Graph, node_uri: URIRef, node: dict) -> None:
    _emit_reference(g, node_uri, P_REL_FIRST, node.get("first"))
    _emit_reference(g, node_uri, P_REL_SECOND, node.get("second"))


def _emit_reference_element(g: Graph, node_uri: URIRef, node: dict) -> None:
    _emit_reference(g, node_uri, P_REF_ELEM_VALUE, node.get("value"))


def _emit_entity(g: Graph, node_uri: URIRef, node: dict) -> None:
    entity_type = node.get("entityType")
    if entity_type:
        # Emit as a typed enum individual: aas:EntityType/SelfManagedEntity etc.
        g.add((node_uri, P_ENTITY_TYPE, _enum_iri("EntityType", str(entity_type))))
    global_asset_id = node.get("globalAssetId")
    if global_asset_id:
        g.add((node_uri, P_ENTITY_GLOBAL_ID, Literal(str(global_asset_id), datatype=XSD.string)))


def _emit_administration(g: Graph, node_uri: URIRef, node: dict) -> None:
    admin = node.get("administration")
    if not isinstance(admin, dict):
        return
    admin_uri = _next_anon(node_uri, "admin")
    g.add((node_uri, P_HAS_ADMIN, admin_uri))
    g.add((admin_uri, RDF.type, AAS.AdministrativeInformation))
    if admin.get("version"):
        g.add((admin_uri, P_ADMIN_VERSION, Literal(str(admin["version"]), datatype=XSD.string)))
    if admin.get("revision"):
        g.add((admin_uri, P_ADMIN_REVISION, Literal(str(admin["revision"]), datatype=XSD.string)))


def _emit_asset_information(g: Graph, shell_uri: URIRef, asset_info: dict) -> URIRef | None:
    if not isinstance(asset_info, dict):
        return None
    ai_uri = _next_anon(shell_uri, "assetInformation")
    g.add((shell_uri, P_AAS_ASSET_INFO, ai_uri))
    g.add((ai_uri, RDF.type, AAS.AssetInformation))

    asset_kind = asset_info.get("assetKind") or "Instance"
    g.add((ai_uri, P_AI_ASSET_KIND, _enum_iri("AssetKind", str(asset_kind))))

    if asset_info.get("globalAssetId"):
        g.add((ai_uri, P_AI_GLOBAL_ASSET_ID, Literal(str(asset_info["globalAssetId"]), datatype=XSD.string)))
    if asset_info.get("assetType"):
        g.add((ai_uri, P_AI_ASSET_TYPE, Literal(str(asset_info["assetType"]), datatype=XSD.string)))

    for sai in asset_info.get("specificAssetIds", []) or []:
        if not isinstance(sai, dict):
            continue
        sai_uri = _next_anon(ai_uri, "specificAssetId")
        g.add((ai_uri, P_AI_SPECIFIC_IDS, sai_uri))
        g.add((sai_uri, RDF.type, AAS.SpecificAssetId))
        if sai.get("name"):
            g.add((sai_uri, P_SAI_NAME, Literal(str(sai["name"]), datatype=XSD.string)))
        if sai.get("value"):
            g.add((sai_uri, P_SAI_VALUE, Literal(str(sai["value"]), datatype=XSD.string)))
        external = sai.get("externalSubjectId")
        if isinstance(external, dict):
            _emit_reference(g, sai_uri, P_SAI_EXTERNAL, external)
    return ai_uri


def _walk_element(g: Graph, parent_uri: URIRef, parent_container_prop: URIRef,
                  element: dict, index: int) -> None:
    """Emit a single submodel element and recurse into its children."""
    if not isinstance(element, dict):
        return

    idshort = element.get("idShort")
    elem_uri = _mint_child_uri(parent_uri, idshort, index)
    g.add((parent_uri, parent_container_prop, elem_uri))

    model_type = element.get("modelType")
    aas_class = _AAS_CLASS_BY_MODEL_TYPE.get(model_type or "")
    if aas_class is not None:
        g.add((elem_uri, RDF.type, aas_class))

    _emit_referable(g, elem_uri, element)
    _emit_semantic_id(g, elem_uri, element)

    if model_type == "Property":
        _emit_property_value(g, elem_uri, element)
    elif model_type == "MultiLanguageProperty":
        _emit_mlp_value(g, elem_uri, element)
    elif model_type == "Range":
        _emit_range_value(g, elem_uri, element)
    elif model_type == "File":
        _emit_file_value(g, elem_uri, element)
    elif model_type == "RelationshipElement":
        _emit_relationship(g, elem_uri, element)
    elif model_type == "AnnotatedRelationshipElement":
        _emit_relationship(g, elem_uri, element)
        for i, child in enumerate(element.get("annotations", []) or []):
            _walk_element(g, elem_uri, P_SMC_VALUE, child, i)
    elif model_type == "ReferenceElement":
        _emit_reference_element(g, elem_uri, element)
    elif model_type == "SubmodelElementCollection":
        for i, child in enumerate(element.get("value", []) or []):
            _walk_element(g, elem_uri, P_SMC_VALUE, child, i)
    elif model_type == "SubmodelElementList":
        for i, child in enumerate(element.get("value", []) or []):
            _walk_element(g, elem_uri, P_SML_VALUE, child, i)
    elif model_type == "Entity":
        _emit_entity(g, elem_uri, element)
        for i, child in enumerate(element.get("statements", []) or []):
            _walk_element(g, elem_uri, P_ENTITY_STATEMENTS, child, i)


def _walk_submodel(g: Graph, shell_uri: URIRef, submodel: dict) -> URIRef | None:
    submodel_id = submodel.get("id")
    if not submodel_id:
        return None

    sm_uri = URIRef(submodel_id)
    g.add((sm_uri, RDF.type, AAS.Submodel))
    g.add((sm_uri, P_IDENTIFIABLE_ID, Literal(submodel_id, datatype=XSD.string)))
    _emit_referable(g, sm_uri, submodel)
    _emit_semantic_id(g, sm_uri, submodel)
    _emit_administration(g, sm_uri, submodel)

    sid = _first_semantic_id(submodel)
    subtype = SUBMODEL_TYPE_BY_SEMANTIC_ID.get(sid) if sid else None
    if subtype is not None:
        g.add((sm_uri, RDF.type, subtype))
        g.add((shell_uri, CSSX.hasSubmodel, sm_uri))
        typed_link = _TYPED_LINK_BY_SUBTYPE.get(subtype)
        if typed_link is not None:
            g.add((shell_uri, typed_link, sm_uri))
    else:
        g.add((shell_uri, CSSX.hasSubmodel, sm_uri))

    for i, element in enumerate(submodel.get("submodelElements", []) or []):
        _walk_element(g, sm_uri, P_SUBMODEL_ELEMENTS, element, i)

    return sm_uri


def _walk_shell(g: Graph, shell: dict, submodels_by_id: dict[str, dict]) -> None:
    shell_id = shell.get("id")
    if not shell_id:
        return

    shell_uri = URIRef(shell_id)
    g.add((shell_uri, RDF.type, AAS.AssetAdministrationShell))
    g.add((shell_uri, P_IDENTIFIABLE_ID, Literal(shell_id, datatype=XSD.string)))
    _emit_referable(g, shell_uri, shell)
    _emit_administration(g, shell_uri, shell)

    # AssetInformation: emit as a structured AAS resource so AssetInformationShape
    # passes; also keep the cssx:representsResource link to a css:Resource.
    asset_info = shell.get("assetInformation") or {}
    if isinstance(asset_info, dict):
        _emit_asset_information(g, shell_uri, asset_info)
    global_asset_id = asset_info.get("globalAssetId") if isinstance(asset_info, dict) else None
    resource_iri = global_asset_id or f"{shell_id}#asset"
    resource_uri = URIRef(resource_iri)
    g.add((resource_uri, RDF.type, CSS.Resource))
    g.add((shell_uri, CSSX.representsResource, resource_uri))
    g.add((resource_uri, CSSX.hasAAS, shell_uri))

    # derivedFrom is itself an aas:Reference
    if isinstance(shell.get("derivedFrom"), dict):
        _emit_reference(g, shell_uri, P_AAS_DERIVED_FROM, shell["derivedFrom"])

    # Each submodel reference is a Reference resource AND we walk into the
    # actual submodel body via the in-document submodels_by_id index.
    for ref in shell.get("submodels", []) or []:
        if isinstance(ref, dict):
            _emit_reference(g, shell_uri, P_AAS_SUBMODELS, ref)
        keys = ref.get("keys", []) if isinstance(ref, dict) else []
        if not keys:
            continue
        target_id = keys[-1].get("value") if isinstance(keys[-1], dict) else None
        if not target_id:
            continue
        submodel = submodels_by_id.get(str(target_id))
        if submodel:
            _walk_submodel(g, shell_uri, submodel)


# ------------------------------------------------------------------ public API


def serialize(document: dict) -> Graph:
    """Build an RDF graph from a parsed AAS JSON document."""
    _BNODE_COUNTER[0] = 0
    g = Graph()
    g.bind("aas", AAS)
    g.bind("css", CSS)
    g.bind("cssx", CSSX)
    g.bind("xsd", XSD)
    g.bind("rdfs", RDFS)

    submodels = document.get("submodels", []) or []
    submodels_by_id: dict[str, dict] = {}
    for sm in submodels:
        if isinstance(sm, dict) and sm.get("id"):
            submodels_by_id[str(sm["id"])] = sm

    for shell in document.get("assetAdministrationShells", []) or []:
        if isinstance(shell, dict):
            _walk_shell(g, shell, submodels_by_id)

    # Emit any submodels that aren't referenced by a shell, so they still get
    # validated structurally and by their cssx subclass.
    referenced: set[str] = set()
    for shell in document.get("assetAdministrationShells", []) or []:
        for ref in (shell or {}).get("submodels", []) or []:
            keys = ref.get("keys", []) if isinstance(ref, dict) else []
            if keys and isinstance(keys[-1], dict):
                value = keys[-1].get("value")
                if value:
                    referenced.add(str(value))
    for sm_id, sm in submodels_by_id.items():
        if sm_id in referenced:
            continue
        sm_uri = URIRef(sm_id)
        g.add((sm_uri, RDF.type, AAS.Submodel))
        g.add((sm_uri, P_IDENTIFIABLE_ID, Literal(sm_id, datatype=XSD.string)))
        _emit_referable(g, sm_uri, sm)
        _emit_semantic_id(g, sm_uri, sm)
        _emit_administration(g, sm_uri, sm)
        sid = _first_semantic_id(sm)
        subtype = SUBMODEL_TYPE_BY_SEMANTIC_ID.get(sid) if sid else None
        if subtype is not None:
            g.add((sm_uri, RDF.type, subtype))
        for i, element in enumerate(sm.get("submodelElements", []) or []):
            _walk_element(g, sm_uri, P_SUBMODEL_ELEMENTS, element, i)

    return g


def convert(aas_json_path: Path, output_ttl_path: Path) -> None:
    """Read AAS JSON from `aas_json_path`, write Turtle RDF to `output_ttl_path`."""
    with open(aas_json_path, "r", encoding="utf-8") as fh:
        document = json.load(fh)
    g = serialize(document)
    output_ttl_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(output_ttl_path), format="turtle")


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serialize AAS JSON to RDF aligned with CSSx_AAS.ttl.")
    parser.add_argument("--input",  required=True, help="Path to AAS JSON.")
    parser.add_argument("--output", required=True, help="Path to output Turtle file.")
    args = parser.parse_args(list(argv) if argv is not None else None)
    convert(Path(args.input), Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

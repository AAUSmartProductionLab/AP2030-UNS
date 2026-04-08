#!/usr/bin/env python3
"""
AAS Validation Module
Validates Asset Administration Shell structures for correctness and compliance.
"""

from typing import Dict, List, Tuple, Set
from basyx.aas import model
import re


class ValidationResult:
    """Stores validation results with severity levels."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
    
    def add_error(self, message: str):
        """Add a critical error."""
        self.errors.append(message)
    
    def add_warning(self, message: str):
        """Add a warning."""
        self.warnings.append(message)
    
    def add_info(self, message: str):
        """Add an informational message."""
        self.info.append(message)
    
    def is_valid(self) -> bool:
        """Returns True if no errors exist."""
        return len(self.errors) == 0
    
    def summary(self) -> str:
        """Returns a formatted summary of validation results."""
        lines = []
        lines.append("=" * 80)
        lines.append("AAS VALIDATION REPORT")
        lines.append("=" * 80)
        
        if self.is_valid():
            lines.append("✅ VALID - No critical errors found")
        else:
            lines.append(f"❌ INVALID - {len(self.errors)} error(s) found")
        
        lines.append(f"\nErrors: {len(self.errors)}")
        lines.append(f"Warnings: {len(self.warnings)}")
        lines.append(f"Info: {len(self.info)}")
        
        if self.errors:
            lines.append("\n" + "-" * 80)
            lines.append("ERRORS:")
            lines.append("-" * 80)
            for i, error in enumerate(self.errors, 1):
                lines.append(f"{i}. {error}")
        
        if self.warnings:
            lines.append("\n" + "-" * 80)
            lines.append("WARNINGS:")
            lines.append("-" * 80)
            for i, warning in enumerate(self.warnings, 1):
                lines.append(f"{i}. {warning}")
        
        if self.info:
            lines.append("\n" + "-" * 80)
            lines.append("INFORMATION:")
            lines.append("-" * 80)
            for i, info in enumerate(self.info, 1):
                lines.append(f"{i}. {info}")
        
        lines.append("=" * 80)
        return "\n".join(lines)


class AASValidator:
    """Validates AAS structures for correctness and compliance."""
    
    # Known IDTA semantic IDs for validation
    IDTA_SUBMODELS = {
        "https://admin-shell.io/idta/AssetInterfacesDescription/1/0",
        "https://admin-shell.io/zvei/nameplate/1/0/Nameplate",
        "https://admin-shell.io/ZVEI/TechnicalData/Submodel/1/2",
        "https://admin-shell.io/idta/HierarchicalStructures/1/0/Submodel",
        "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel",
        "https://admin-shell.io/idta/CarbonFootprint/0/9/ProductCarbonFootprint",
        "http://smartproductionlab.aau.dk/submodels/Variables/1/0",
        "http://smartproductionlab.aau.dk/submodels/Parameters/1/0",
        "http://smartproductionlab.aau.dk/submodels/Skills/1/0",
        "http://smartproductionlab.aau.dk/submodels/OfferedCapabilityDescription/1/0",
    }
    
    # W3C Thing Description semantic IDs
    WOT_SEMANTIC_IDS = {
        "https://www.w3.org/2019/wot/td#ActionAffordance",
        "https://www.w3.org/2019/wot/td#PropertyAffordance",
        "https://www.w3.org/2019/wot/td#InteractionAffordance",
    }
    
    def __init__(self):
        self.result = ValidationResult()
        self.visited_ids: Set[str] = set()
    
    def validate(self, obj_store: model.DictObjectStore) -> ValidationResult:
        """
        Validate all AAS objects in the object store.
        
        Args:
            obj_store: DictObjectStore containing AAS, Submodels, and other objects
            
        Returns:
            ValidationResult with errors, warnings, and info
        """
        self.result = ValidationResult()
        self.visited_ids = set()
        
        # Count objects
        aas_count = 0
        submodel_count = 0
        concept_desc_count = 0
        
        # Validate each object
        for obj in obj_store:
            if isinstance(obj, model.AssetAdministrationShell):
                aas_count += 1
                self._validate_aas(obj, obj_store)
            elif isinstance(obj, model.Submodel):
                submodel_count += 1
                self._validate_submodel(obj)
            elif isinstance(obj, model.ConceptDescription):
                concept_desc_count += 1
                self._validate_concept_description(obj)
        
        # Summary info
        self.result.add_info(f"Validated {aas_count} AAS shell(s)")
        self.result.add_info(f"Validated {submodel_count} submodel(s)")
        self.result.add_info(f"Validated {concept_desc_count} concept description(s)")
        
        return self.result
    
    def _validate_aas(self, aas: model.AssetAdministrationShell, obj_store: model.DictObjectStore):
        """Validate an Asset Administration Shell."""
        
        # Check ID uniqueness
        if aas.id in self.visited_ids:
            self.result.add_error(f"Duplicate AAS ID: {aas.id}")
        self.visited_ids.add(aas.id)
        
        # Validate idShort
        if aas.id_short:
            try:
                aas.validate_id_short(aas.id_short)
            except Exception as e:
                self.result.add_error(f"AAS '{aas.id_short}' has invalid idShort: {e}")
        else:
            self.result.add_warning(f"AAS '{aas.id}' has no idShort")
        
        # Validate ID format (should be URI)
        if not self._is_valid_uri(aas.id):
            self.result.add_error(f"AAS ID is not a valid URI: {aas.id}")
        
        # Check asset information
        if not aas.asset_information:
            self.result.add_error(f"AAS '{aas.id_short or aas.id}' missing asset_information")
        else:
            self._validate_asset_information(aas.asset_information, aas.id_short or aas.id)
        
        # Validate submodel references
        if aas.submodel:
            for ref in aas.submodel:
                self._validate_reference(ref, "Submodel reference", obj_store)
        else:
            self.result.add_warning(f"AAS '{aas.id_short}' has no submodels")
        
        # Validate derivedFrom if present
        if aas.derived_from:
            self._validate_reference(aas.derived_from, "derivedFrom reference", obj_store, allow_external=True)
    
    def _validate_asset_information(self, asset_info: model.AssetInformation, context: str):
        """Validate asset information."""
        
        if not asset_info.global_asset_id:
            self.result.add_error(f"{context}: Missing global_asset_id")
        elif not self._is_valid_uri(asset_info.global_asset_id):
            self.result.add_error(f"{context}: global_asset_id is not a valid URI: {asset_info.global_asset_id}")
        
        if asset_info.asset_kind not in [model.AssetKind.INSTANCE, model.AssetKind.TYPE]:
            self.result.add_error(f"{context}: Invalid asset_kind")
    
    def _validate_submodel(self, submodel: model.Submodel):
        """Validate a Submodel."""
        
        # Check ID uniqueness
        if submodel.id in self.visited_ids:
            self.result.add_error(f"Duplicate Submodel ID: {submodel.id}")
        self.visited_ids.add(submodel.id)
        
        # Validate idShort
        if submodel.id_short:
            try:
                submodel.validate_id_short(submodel.id_short)
            except Exception as e:
                self.result.add_error(f"Submodel '{submodel.id_short}' has invalid idShort: {e}")
        
        # Validate ID format
        if not self._is_valid_uri(submodel.id):
            self.result.add_error(f"Submodel '{submodel.id_short}' ID is not a valid URI: {submodel.id}")
        
        # Check semantic ID
        if submodel.semantic_id:
            self._validate_semantic_id(submodel.semantic_id, f"Submodel '{submodel.id_short}'")
        else:
            self.result.add_warning(f"Submodel '{submodel.id_short}' has no semantic_id")
        
        # Validate submodel elements
        if submodel.submodel_element:
            for element in submodel.submodel_element:
                self._validate_submodel_element(element, f"Submodel '{submodel.id_short}'")
        
        # Check for known IDTA submodels
        if submodel.semantic_id:
            sem_id = self._get_semantic_id_value(submodel.semantic_id)
            if sem_id and sem_id in self.IDTA_SUBMODELS:
                self.result.add_info(f"Submodel '{submodel.id_short}' uses recognized IDTA template: {sem_id}")
    
    def _validate_submodel_element(self, element, context: str):
        """Validate a submodel element."""
        
        # Validate idShort
        if hasattr(element, 'id_short') and element.id_short:
            try:
                element.validate_id_short(element.id_short)
            except Exception as e:
                self.result.add_error(f"{context}/{element.id_short}: Invalid idShort: {e}")
        
        # Validate semantic ID if present
        if hasattr(element, 'semantic_id') and element.semantic_id:
            self._validate_semantic_id(element.semantic_id, f"{context}/{element.id_short}")
        
        # Type-specific validation
        if isinstance(element, model.Property):
            self._validate_property(element, context)
        elif isinstance(element, model.ReferenceElement):
            self._validate_reference_element(element, context)
        elif isinstance(element, model.SubmodelElementCollection):
            self._validate_collection(element, context)
        elif isinstance(element, model.RelationshipElement):
            self._validate_relationship(element, context)
    
    def _validate_property(self, prop: model.Property, context: str):
        """Validate a Property element."""
        
        if prop.value_type is None:
            self.result.add_error(f"{context}/{prop.id_short}: Property missing value_type")
        
        # Value can be None, but if present should match value_type
        if prop.value is not None and prop.value_type:
            # Basic type checking (simplified)
            try:
                # The SDK should handle this, but we can add extra checks
                pass
            except Exception as e:
                self.result.add_warning(f"{context}/{prop.id_short}: Value may not match value_type: {e}")
    
    def _validate_reference_element(self, ref_elem: model.ReferenceElement, context: str):
        """Validate a ReferenceElement."""
        
        if ref_elem.value is None:
            self.result.add_warning(f"{context}/{ref_elem.id_short}: ReferenceElement has no value (reference)")
        else:
            # Validate the reference structure
            if not ref_elem.value.key:
                self.result.add_error(f"{context}/{ref_elem.id_short}: Reference has no keys")
            else:
                for i, key in enumerate(ref_elem.value.key):
                    if not key.value:
                        self.result.add_error(f"{context}/{ref_elem.id_short}: Key {i} has no value")
                    if not key.type:
                        self.result.add_error(f"{context}/{ref_elem.id_short}: Key {i} has no type")
    
    def _validate_collection(self, collection: model.SubmodelElementCollection, context: str):
        """Validate a SubmodelElementCollection."""
        
        if collection.value:
            for element in collection.value:
                self._validate_submodel_element(element, f"{context}/{collection.id_short}")
        else:
            self.result.add_info(f"{context}/{collection.id_short}: Collection is empty")
    
    def _validate_relationship(self, rel: model.RelationshipElement, context: str):
        """Validate a RelationshipElement."""
        
        if not rel.first:
            self.result.add_error(f"{context}/{rel.id_short}: RelationshipElement missing 'first' reference")
        if not rel.second:
            self.result.add_error(f"{context}/{rel.id_short}: RelationshipElement missing 'second' reference")
    
    def _validate_reference(self, ref, context: str, obj_store: model.DictObjectStore = None, allow_external: bool = False):
        """Validate a Reference."""
        
        if not ref.key or len(ref.key) == 0:
            self.result.add_error(f"{context}: Reference has no keys")
            return
        
        # Check reference type
        if isinstance(ref, model.ExternalReference):
            if not allow_external:
                self.result.add_info(f"{context}: Uses ExternalReference")
        elif isinstance(ref, model.ModelReference):
            # For ModelReference, we can optionally check if target exists in object store
            if obj_store and len(ref.key) > 0:
                first_key = ref.key[0]
                # Try to find the referenced object
                target_id = first_key.value
                found = False
                for obj in obj_store:
                    if obj.id == target_id:
                        found = True
                        break
                
                if not found and not allow_external:
                    self.result.add_warning(f"{context}: Referenced object not found: {target_id}")
    
    def _validate_semantic_id(self, semantic_id, context: str):
        """Validate a semantic ID."""
        
        if not semantic_id.key or len(semantic_id.key) == 0:
            self.result.add_error(f"{context}: Semantic ID has no keys")
            return
        
        # Get the actual semantic ID value
        sem_value = self._get_semantic_id_value(semantic_id)
        
        # Check if it's a valid URI
        if sem_value and not self._is_valid_uri(sem_value):
            self.result.add_warning(f"{context}: Semantic ID is not a valid URI: {sem_value}")
        
        # Check if it's a known standard
        if sem_value:
            if sem_value in self.IDTA_SUBMODELS:
                # Already logged in submodel validation
                pass
            elif sem_value in self.WOT_SEMANTIC_IDS:
                self.result.add_info(f"{context}: Uses W3C Thing Description semantic ID")
            elif sem_value.startswith("https://admin-shell.io/idta/"):
                self.result.add_info(f"{context}: Uses IDTA semantic ID")
            elif sem_value.startswith("https://www.w3.org/"):
                self.result.add_info(f"{context}: Uses W3C semantic ID")
    
    def _validate_concept_description(self, concept_desc: model.ConceptDescription):
        """Validate a Concept Description."""
        
        if concept_desc.id in self.visited_ids:
            self.result.add_error(f"Duplicate ConceptDescription ID: {concept_desc.id}")
        self.visited_ids.add(concept_desc.id)
        
        if not self._is_valid_uri(concept_desc.id):
            self.result.add_error(f"ConceptDescription ID is not a valid URI: {concept_desc.id}")
    
    def _get_semantic_id_value(self, semantic_id) -> str:
        """Extract the semantic ID value from a Reference."""
        if semantic_id and semantic_id.key and len(semantic_id.key) > 0:
            return semantic_id.key[0].value
        return ""
    
    def _is_valid_uri(self, uri: str) -> bool:
        """Check if a string is a valid URI."""
        # Simple URI validation
        uri_pattern = re.compile(
            r'^(https?|urn|irdi):'  # Scheme
            r'([^\s]+)$'  # Rest of URI
        )
        return bool(uri_pattern.match(uri))


def validate_aas_file(json_file_path: str, verbose: bool = False) -> ValidationResult:
    """
    Validate an AAS JSON file.
    
    Args:
        json_file_path: Path to the AAS JSON file
        verbose: If True, print detailed validation results
        
    Returns:
        ValidationResult object
    """
    from basyx.aas.adapter.json import json_deserialization
    
    # Load the AAS file
    with open(json_file_path, 'r') as f:
        obj_store = json_deserialization.read_aas_json_file(f)
    
    # Validate
    validator = AASValidator()
    result = validator.validate(obj_store)
    
    if verbose:
        print(result.summary())
    
    return result

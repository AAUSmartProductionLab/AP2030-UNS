"""
AASX File Parser

Extracts AAS and submodel information from AASX packages using BaSyx Python SDK.
"""

import logging
from pathlib import Path
from typing import List

from basyx.aas import model
from basyx.aas.adapter import aasx

logger = logging.getLogger(__name__)


class AASXParser:
    """
    Parser for AASX files using the BaSyx Python SDK.
    
    This class now uses the official SDK for parsing AASX files,
    eliminating the need for manual XML parsing and ensuring
    compliance with the AAS specification.
    """

    def __init__(self, aasx_path: str):
        self.aasx_path = Path(aasx_path)

    def parse(self) -> model.DictObjectStore[model.Identifiable]:
        """
        Parse AASX file and extract AAS objects using BaSyx SDK.
        
        Returns:
            DictObjectStore containing all parsed AAS, Submodels, and ConceptDescriptions
        
        Raises:
            FileNotFoundError: If the AASX file doesn't exist
            Exception: For any parsing errors
        """
        try:
            if not self.aasx_path.exists():
                raise FileNotFoundError(f"AASX file not found: {self.aasx_path}")
            
            logger.info(f"Parsing AASX file: {self.aasx_path}")
            
            # Use BaSyx SDK to read the AASX file
            # This returns a DictObjectStore containing all objects
            object_store = model.DictObjectStore()
            
            with aasx.AASXReader(str(self.aasx_path)) as reader:
                # Read all objects from the AASX file into the object store
                reader.read_into(object_store)
            
            # Log what we found
            shells = list(object_store.get_identifiable_by_type(model.AssetAdministrationShell))
            submodels = list(object_store.get_identifiable_by_type(model.Submodel))
            concept_descriptions = list(object_store.get_identifiable_by_type(model.ConceptDescription))
            
            logger.info(f"Parsed {len(shells)} AAS shell(s), "
                       f"{len(submodels)} submodel(s), "
                       f"{len(concept_descriptions)} concept description(s)")
            
            return object_store

        except Exception as e:
            logger.error(f"Error parsing AASX file: {e}", exc_info=True)
            raise
    
    def get_shells(self, object_store: model.DictObjectStore) -> List[model.AssetAdministrationShell]:
        """Extract all AAS shells from the object store."""
        return [obj for obj in object_store if isinstance(obj, model.AssetAdministrationShell)]
    
    def get_submodels(self, object_store: model.DictObjectStore) -> List[model.Submodel]:
        """Extract all submodels from the object store."""
        return [obj for obj in object_store if isinstance(obj, model.Submodel)]
    
    def get_concept_descriptions(self, object_store: model.DictObjectStore) -> List[model.ConceptDescription]:
        """Extract all concept descriptions from the object store."""
        return [obj for obj in object_store if isinstance(obj, model.ConceptDescription)]

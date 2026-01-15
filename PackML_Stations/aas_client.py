#!/usr/bin/env python3
"""
AAS Client wrapper using BaSyx Python SDK for deserialization
Combines requests for HTTP communication with BaSyx SDK for parsing AAS objects
"""

import requests
import json
import base64
import logging
from typing import Optional, List
from basyx.aas import model
from basyx.aas.adapter.json import AASFromJsonDecoder

# Suppress BaSyx SDK deserialization errors for malformed AAS objects
logging.getLogger('basyx.aas.adapter.json').setLevel(logging.CRITICAL)


class AASClient:
    """Client for interacting with AAS HTTP servers using BaSyx SDK for deserialization"""
    
    def __init__(self, server_url: str, registry_url: Optional[str] = None):
        """
        Initialize AAS client
        
        Args:
            server_url: Base URL of the AAS server (e.g., "http://192.168.0.104:8081")
            registry_url: Optional URL of the AAS registry
        """
        self.server_url = server_url.rstrip('/')
        self.registry_url = registry_url.rstrip('/') if registry_url else None
    
    def get_all_aas(self) -> List[model.AssetAdministrationShell]:
        """
        Get all Asset Administration Shells from the server
        
        Returns:
            List of AssetAdministrationShell objects
        """
        try:
            response = requests.get(f"{self.server_url}/shells")
            if response.status_code != 200:
                return []
            
            shells_data = response.json().get('result', [])
            shells = []
            
            for shell_data in shells_data:
                try:
                    # Parse using BaSyx SDK's AASFromJsonDecoder to include submodel references
                    shell = json.loads(json.dumps(shell_data), cls=AASFromJsonDecoder)
                    if isinstance(shell, model.AssetAdministrationShell):
                        shells.append(shell)
                except (TypeError, ValueError, KeyError) as e:
                    # Skip malformed AAS shells (e.g., invalid extension types)
                    # These errors are logged by the decoder in failsafe mode
                    continue
                except Exception as e:
                    # Log unexpected errors but continue processing
                    print(f"Warning: Unexpected error parsing shell {shell_data.get('idShort', 'unknown')}: {e}")
                    continue
            
            return shells
            
        except Exception as e:
            print(f"Error fetching shells: {e}")
            return []
    
    def get_aas_by_id(self, aas_id: str) -> Optional[model.AssetAdministrationShell]:
        """
        Get a specific Asset Administration Shell by ID
        
        Args:
            aas_id: The identifier of the AAS
            
        Returns:
            AssetAdministrationShell object or None
        """
        try:
            encoded_id = base64.urlsafe_b64encode(aas_id.encode()).decode().rstrip('=')
            response = requests.get(f"{self.server_url}/shells/{encoded_id}")
            
            if response.status_code != 200:
                return None
            
            # Parse using BaSyx SDK
            shell = json.loads(response.text, cls=AASFromJsonDecoder)
            if isinstance(shell, model.AssetAdministrationShell):
                return shell
            
            return None
            
        except Exception as e:
            print(f"Error fetching AAS {aas_id}: {e}")
            return None
    
    def get_submodel_by_id(self, submodel_id: str) -> Optional[model.Submodel]:
        """
        Get a specific Submodel by ID
        
        Args:
            submodel_id: The identifier of the submodel
            
        Returns:
            Submodel object or None
        """
        try:
            encoded_id = base64.urlsafe_b64encode(submodel_id.encode()).decode().rstrip('=')
            response = requests.get(f"{self.server_url}/submodels/{encoded_id}")
            
            if response.status_code != 200:
                return None
            
            # Parse using BaSyx SDK
            submodel = json.loads(response.text, cls=AASFromJsonDecoder)
            if isinstance(submodel, model.Submodel):
                return submodel
            
            return None
            
        except Exception as e:
            print(f"Error fetching submodel {submodel_id}: {e}")
            return None
    
    def lookup_aas_by_asset_id(self, asset_id: str) -> Optional[str]:
        """
        Lookup AAS shell ID from global asset ID
        
        Args:
            asset_id: Global asset ID or AAS ID
            
        Returns:
            AAS ID or None
        """
        try:
            # If the ID looks like an AAS ID (contains '/aas/'), verify and return it
            if '/aas/' in asset_id:
                shells = self.get_all_aas()
                for shell in shells:
                    if shell.id == asset_id:
                        return asset_id
                # If not found, still return it (might work directly)
                return asset_id
            
            # Otherwise, treat it as a global asset ID and look it up
            shells = self.get_all_aas()
            for shell in shells:
                if shell.asset_information and shell.asset_information.global_asset_id == asset_id:
                    return shell.id
            
            print(f"Warning: Could not find AAS for asset {asset_id}")
            return None
            
        except Exception as e:
            print(f"Error looking up AAS for asset {asset_id}: {e}")
            return None
    
    def get_submodels_from_aas(self, aas_id: str) -> List[model.Submodel]:
        """
        Get all submodels referenced by an AAS
        
        Args:
            aas_id: The identifier of the AAS
            
        Returns:
            List of Submodel objects
        """
        try:
            shell = self.get_aas_by_id(aas_id)
            if not shell or not shell.submodel:
                return []
            
            submodels: List[model.Submodel] = []
            # shell.submodel is a set of ModelReferences
            for submodel_ref in shell.submodel:
                # Reference.key is a tuple of Key objects
                if submodel_ref.key:
                    for key in submodel_ref.key:
                        # Key has a value attribute containing the ID
                        submodel = self.get_submodel_by_id(key.value)
                        if submodel:
                            submodels.append(submodel)
                        break
            
            return submodels
            
        except Exception as e:
            print(f"Error fetching submodels for AAS {aas_id}: {e}")
            return []
    
    def find_submodel_by_semantic_id(self, aas_id: str, semantic_id_pattern: str) -> Optional[model.Submodel]:
        """
        Find a submodel in an AAS by semantic ID pattern
        
        Args:
            aas_id: The identifier of the AAS
            semantic_id_pattern: Pattern to match in the semantic ID
            
        Returns:
            Submodel object or None
        """
        try:
            submodels = self.get_submodels_from_aas(aas_id)
            
            for submodel in submodels:
                if submodel.semantic_id:
                    for key in submodel.semantic_id.key:
                        if semantic_id_pattern in key.value:
                            return submodel
            
            return None
            
        except Exception as e:
            print(f"Error finding submodel: {e}")
            return None

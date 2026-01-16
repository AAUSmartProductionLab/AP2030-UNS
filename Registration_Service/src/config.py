"""
BaSyx Server Configuration

Manages URLs and endpoints for BaSyx components.
"""

from typing import Optional
from .core.constants import (
    DEFAULT_BASYX_URL,
    DEFAULT_BASYX_INTERNAL_URL,
    EXTERNAL_BASYX_HOST,
    BaSyxEndpoints,
    BaSyxPorts
)


class BaSyxConfig:
    """
    BaSyx server configuration.
    
    Manages URLs and endpoints for BaSyx components with support
    for both internal (Docker network) and external URLs.
    """

    def __init__(self, 
                 base_url: str = DEFAULT_BASYX_URL,
                 internal_url: Optional[str] = None,
                 external_host: Optional[str] = None):
        """
        Initialize BaSyx configuration.
        
        Args:
            base_url: External BaSyx server URL (default: http://localhost:8081)
            internal_url: Internal Docker network URL (default: http://aas-env:8081)
            external_host: External host for registry descriptors (default: 192.168.0.104)
        """
        self.base_url = base_url
        self.internal_url = internal_url or DEFAULT_BASYX_INTERNAL_URL
        self.external_host = external_host or EXTERNAL_BASYX_HOST
        
        # Extract host from base_url for registry endpoints
        # BaSyx 2.0 uses different registry endpoints
        host_part = base_url.rsplit(':', 1)[0]  # Remove port from base_url
        
        # Registry URLs
        self.aas_registry_url = f"{host_part}:{BaSyxPorts.AAS_REGISTRY}{BaSyxEndpoints.SHELL_DESCRIPTORS}"
        self.submodel_registry_url = f"{host_part}:{BaSyxPorts.SUBMODEL_REGISTRY}{BaSyxEndpoints.SUBMODEL_DESCRIPTORS}"
        
        # Repository URLs
        self.aas_repo_url = f"{base_url}{BaSyxEndpoints.SHELLS}"
        self.submodel_repo_url = f"{base_url}{BaSyxEndpoints.SUBMODELS}"
        self.concept_desc_url = f"{base_url}{BaSyxEndpoints.CONCEPT_DESCRIPTIONS}"
    
    def get_external_url(self) -> str:
        """
        Get external URL for registry descriptors.
        
        Returns:
            URL with external host (e.g., http://192.168.0.104:8081)
        """
        # Extract port from base_url
        if ':' in self.base_url:
            port = self.base_url.rsplit(':', 1)[1].rstrip('/')
        else:
            port = '8081'
        
        return f"http://{self.external_host}:{port}"
    
    def get_internal_url_for_databridge(self) -> str:
        """
        Get internal BaSyx URL for DataBridge (Docker network).
        
        Returns:
            Internal URL (e.g., http://aas-env:8081)
        """
        return self.internal_url

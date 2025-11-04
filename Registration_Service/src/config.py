"""
BaSyx Server Configuration

Manages URLs and endpoints for BaSyx components.
"""


class BaSyxConfig:
    """BaSyx server configuration"""

    def __init__(self, base_url: str = "http://localhost:8081"):
        self.base_url = base_url
        # Extract host from base_url for registry endpoints
        # BaSyx 2.0 uses different registry endpoints
        host_part = base_url.rsplit(':', 1)[0]  # Remove port from base_url
        self.aas_registry_url = f"{host_part}:8082/shell-descriptors"
        self.submodel_registry_url = f"{host_part}:8083/submodel-descriptors"
        self.aas_repo_url = f"{base_url}/shells"
        self.submodel_repo_url = f"{base_url}/submodels"

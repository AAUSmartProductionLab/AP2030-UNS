"""
HTTP client for BaSyx API interactions.

Provides a consistent interface for making HTTP requests with proper
error handling, logging, and retry logic.
"""

import logging
from typing import Any, Dict, Optional
import requests

from .constants import HTTPStatus, TimeoutDefaults

logger = logging.getLogger(__name__)


class HTTPError(Exception):
    """Exception raised for HTTP errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[requests.Response] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class HTTPClient:
    """
    HTTP client for making requests with consistent error handling.
    
    Features:
    - Automatic JSON content-type headers
    - Standardized error handling
    - Request logging
    - Timeout configuration
    """
    
    def __init__(self, timeout: int = TimeoutDefaults.HTTP_REQUEST):
        """
        Initialize HTTP client.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """
        Make GET request.
        
        Args:
            url: Target URL
            **kwargs: Additional arguments passed to requests.get
            
        Returns:
            Response object
            
        Raises:
            HTTPError: If request fails
        """
        return self._request('GET', url, **kwargs)
    
    def post(self, url: str, data: Any = None, **kwargs) -> requests.Response:
        """
        Make POST request.
        
        Args:
            url: Target URL
            data: JSON data to send
            **kwargs: Additional arguments passed to requests.post
            
        Returns:
            Response object
            
        Raises:
            HTTPError: If request fails
        """
        return self._request('POST', url, json=data, **kwargs)
    
    def put(self, url: str, data: Any = None, **kwargs) -> requests.Response:
        """
        Make PUT request.
        
        Args:
            url: Target URL
            data: JSON data to send
            **kwargs: Additional arguments passed to requests.put
            
        Returns:
            Response object
            
        Raises:
            HTTPError: If request fails
        """
        return self._request('PUT', url, json=data, **kwargs)
    
    def delete(self, url: str, **kwargs) -> requests.Response:
        """
        Make DELETE request.
        
        Args:
            url: Target URL
            **kwargs: Additional arguments passed to requests.delete
            
        Returns:
            Response object
            
        Raises:
            HTTPError: If request fails
        """
        return self._request('DELETE', url, **kwargs)
    
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make HTTP request with error handling.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Target URL
            **kwargs: Additional arguments passed to requests
            
        Returns:
            Response object
            
        Raises:
            HTTPError: If request fails
        """
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
        try:
            response = self.session.request(method, url, **kwargs)
            
            # Log non-success responses
            if response.status_code not in [
                HTTPStatus.OK,
                HTTPStatus.CREATED,
                HTTPStatus.NO_CONTENT,
                HTTPStatus.NOT_FOUND,  # Sometimes expected
                HTTPStatus.CONFLICT    # Sometimes expected (resource exists)
            ]:
                logger.warning(f"HTTP {response.status_code} for {method} {url}")
            
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {method} {url} - {e}")
            raise HTTPError(f"HTTP request failed: {e}") from e
    
    def is_success(self, response: requests.Response) -> bool:
        """
        Check if response indicates success.
        
        Args:
            response: Response to check
            
        Returns:
            True if status code indicates success
        """
        return response.status_code in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.NO_CONTENT]
    
    def is_conflict(self, response: requests.Response) -> bool:
        """
        Check if response indicates resource conflict (already exists).
        
        Args:
            response: Response to check
            
        Returns:
            True if status code is 409 CONFLICT
        """
        return response.status_code == HTTPStatus.CONFLICT
    
    def is_not_found(self, response: requests.Response) -> bool:
        """
        Check if response indicates resource not found.
        
        Args:
            response: Response to check
            
        Returns:
            True if status code is 404 NOT FOUND
        """
        return response.status_code == HTTPStatus.NOT_FOUND
    
    def close(self):
        """Close the session."""
        self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

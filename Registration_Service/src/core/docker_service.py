"""
Docker service for container management.

Provides utilities for interacting with Docker containers
(restart, logs, status checks, etc.).
"""

import logging
import subprocess
from typing import Optional, List
from pathlib import Path

from .constants import TimeoutDefaults, ContainerNames

logger = logging.getLogger(__name__)


class DockerError(Exception):
    """Exception raised for Docker operation errors."""
    pass


class DockerService:
    """
    Service for managing Docker containers.
    
    Provides methods for restarting containers, checking status,
    and retrieving logs.
    """
    
    def __init__(self):
        """Initialize Docker service."""
        self._docker_available = None
    
    def is_available(self) -> bool:
        """
        Check if Docker is available on the system.
        
        Returns:
            True if Docker CLI is available
        """
        if self._docker_available is None:
            try:
                result = subprocess.run(
                    ['which', 'docker'],
                    capture_output=True,
                    timeout=5
                )
                self._docker_available = result.returncode == 0
            except Exception:
                self._docker_available = False
        
        return self._docker_available
    
    def restart_container(self, container_name: str, timeout: int = TimeoutDefaults.DOCKER_RESTART) -> bool:
        """
        Restart a Docker container.
        
        Args:
            container_name: Name of the container to restart
            timeout: Timeout for the restart operation
            
        Returns:
            True if restart successful, False otherwise
        """
        if not self.is_available():
            logger.warning("Docker not available, skipping container restart")
            return False
        
        try:
            logger.info(f"Restarting container: {container_name}")
            result = subprocess.run(
                ['docker', 'restart', container_name],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                logger.info(f"✓ Restarted {container_name}")
                return True
            else:
                logger.warning(f"Failed to restart {container_name}: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout restarting {container_name}")
            return False
        except Exception as e:
            logger.warning(f"Could not restart {container_name}: {e}")
            return False
    
    def get_container_logs(self, container_name: str, tail: int = 50) -> Optional[str]:
        """
        Get logs from a Docker container.
        
        Args:
            container_name: Name of the container
            tail: Number of lines to retrieve from the end
            
        Returns:
            Log output as string, or None if failed
        """
        if not self.is_available():
            return None
        
        try:
            result = subprocess.run(
                ['docker', 'logs', container_name, '--tail', str(tail)],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                logger.warning(f"Failed to get logs for {container_name}: {result.stderr}")
                return None
                
        except Exception as e:
            logger.warning(f"Could not get logs for {container_name}: {e}")
            return None
    
    def is_container_running(self, container_name: str) -> bool:
        """
        Check if a container is running.
        
        Args:
            container_name: Name of the container
            
        Returns:
            True if container is running
        """
        if not self.is_available():
            return False
        
        try:
            result = subprocess.run(
                ['docker', 'inspect', '-f', '{{.State.Running}}', container_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            return result.returncode == 0 and result.stdout.strip() == 'true'
            
        except Exception as e:
            logger.debug(f"Could not check status for {container_name}: {e}")
            return False
    
    def execute_in_container(self, container_name: str, command: List[str]) -> Optional[str]:
        """
        Execute a command inside a container.
        
        Args:
            container_name: Name of the container
            command: Command to execute (as list of arguments)
            
        Returns:
            Command output as string, or None if failed
        """
        if not self.is_available():
            return None
        
        try:
            cmd = ['docker', 'exec', container_name] + command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                logger.warning(f"Command failed in {container_name}: {result.stderr}")
                return None
                
        except Exception as e:
            logger.warning(f"Could not execute command in {container_name}: {e}")
            return None
    
    def restart_databridge(self) -> bool:
        """
        Restart the DataBridge container.
        
        Returns:
            True if successful
        """
        return self.restart_container(ContainerNames.DATABRIDGE)
    
    def restart_operation_delegation(self) -> bool:
        """
        Restart the Operation Delegation container.
        
        Returns:
            True if successful
        """
        return self.restart_container(ContainerNames.OPERATION_DELEGATION)

"""
ID utilities for AAS and MQTT topic handling.

Provides functions for encoding, sanitizing, and transforming identifiers.
"""

import base64
import re


def encode_aas_id(aas_id: str) -> str:
    """
    Encode AAS ID to base64 for URL usage.
    
    Args:
        aas_id: AAS identifier string
        
    Returns:
        Base64-encoded ID
    """
    return base64.b64encode(aas_id.encode()).decode()


def sanitize_id(identifier: str) -> str:
    """
    Sanitize identifier for use in file names and unique IDs.
    
    Replaces non-alphanumeric characters with underscores.
    
    Args:
        identifier: Raw identifier
        
    Returns:
        Sanitized identifier safe for file names
    """
    # Replace non-alphanumeric characters (except hyphens) with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9\-]', '_', identifier)
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    return sanitized.strip('_')


def topic_to_id(topic: str) -> str:
    """
    Convert MQTT topic to a unique identifier.
    
    Args:
        topic: MQTT topic string
        
    Returns:
        Unique ID derived from topic
    """
    # Replace slashes and special chars with underscores
    topic_id = topic.replace('/', '_').replace('+', 'wildcard').replace('#', 'multilevel')
    return sanitize_id(topic_id)

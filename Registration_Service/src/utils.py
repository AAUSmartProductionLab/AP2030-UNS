"""
Utility Functions (Legacy Compatibility)

This module maintains backward compatibility.
New code should import from src.utils.* directly.
"""

from .utils.formatters import save_json_file, load_json_file, ensure_directory
from .utils.id_utils import encode_aas_id, sanitize_id, topic_to_id

# Re-export for backward compatibility
__all__ = [
    'save_json_file',
    'load_json_file',
    'ensure_directory',
    'encode_aas_id',
    'sanitize_id',
    'topic_to_id',
]


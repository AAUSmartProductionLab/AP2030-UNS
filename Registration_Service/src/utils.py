"""
Utility Functions

Helper functions for the AAS registration service.
"""

import json
from pathlib import Path
from typing import Any


def save_json_file(file_path: Path, data: Any, indent: int = 2):
    """Save data to JSON file with formatting"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def load_json_file(file_path: Path) -> Any:
    """Load data from JSON file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def ensure_directory(dir_path: Path) -> Path:
    """Ensure directory exists, create if needed"""
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path

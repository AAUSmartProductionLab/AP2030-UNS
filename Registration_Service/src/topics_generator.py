"""
Topics Generator for Operation Delegation Service

Generates and manages topics.json configuration for the Operation Delegation
Service directly from YAML configuration files.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

from .config_parser import ConfigParser, parse_config_file

logger = logging.getLogger(__name__)


class TopicsGenerator:
    """
    Generates topics.json for Operation Delegation Service.
    
    The topics.json maps asset IDs to their MQTT command/response topics
    for operation invocation.
    """
    
    def __init__(self, output_path: str = None):
        """
        Initialize the topics generator.
        
        Args:
            output_path: Path to topics.json file (default: ../OperationDelegation/config/topics.json)
        """
        if output_path:
            self.output_path = Path(output_path)
        else:
            # Default to OperationDelegation/config/topics.json relative to Registration_Service
            script_dir = Path(__file__).resolve().parent.parent
            self.output_path = script_dir.parent / 'OperationDelegation' / 'config' / 'topics.json'
        
        # Current topics configuration
        self.topics: Dict[str, Any] = {}
        
        # Load existing configuration if present
        self._load_existing()
    
    def _load_existing(self):
        """Load existing topics.json if it exists"""
        if self.output_path.exists():
            try:
                with open(self.output_path, 'r') as f:
                    self.topics = json.load(f)
                logger.info(f"Loaded existing topics.json with {len(self.topics)} assets")
            except Exception as e:
                logger.warning(f"Could not load existing topics.json: {e}")
                self.topics = {}
    
    def add_from_config(self, config: ConfigParser) -> bool:
        """
        Add/update topics from a parsed configuration.
        
        Args:
            config: Parsed ConfigParser instance
            
        Returns:
            True if successful
        """
        try:
            asset_id = config.system_id
            entry = config.get_operation_delegation_entry()
            
            # Only add if there are skills (actions)
            if entry.get('skills'):
                self.topics[asset_id] = entry
                logger.info(f"Added {len(entry['skills'])} skills for {asset_id}")
                return True
            else:
                logger.debug(f"No skills found for {asset_id}, skipping")
                return True
                
        except Exception as e:
            logger.error(f"Failed to add config: {e}")
            return False
    
    def add_from_config_file(self, config_path: str) -> bool:
        """
        Add/update topics from a YAML configuration file.
        
        Args:
            config_path: Path to YAML config file
            
        Returns:
            True if successful
        """
        try:
            config = parse_config_file(config_path)
            return self.add_from_config(config)
        except Exception as e:
            logger.error(f"Failed to parse config file {config_path}: {e}")
            return False
    
    def add_from_config_data(self, config_data: Dict[str, Any]) -> bool:
        """
        Add/update topics from YAML config data (already parsed).
        
        Args:
            config_data: Parsed YAML dictionary
            
        Returns:
            True if successful
        """
        try:
            config = ConfigParser(config_data=config_data)
            return self.add_from_config(config)
        except Exception as e:
            logger.error(f"Failed to process config data: {e}")
            return False
    
    def remove_asset(self, asset_id: str) -> bool:
        """
        Remove an asset from topics configuration.
        
        Args:
            asset_id: Asset ID to remove
            
        Returns:
            True if removed, False if not found
        """
        if asset_id in self.topics:
            del self.topics[asset_id]
            logger.info(f"Removed {asset_id} from topics")
            return True
        return False
    
    def save(self) -> bool:
        """
        Save topics.json to disk.
        
        Returns:
            True if successful
        """
        try:
            # Ensure directory exists
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.output_path, 'w') as f:
                json.dump(self.topics, f, indent=4)
            
            logger.info(f"Saved topics.json with {len(self.topics)} assets to {self.output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save topics.json: {e}")
            return False
    
    def get_topics(self) -> Dict[str, Any]:
        """Get current topics configuration"""
        return self.topics.copy()
    
    def get_asset_skills(self, asset_id: str) -> Dict[str, Any]:
        """Get skills for a specific asset"""
        if asset_id in self.topics:
            return self.topics[asset_id].get('skills', {})
        return {}


def generate_topics_from_configs(config_paths: List[str], output_path: str = None) -> bool:
    """
    Generate topics.json from multiple YAML config files.
    
    Args:
        config_paths: List of paths to YAML config files
        output_path: Output path for topics.json
        
    Returns:
        True if successful
    """
    generator = TopicsGenerator(output_path)
    
    success_count = 0
    for config_path in config_paths:
        if generator.add_from_config_file(config_path):
            success_count += 1
    
    if success_count > 0:
        generator.save()
        logger.info(f"Generated topics.json from {success_count}/{len(config_paths)} configs")
        return True
    
    return False


def generate_topics_from_directory(config_dir: str, output_path: str = None) -> bool:
    """
    Generate topics.json from all YAML files in a directory.
    
    Args:
        config_dir: Directory containing YAML config files
        output_path: Output path for topics.json
        
    Returns:
        True if successful
    """
    config_dir = Path(config_dir)
    if not config_dir.exists():
        logger.error(f"Config directory not found: {config_dir}")
        return False
    
    config_paths = list(config_dir.glob('*.yaml')) + list(config_dir.glob('*.yml'))
    
    if not config_paths:
        logger.warning(f"No YAML files found in {config_dir}")
        return False
    
    return generate_topics_from_configs([str(p) for p in config_paths], output_path)

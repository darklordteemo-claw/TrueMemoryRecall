#!/usr/bin/env python3
"""
TMR v2 Configuration Loader

Centralized configuration management for all TMR v2 components.
Loads from config/tmr_config.yaml with environment variable substitution.
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


class TMRConfig:
    """
    Centralized configuration manager for TMR v2.
    Loads config from YAML with environment variable support.
    """
    
    _instance = None
    _config = None
    
    def __new__(cls, config_path: Optional[str] = None):
        """Singleton pattern - only one config instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(config_path)
        return cls._instance
    
    def _load_config(self, config_path: Optional[str] = None):
        """Load configuration from YAML file"""
        if config_path is None:
            # Default path relative to this file
            base_dir = Path(__file__).parent.parent
            config_path = base_dir / "config" / "tmr_config.yaml"
        else:
            config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            raw_content = f.read()
        
        # Substitute environment variables
        content = self._substitute_env_vars(raw_content)
        
        # Parse YAML
        self._config = yaml.safe_load(content)
        
        # Store config path for reload
        self._config_path = config_path
    
    def _substitute_env_vars(self, content: str) -> str:
        """Substitute ${VAR} and ${VAR:-default} patterns"""
        pattern = r'\$\{(\w+)(?::-([^}]*))?\}'
        
        def replacer(match):
            var_name = match.group(1)
            default_val = match.group(2)
            value = os.environ.get(var_name, default_val)
            return value if value is not None else match.group(0)
        
        return re.sub(pattern, replacer, content)
    
    def reload(self):
        """Reload configuration from file"""
        self._load_config(self._config_path)
    
    def get(self, *keys, default=None):
        """
        Get nested config value by key path.
        
        Example:
            config.get('intent_classification', 'intents', 'greeting', 'patterns')
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    @property
    def storage(self) -> Dict[str, Any]:
        """Storage configuration"""
        return self._config.get('storage', {})
    
    @property
    def qdrant(self) -> Dict[str, Any]:
        """Qdrant configuration"""
        return self._config.get('qdrant', {})
    
    @property
    def intent_classification(self) -> Dict[str, Any]:
        """Intent classification configuration"""
        return self._config.get('intent_classification', {})
    
    @property
    def query_planning(self) -> Dict[str, Any]:
        """Query planning configuration"""
        return self._config.get('query_planning', {})
    
    @property
    def graph_traversal(self) -> Dict[str, Any]:
        """Graph traversal configuration"""
        return self._config.get('graph_traversal', {})
    
    @property
    def feedback_loop(self) -> Dict[str, Any]:
        """Feedback loop configuration"""
        return self._config.get('feedback_loop', {})
    
    @property
    def hybrid_search(self) -> Dict[str, Any]:
        """Hybrid search configuration"""
        return self._config.get('hybrid_search', {})
    
    @property
    def entity_extraction(self) -> Dict[str, Any]:
        """Entity extraction configuration"""
        return self._config.get('entity_extraction', {})
    
    @property
    def embeddings(self) -> Dict[str, Any]:
        """Embedding configuration"""
        return self._config.get('embeddings', {})
    
    # Convenience methods for commonly accessed values
    
    def get_intent_weights(self, intent: str) -> Dict[str, float]:
        """Get graph/semantic weights for an intent"""
        weights_config = self.get('feedback_loop', 'default_weights', default={})
        if intent in weights_config:
            return weights_config[intent]
        return weights_config.get('default', {'graph': 0.4, 'semantic': 0.6})
    
    def get_intent_max_hops(self, intent: str) -> int:
        """Get max hops for an intent type"""
        hop_limits = self.get('graph_traversal', 'intent_hop_limits', default={})
        return hop_limits.get(intent, hop_limits.get('default', 2))
    
    def get_strategy_config(self, strategy: str) -> Dict[str, Any]:
        """Get configuration for a retrieval strategy"""
        strategies = self.get('query_planning', 'strategies', default={})
        return strategies.get(strategy, strategies.get('hybrid', {}))
    
    def is_intent_enabled(self, intent: str) -> bool:
        """Check if an intent type is enabled"""
        intents = self.get('intent_classification', 'intents', default={})
        return intent in intents
    
    def get_all_intents(self) -> Dict[str, Dict[str, Any]]:
        """Get all configured intent types"""
        return self.get('intent_classification', 'intents', default={})


# Global config instance (lazy-loaded)
_config_instance: Optional[TMRConfig] = None


def get_config(config_path: Optional[str] = None) -> TMRConfig:
    """Get the global config instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = TMRConfig(config_path)
    return _config_instance


def reload_config():
    """Reload the global config from file"""
    global _config_instance
    if _config_instance is not None:
        _config_instance.reload()


# For testing
if __name__ == "__main__":
    config = get_config()
    
    print("TMR v2 Configuration Loaded")
    print("=" * 60)
    
    print(f"\nStorage:")
    print(f"  Raw dir: {config.storage.get('raw_dir')}")
    print(f"  Graph dir: {config.storage.get('graph_dir')}")
    
    print(f"\nIntent Weights (greeting):")
    weights = config.get_intent_weights('greeting')
    print(f"  Graph: {weights['graph']}, Semantic: {weights['semantic']}")
    
    print(f"\nMax Hops (technical_howto):")
    hops = config.get_intent_max_hops('technical_howto')
    print(f"  {hops} hops")
    
    print(f"\nAll Intents:")
    for intent_name in config.get_all_intents():
        print(f"  - {intent_name}")
    
    print("\n✅ Config loader test passed!")

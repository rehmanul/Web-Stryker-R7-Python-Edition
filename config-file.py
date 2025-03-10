"""
Configuration System for Web Stryker R7 Python Edition
Manages all configuration settings and API keys
"""
import os
import json
from typing import Dict, Any, Optional
from pathlib import Path


class Config:
    """Configuration manager for the extraction system"""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration with default values"""
        # Default configuration
        self.config = {
            "MAX_RETRIES": 3,
            "TIMEOUT_SECONDS": 30,
            "USER_AGENT": "Mozilla/5.0 (compatible; WebStrykerPython/1.0)",
            "ENABLE_ADVANCED_FEATURES": True,
            "FALLBACK_TO_BASIC": True,
            "MAX_PRODUCT_PAGES": 10,
            "MAX_CRAWL_DEPTH": 3,
            
            # API configuration
            "API": {
                "AZURE": {
                    "OPENAI": {
                        "ENDPOINT": "https://fetcher.openai.azure.com/",
                        "KEY": "",
                        "DEPLOYMENT": "gpt-4",
                        "MAX_TOKENS": 1000,
                        "TEMPERATURE": 0.3
                    }
                },
                "GOOGLE_CLOUD": {
                    "VERTEX_AI": {
                        "KEY": "",
                        "ENDPOINT": "https://us-central1-aiplatform.googleapis.com/v1",
                        "PROJECT_ID": "",
                        "LOCATION": "us-central1"
                    },
                    "VISION": {
                        "KEY": "",
                        "ENDPOINT": "https://vision.googleapis.com/v1"
                    },
                    "COMMERCE_SEARCH": {
                        "ENGINE": ""
                    }
                },
                "KNOWLEDGE_GRAPH": {
                    "KEY": ""
                }
            },
            
            # Extraction settings
            "EXTRACTION": {
                "FOLLOW_LINKS": True,
                "MAX_PRODUCTS": 20,
                "EXTRACT_IMAGES": True,
                "DETAILED_LOGGING": True
            },
            
            # Database settings
            "DATABASE": {
                "TYPE": "sqlite",  # sqlite, postgresql, mysql
                "CONNECTION_STRING": "web_stryker.db",
                "ENABLE_MIGRATIONS": True
            },
            
            # Web UI settings
            "WEB_UI": {
                "PORT": 8080,
                "HOST": "127.0.0.1",
                "DEBUG": True,
                "SECRET_KEY": "change-this-in-production"
            }
        }
        
        # Load configuration from file if provided
        self.config_path = config_path or self._get_default_config_path()
        self.load_config()
    
    def _get_default_config_path(self) -> str:
        """Get default configuration path"""
        # Check for config in user's home directory
        home_config = Path.home() / ".web_stryker" / "config.json"
        if home_config.exists():
            return str(home_config)
        
        # Check for config in current directory
        current_dir_config = Path("config.json")
        if current_dir_config.exists():
            return str(current_dir_config)
        
        # Return path for creating new config
        os.makedirs(Path.home() / ".web_stryker", exist_ok=True)
        return str(Path.home() / ".web_stryker" / "config.json")
    
    def load_config(self) -> None:
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    # Update config with loaded values (keep defaults for missing keys)
                    self._deep_update(self.config, loaded_config)
                print(f"Configuration loaded from {self.config_path}")
        except Exception as e:
            print(f"Error loading configuration: {e}")
            # If loading fails, continue with default config
            pass
    
    def save_config(self) -> bool:
        """Save current configuration to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            print(f"Configuration saved to {self.config_path}")
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
    
    def _deep_update(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Recursively update nested dictionaries"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'API.AZURE.OPENAI.KEY')"""
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key_path: str, value: Any) -> None:
        """Set configuration value using dot notation"""
        keys = key_path.split('.')
        target = self.config
        
        # Navigate to the innermost dictionary
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        
        # Set the value
        target[keys[-1]] = value
    
    def update_api_keys(self, api_keys: Dict[str, str]) -> None:
        """Update API keys in configuration"""
        if "azure_openai_key" in api_keys:
            self.set("API.AZURE.OPENAI.KEY", api_keys["azure_openai_key"])
        
        if "azure_openai_endpoint" in api_keys:
            self.set("API.AZURE.OPENAI.ENDPOINT", api_keys["azure_openai_endpoint"])
        
        if "azure_openai_deployment" in api_keys:
            self.set("API.AZURE.OPENAI.DEPLOYMENT", api_keys["azure_openai_deployment"])
        
        if "knowledge_graph_api_key" in api_keys:
            self.set("API.KNOWLEDGE_GRAPH.KEY", api_keys["knowledge_graph_api_key"])
            
        if "google_vision_api_key" in api_keys:
            self.set("API.GOOGLE_CLOUD.VISION.KEY", api_keys["google_vision_api_key"])
            
        if "google_vertex_api_key" in api_keys:
            self.set("API.GOOGLE_CLOUD.VERTEX_AI.KEY", api_keys["google_vertex_api_key"])
            
        # Save updated configuration
        self.save_config()
    
    def get_api_keys(self) -> Dict[str, str]:
        """Get all API keys"""
        return {
            "azure_openai_key": self.get("API.AZURE.OPENAI.KEY", ""),
            "azure_openai_endpoint": self.get("API.AZURE.OPENAI.ENDPOINT", ""),
            "azure_openai_deployment": self.get("API.AZURE.OPENAI.DEPLOYMENT", ""),
            "knowledge_graph_api_key": self.get("API.KNOWLEDGE_GRAPH.KEY", ""),
            "google_vision_api_key": self.get("API.GOOGLE_CLOUD.VISION.KEY", ""),
            "google_vertex_api_key": self.get("API.GOOGLE_CLOUD.VERTEX_AI.KEY", "")
        }


# Singleton instance to be used throughout the application
config = Config()

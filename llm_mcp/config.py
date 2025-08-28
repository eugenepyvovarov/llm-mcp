"""Configuration management for LLM MCP plugin."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import llm
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Configuration for a single MCP server."""
    
    command: str
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    description: str = ""
    enabled: bool = True
    transport: str = "stdio"


class Settings(BaseModel):
    """Global plugin settings."""
    
    cache_duration_seconds: int = 300
    max_reconnection_attempts: int = 3
    reconnection_base_delay: float = 1.0
    log_level: str = "INFO"


class Config(BaseModel):
    """Root configuration model."""
    
    servers: Dict[str, ServerConfig] = Field(default_factory=dict)
    settings: Settings = Field(default_factory=Settings)


class ConfigManager:
    """Manages plugin configuration and storage."""
    
    def __init__(self):
        self.mcp_dir = Path(llm.user_dir()) / "mcp"
        self.servers_file = self.mcp_dir / "servers.json"
        self.connections_file = self.mcp_dir / "connections.json"
        self.tools_cache_file = self.mcp_dir / "tools_cache.json"
        self.logs_dir = self.mcp_dir / "logs"
        
        # Ensure directories exist
        self.mcp_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
    
    def load_config(self) -> Config:
        """Load configuration from disk."""
        if not self.servers_file.exists():
            return Config()
        
        try:
            with open(self.servers_file, 'r') as f:
                data = json.load(f)
            return Config.model_validate(data)
        except Exception as e:
            raise ValueError(f"Failed to load configuration: {e}")
    
    def save_config(self, config: Config) -> None:
        """Save configuration to disk."""
        try:
            with open(self.servers_file, 'w') as f:
                json.dump(config.model_dump(), f, indent=2)
        except Exception as e:
            raise ValueError(f"Failed to save configuration: {e}")
    
    def add_server(
        self,
        name: str,
        command: str,
        args: List[str],
        env_vars: Optional[Dict[str, str]] = None,
        description: str = ""
    ) -> None:
        """Add a new server configuration."""
        config = self.load_config()
        
        if name in config.servers:
            raise ValueError(f"Server '{name}' already exists")
        
        # Store sensitive environment variables using LLM's key system
        stored_env = {}
        if env_vars:
            for key, value in env_vars.items():
                key_name = f"mcp_{name}_{key.lower()}"
                llm.set_key(key_name, value)
                stored_env[key] = key_name
        
        config.servers[name] = ServerConfig(
            command=command,
            args=args,
            env=stored_env,
            description=description
        )
        
        self.save_config(config)
    
    def remove_server(self, name: str) -> None:
        """Remove a server configuration."""
        config = self.load_config()
        
        if name not in config.servers:
            raise ValueError(f"Server '{name}' not found")
        
        # Clean up stored keys
        server_config = config.servers[name]
        for env_key, stored_key in server_config.env.items():
            try:
                llm.remove_key(stored_key)
            except Exception:
                pass  # Key might not exist
        
        del config.servers[name]
        self.save_config(config)
    
    def get_server(self, name: str) -> ServerConfig:
        """Get server configuration by name."""
        config = self.load_config()
        if name not in config.servers:
            raise ValueError(f"Server '{name}' not found")
        return config.servers[name]
    
    def list_servers(self, enabled_only: bool = False) -> Dict[str, ServerConfig]:
        """List all server configurations."""
        config = self.load_config()
        if enabled_only:
            return {
                name: server for name, server in config.servers.items()
                if server.enabled
            }
        return config.servers
    
    def enable_server(self, name: str) -> None:
        """Enable a server."""
        config = self.load_config()
        if name not in config.servers:
            raise ValueError(f"Server '{name}' not found")
        config.servers[name].enabled = True
        self.save_config(config)
    
    def disable_server(self, name: str) -> None:
        """Disable a server."""
        config = self.load_config()
        if name not in config.servers:
            raise ValueError(f"Server '{name}' not found")
        config.servers[name].enabled = False
        self.save_config(config)
    
    def get_server_env(self, name: str) -> Dict[str, str]:
        """Get resolved environment variables for a server."""
        server_config = self.get_server(name)
        resolved_env = {}
        
        for env_key, stored_key in server_config.env.items():
            try:
                value = llm.get_key(stored_key)
                if value:
                    resolved_env[env_key] = value
            except Exception:
                pass  # Key might not exist
        
        return resolved_env
    
    def load_tools_cache(self) -> Dict[str, Any]:
        """Load cached tool schemas."""
        if not self.tools_cache_file.exists():
            return {}
        
        try:
            with open(self.tools_cache_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def save_tools_cache(self, cache: Dict[str, Any]) -> None:
        """Save tool schemas to cache."""
        try:
            with open(self.tools_cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
        except Exception:
            pass  # Non-critical failure
    
    def get_log_file(self, server_name: str) -> Path:
        """Get log file path for a server."""
        return self.logs_dir / f"{server_name}.log"
    
    def get_settings(self) -> Settings:
        """Get global settings."""
        return self.load_config().settings
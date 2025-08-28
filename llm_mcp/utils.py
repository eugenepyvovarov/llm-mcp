"""Shared utilities for the LLM MCP plugin."""

import asyncio
import logging
import os
import sys
from typing import Any, Callable, Coroutine, Optional, Tuple


class McpError(Exception):
    """Base exception for MCP-related errors."""
    pass


class ServerConnectionError(McpError):
    """Error connecting to MCP server."""
    pass


class ServerProtocolError(McpError):
    """MCP protocol violation error."""
    pass


class ToolExecutionError(McpError):
    """Error executing MCP tool."""
    pass


class ConfigurationError(McpError):
    """Configuration-related error."""
    pass


def setup_logging(name: str, log_file: Optional[str] = None, level: str = "INFO") -> logging.Logger:
    """Set up logging for a component."""
    logger = logging.getLogger(name)
    
    # Don't add handlers if already configured
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, level.upper()))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)  # Only show warnings/errors on console
    console_formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(getattr(logging, level.upper()))
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Failed to set up file logging: {e}")
    
    return logger


def run_async_with_factory(coro_factory: Callable[[], Coroutine]) -> Any:
    """Run an async coroutine factory in a simple, reliable manner."""
    # Simple approach - just use asyncio.run
    try:
        return asyncio.run(coro_factory())
    except RuntimeError as e:
        # If asyncio.run fails, try alternative approaches
        error_str = str(e).lower()
        
        # Case 1: Event loop is already running
        if "already running" in error_str:
            try:
                # Get the running loop and try to run there
                loop = asyncio.get_running_loop()
                # This will fail if we're actually in the loop, but worth trying
                return loop.run_until_complete(coro_factory())
            except RuntimeError:
                # We're in a running loop, need to use thread
                import concurrent.futures
                import threading
                
                def run_in_thread():
                    # Create completely isolated event loop in new thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(coro_factory())
                    finally:
                        new_loop.close()
                        asyncio.set_event_loop(None)
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result()
        
        # Case 2: No event loop exists  
        else:
            try:
                # Try to get existing loop
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(coro_factory())
            except RuntimeError:
                # Create a new loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(coro_factory())
                finally:
                    # Clean up but don't interfere with other code
                    pass


def run_async(coro: Coroutine) -> Any:
    """Run an async coroutine in a simple, reliable manner.
    
    Note: This function only tries one execution method to avoid 
    coroutine reuse issues. Use run_async_with_factory for retry logic.
    """
    # Try the most appropriate method based on current context
    try:
        # Check if we're in an event loop
        loop = asyncio.get_running_loop()
        # We're in a running loop, need to use thread
        import concurrent.futures
        import threading
        
        def run_in_thread():
            # Create completely isolated event loop in new thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result()
            
    except RuntimeError:
        # No running loop, use asyncio.run
        return asyncio.run(coro)




def safe_json_loads(data: str, default: Any = None) -> Any:
    """Safely load JSON data with error handling."""
    try:
        import json
        return json.loads(data)
    except (json.JSONDecodeError, TypeError) as e:
        if default is not None:
            return default
        raise ConfigurationError(f"Invalid JSON data: {e}")


def safe_json_dumps(obj: Any, default: Any = None) -> str:
    """Safely dump object to JSON string."""
    try:
        import json
        return json.dumps(obj, indent=2, default=str)
    except (TypeError, ValueError) as e:
        if default is not None:
            return default
        raise ConfigurationError(f"Failed to serialize to JSON: {e}")


def validate_server_name(name: str) -> str:
    """Validate and normalize server name."""
    if not name:
        raise ConfigurationError("Server name cannot be empty")
    
    if not name.replace("-", "").replace("_", "").isalnum():
        raise ConfigurationError("Server name must contain only letters, numbers, hyphens, and underscores")
    
    if len(name) > 64:
        raise ConfigurationError("Server name must be 64 characters or less")
    
    return name.lower().strip()


def validate_tool_name(name: str) -> str:
    """Validate tool name format."""
    if not name:
        raise ConfigurationError("Tool name cannot be empty")
    
    if "__" not in name:
        raise ConfigurationError("Tool name must contain server namespace (format: server__tool)")
    
    parts = name.split("__", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ConfigurationError("Invalid tool name format (expected: server__tool)")
    
    return name


def sanitize_env_var(key: str, value: str) -> Tuple[str, str]:
    """Sanitize environment variable key and value."""
    # Validate key
    if not key:
        raise ConfigurationError("Environment variable key cannot be empty")
    
    if not key.replace("_", "").isalnum():
        raise ConfigurationError("Environment variable key must contain only letters, numbers, and underscores")
    
    # Sanitize value (remove dangerous characters)
    sanitized_value = value.replace('\n', '').replace('\r', '').replace('\0', '')
    
    return key.upper(), sanitized_value

def get_user_data_dir() -> str:
    """Get platform-specific user data directory."""
    if sys.platform == "win32":
        return os.path.expandvars(r"%APPDATA%\llm-mcp")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/llm-mcp")
    else:
        return os.path.expanduser("~/.local/share/llm-mcp")


def ensure_directory(path: str) -> str:
    """Ensure directory exists, creating it if necessary."""
    os.makedirs(path, exist_ok=True)
    return path
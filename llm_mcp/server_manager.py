"""MCP server lifecycle management."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .client import McpClient
from .config import ConfigManager, ServerConfig


class ServerConnection:
    """Manages connection to a single MCP server."""
    
    def __init__(self, name: str, config: ServerConfig, config_manager: ConfigManager):
        self.name = name
        self.config = config
        self.config_manager = config_manager
        self.client: Optional[McpClient] = None
        self.tools: List[Dict[str, Any]] = []
        self.tools_cached_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.connection_attempts = 0
        self.max_attempts = 3
        self.base_delay = 1.0
        self.connected = False
        
        # Set up logging
        log_file = config_manager.get_log_file(name)
        self.logger = logging.getLogger(f"mcp.{name}")
        self.logger.setLevel(getattr(logging, config_manager.get_settings().log_level))
        
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(file_handler)
        
        # Prevent duplicate console logs
        self.logger.propagate = False
    
    async def connect(self) -> bool:
        """Connect to the MCP server with retry logic."""
        if self.connected and self.client:
            return True
        
        for attempt in range(self.max_attempts):
            try:
                self.connection_attempts = attempt + 1
                self.logger.info(f"Connection attempt {self.connection_attempts}/{self.max_attempts}")
                
                # Create new client
                self.client = McpClient(self.name, self.logger)
                
                # Get environment variables
                env_vars = self.config_manager.get_server_env(self.name)
                
                # Start process
                await self.client.start_process(
                    command=self.config.command,
                    args=self.config.args,
                    env=env_vars
                )
                
                # Initialize connection
                await self.client.initialize()
                
                self.connected = True
                self.last_error = None
                self.logger.info("Successfully connected to MCP server")
                return True
                
            except Exception as e:
                error_msg = str(e)
                self.last_error = error_msg
                self.logger.error(f"Connection attempt {attempt + 1} failed: {error_msg}")
                
                # Clean up failed client
                if self.client:
                    try:
                        await self.client.close()
                    except Exception:
                        pass
                    self.client = None
                
                # Wait before retry (exponential backoff)
                if attempt < self.max_attempts - 1:
                    delay = self.base_delay * (2 ** attempt)
                    self.logger.info(f"Waiting {delay}s before retry")
                    await asyncio.sleep(delay)
        
        self.connected = False
        return False
    
    async def disconnect(self, fast_shutdown: bool = False) -> None:
        """Disconnect from the MCP server."""
        if self.client:
            try:
                await self.client.close(fast_shutdown=fast_shutdown)
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
            finally:
                self.client = None
                self.connected = False
                self.logger.debug("Disconnected from MCP server")
    
    async def get_tools(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get tools from server, with caching."""
        settings = self.config_manager.get_settings()
        cache_duration = settings.cache_duration_seconds
        
        # Check cache validity
        if not force_refresh and self.tools_cached_at:
            if time.time() - self.tools_cached_at < cache_duration:
                return self.tools
        
        # Ensure connection
        if not await self.connect():
            raise RuntimeError(f"Failed to connect to server {self.name}: {self.last_error}")
        
        try:
            # Fetch tools from server
            self.tools = await self.client.list_tools()
            self.tools_cached_at = time.time()
            
            self.logger.info(f"Retrieved {len(self.tools)} tools from server")
            return self.tools
            
        except Exception as e:
            self.logger.error(f"Failed to get tools: {e}")
            raise
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on this server."""
        # Ensure connection but don't create multiple connections
        if not self.connected or not self.client:
            if not await self.connect():
                raise RuntimeError(f"Failed to connect to server {self.name}: {self.last_error}")
        
        try:
            self.logger.info(f"Calling tool {tool_name} with args: {arguments}")
            result = await self.client.call_tool(tool_name, arguments)
            self.logger.info(f"Tool {tool_name} completed successfully")
            return result
            
        except Exception as e:
            self.logger.error(f"Tool call {tool_name} failed: {e}")
            # If we get a connection error, mark as disconnected and retry once
            error_str = str(e).lower()
            if ("closedresourceerror" in error_str or 
                "not initialized" in error_str or 
                "connection" in error_str or
                "tool call failed:" in error_str):
                self.logger.info(f"Connection lost, attempting to reconnect for {tool_name}")
                self.connected = False
                if self.client:
                    await self.client.close(fast_shutdown=True)
                    self.client = None
                
                # Retry once
                if await self.connect():
                    self.logger.info(f"Reconnection successful, retrying {tool_name}")
                    return await self.client.call_tool(tool_name, arguments)
                else:
                    self.logger.error(f"Reconnection failed for {tool_name}")
            raise
    
    async def test_connection(self) -> Tuple[bool, Optional[str]]:
        """Test server connectivity."""
        try:
            if await self.connect():
                # Try to list tools as a connectivity test
                await self.get_tools(force_refresh=True)
                return True, None
            else:
                return False, self.last_error
        except Exception as e:
            return False, str(e)


class ServerManager:
    """Manages all MCP server connections."""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.connections: Dict[str, ServerConnection] = {}
        self.logger = logging.getLogger(__name__)
    
    def _get_connection(self, server_name: str) -> ServerConnection:
        """Get or create a server connection."""
        if server_name not in self.connections:
            try:
                server_config = self.config_manager.get_server(server_name)
                self.connections[server_name] = ServerConnection(
                    server_name, server_config, self.config_manager
                )
            except ValueError:
                raise ValueError(f"Server '{server_name}' not found in configuration")
        
        return self.connections[server_name]
    
    async def get_tools(self, server_name: Optional[str] = None, force_refresh: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """Get tools from one or all enabled servers."""
        tools_by_server = {}
        
        if server_name:
            # Get tools from specific server
            if not self.config_manager.get_server(server_name).enabled:
                return {}
            
            connection = self._get_connection(server_name)
            try:
                tools = await connection.get_tools(force_refresh=force_refresh)
                tools_by_server[server_name] = tools
            except Exception as e:
                self.logger.error(f"Failed to get tools from {server_name}: {e}")
                tools_by_server[server_name] = []
        else:
            # Get tools from all enabled servers
            servers = self.config_manager.list_servers(enabled_only=True)
            
            # Run all tool fetches concurrently
            tasks = []
            server_names = []
            
            for name, server_config in servers.items():
                connection = self._get_connection(name)
                task = asyncio.create_task(connection.get_tools(force_refresh=force_refresh))
                tasks.append(task)
                server_names.append(name)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for server_name, result in zip(server_names, results):
                if isinstance(result, Exception):
                    self.logger.error(f"Failed to get tools from {server_name}: {result}")
                    tools_by_server[server_name] = []
                else:
                    tools_by_server[server_name] = result
        
        return tools_by_server
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the specified server."""
        connection = self._get_connection(server_name)
        return await connection.call_tool(tool_name, arguments)
    
    async def test_server(self, server_name: str) -> Tuple[bool, Optional[str]]:
        """Test connectivity to a specific server."""
        connection = self._get_connection(server_name)
        return await connection.test_connection()
    
    async def start_server(self, server_name: str) -> bool:
        """Manually start a server connection."""
        connection = self._get_connection(server_name)
        return await connection.connect()
    
    async def stop_server(self, server_name: str, fast_shutdown: bool = False) -> None:
        """Stop a server connection."""
        if server_name in self.connections:
            connection = self.connections[server_name]
            await connection.disconnect(fast_shutdown=fast_shutdown)
            del self.connections[server_name]
    
    async def shutdown_all(self, fast_shutdown: bool = True) -> None:
        """Shutdown all server connections."""
        if not self.connections:
            return
        
        # Disconnect all connections concurrently with timeout
        # Use fast shutdown by default to avoid hanging
        tasks = []
        for connection in self.connections.values():
            task = asyncio.create_task(connection.disconnect(fast_shutdown=True))
            tasks.append(task)
        
        # Use aggressive timeout for bulk shutdown
        timeout = 1.0
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            self.logger.warning("Shutdown timeout exceeded, forcibly clearing connections")
        
        self.connections.clear()
        self.logger.debug("All MCP server connections shutdown")
    
    def get_server_status(self, server_name: str) -> Dict[str, Any]:
        """Get status information for a server."""
        try:
            server_config = self.config_manager.get_server(server_name)
            connection = self.connections.get(server_name)
            
            status = {
                "name": server_name,
                "enabled": server_config.enabled,
                "description": server_config.description,
                "command": server_config.command,
                "args": server_config.args,
                "connected": False,
                "last_error": None,
                "tools_count": 0,
                "connection_attempts": 0
            }
            
            if connection:
                status.update({
                    "connected": connection.connected,
                    "last_error": connection.last_error,
                    "tools_count": len(connection.tools),
                    "connection_attempts": connection.connection_attempts
                })
            
            return status
            
        except ValueError:
            return {"name": server_name, "error": "Server not found"}
    
    def list_server_statuses(self) -> List[Dict[str, Any]]:
        """Get status for all configured servers."""
        servers = self.config_manager.list_servers()
        return [self.get_server_status(name) for name in servers.keys()]
"""MCP client implementation using official SDK."""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from typing import Any, Dict, List, Optional
import threading
import weakref

from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
import llm


class McpClient:
    """MCP client using official SDK."""
    
    # Class-level connection tracking to prevent multiple connections to same server
    _active_connections = weakref.WeakValueDictionary()
    _connection_lock = threading.Lock()
    
    # Common API keys that should be automatically resolved from LLM storage
    COMMON_API_KEYS = [
        'FIRECRAWL_API_KEY',
        'GITHUB_PERSONAL_ACCESS_TOKEN', 
        'GITHUB_TOKEN',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'GOOGLE_API_KEY',
        'BRAVE_SEARCH_API_KEY',
        'TAVILY_API_KEY'
    ]
    
    def __init__(self, server_name: str, logger: Optional[logging.Logger] = None):
        self.server_name = server_name
        self.logger = logger or logging.getLogger(__name__)
        self._initialized = False
        self._server_params = None
        
    def _resolve_api_keys(self, env: Dict[str, str]) -> Dict[str, str]:
        """Resolve API keys from environment or LLM storage."""
        resolved_env = env.copy()
        
        for key_name in self.COMMON_API_KEYS:
            # Skip if already set in environment or passed env
            if key_name in os.environ or key_name in env:
                continue
                
            try:
                # Try to get from LLM storage
                value = llm.get_key(key_name)
                if value:
                    resolved_env[key_name] = value
                    self.logger.debug(f"Resolved {key_name} from LLM storage")
            except Exception as e:
                self.logger.debug(f"Could not resolve {key_name} from LLM storage: {e}")
                
        return resolved_env
        
    async def start_and_initialize(self, command: str, args: List[str], env: Dict[str, str]) -> None:
        """Start the server and initialize the connection parameters."""
        if self._initialized:
            return
        
        try:
            # Set up server parameters only - don't create persistent connection
            process_env = os.environ.copy()
            
            # Resolve API keys from LLM storage if not already set
            resolved_env = self._resolve_api_keys(env)
            process_env.update(resolved_env)
            
            self._server_params = StdioServerParameters(
                command=command,
                args=args,
                env=process_env
            )
            
            self.logger.info(f"MCP server parameters configured: {' '.join([command] + args)}")
            self._initialized = True
            
        except Exception as e:
            self.logger.error(f"Failed to configure MCP server: {e}")
            raise
    
    @asynccontextmanager
    async def _scoped_connection(self):
        """Create a scoped connection that manages its full lifecycle within this context."""
        if not self._server_params:
            raise RuntimeError("Client not configured - call start_and_initialize first")
            
        # Create stdio_client context manager
        session_context = stdio_client(self._server_params)
        session = None
        
        try:
            # Enter the context manager
            read, write = await asyncio.wait_for(
                session_context.__aenter__(),
                timeout=10.0
            )
            
            # Create and initialize the session
            session = ClientSession(read, write)
            try:
                await asyncio.wait_for(
                    session.__aenter__(),
                    timeout=5.0
                )
                
                # Initialize the protocol
                init_result = await asyncio.wait_for(
                    session.initialize(),
                    timeout=10.0
                )
                self.logger.debug(f"MCP connection established: {init_result.serverInfo.name}")
                
                yield session
                
            finally:
                # Clean up session first
                if session:
                    try:
                        await asyncio.wait_for(
                            session.__aexit__(None, None, None),
                            timeout=1.0
                        )
                    except Exception as e:
                        self.logger.debug(f"Session cleanup warning: {e}")
                    
        finally:
            # Clean up stdio_client context - this happens in the same task that created it
            try:
                await asyncio.wait_for(
                    session_context.__aexit__(None, None, None),
                    timeout=1.0
                )
                self.logger.debug("Stdio client connection closed successfully")
            except Exception as e:
                self.logger.debug(f"Stdio client cleanup warning: {e}")
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server."""
        if not self._initialized:
            raise RuntimeError("Client not configured - call start_and_initialize first")
        
        try:
            async with self._scoped_connection() as session:
                tools_result = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema
                    }
                    for tool in tools_result.tools
                ]
        except Exception as e:
            self.logger.error(f"Failed to list tools: {e}")
            raise RuntimeError(f"Failed to list tools: {e}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        if not self._initialized:
            raise RuntimeError("Client not configured - call start_and_initialize first")
        
        try:
            self.logger.info(f"Calling tool {tool_name} with arguments: {arguments}")
            
            async with self._scoped_connection() as session:
                result = await session.call_tool(name=tool_name, arguments=arguments)
                self.logger.info(f"Tool call result type: {type(result)}")
                
                # Extract the content from the result
                if hasattr(result, 'content') and result.content:
                    self.logger.info(f"Result has content: {len(result.content)} items")
                    # Return the text content if available
                    content_list = []
                    for i, content_item in enumerate(result.content):
                        self.logger.info(f"Content item {i}: type={type(content_item)}")
                        if hasattr(content_item, 'text'):
                            content_list.append(content_item.text)
                            self.logger.info(f"Added text content: {content_item.text[:100]}...")
                        elif hasattr(content_item, 'type') and content_item.type == 'text':
                            content_list.append(str(content_item))
                            self.logger.info(f"Added text type content: {str(content_item)[:100]}...")
                    
                    final_result = "\n".join(content_list) if content_list else str(result)
                    self.logger.info(f"Final result length: {len(final_result)}")
                    return final_result
                
                self.logger.info(f"No content found, returning string: {str(result)[:100]}...")
                return str(result)
            
        except Exception as e:
            self.logger.error(f"Tool call failed with exception: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Tool call failed: {e}")
    
    async def _cleanup(self) -> None:
        """Clean up resources gracefully."""
        # With scoped connections, there's no persistent state to clean up
        self._initialized = False
        self._server_params = None
        self.logger.debug("Client cleanup completed")
    
    async def _force_cleanup(self) -> None:
        """Force cleanup when normal cleanup fails."""
        # With scoped connections, just reset state
        self._initialized = False
        self._server_params = None
        self.logger.debug("Force cleanup completed")
    
    async def close(self, fast_shutdown: bool = False) -> None:
        """Close the MCP client."""
        if fast_shutdown:
            await self._force_cleanup()
        else:
            await self._cleanup()
        self.logger.debug("MCP client closed")
    
    # Compatibility methods for the existing server manager
    async def start_process(self, command: str, args: List[str], env: Dict[str, str]) -> None:
        """Compatibility method - starts and initializes in one go."""
        await self.start_and_initialize(command, args, env)
    
    async def initialize(self) -> Dict[str, Any]:
        """Compatibility method - initialization is done in start_process."""
        if not self._initialized:
            raise RuntimeError("Client not configured - call start_process first")
        return {"status": "configured"}
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
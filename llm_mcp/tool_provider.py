"""Tool discovery and LLM integration for MCP servers."""

import asyncio
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

import llm

# No need to import McpTool anymore - we work with dictionaries
from .server_manager import ServerManager
from .utils import run_async, run_async_with_factory


class McpLlmTool:
    """Wrapper that converts MCP tools to LLM Tool objects."""
    
    def __init__(
        self,
        server_name: str,
        mcp_tool: Dict[str, Any],
        server_manager: ServerManager,
        logger: logging.Logger
    ):
        self.server_name = server_name
        self.mcp_tool = mcp_tool
        self.server_manager = server_manager
        self.logger = logger
        
        # Create namespaced tool name
        self.name = f"{server_name}__{mcp_tool['name']}"
        self.description = mcp_tool.get('description') or f"Tool {mcp_tool['name']} from {server_name}"
        self.schema = mcp_tool.get('inputSchema', {})
        
        # Parse schema to get parameter information
        self.parameters = self._parse_schema_parameters()
    
    def _parse_schema_parameters(self) -> Dict[str, Any]:
        """Parse the inputSchema to extract parameter information."""
        parameters = {}
        
        if not self.schema or 'properties' not in self.schema:
            return parameters
        
        properties = self.schema['properties']
        required = set(self.schema.get('required', []))
        
        for param_name, param_info in properties.items():
            param_type = param_info.get('type', 'string')
            param_default = param_info.get('default')
            param_desc = param_info.get('description', '')
            
            # Convert JSON Schema types to Python types
            if param_type == 'string':
                python_type = str
            elif param_type == 'integer':
                python_type = int
            elif param_type == 'boolean':
                python_type = bool
            elif param_type == 'number':
                python_type = float
            else:
                python_type = str
            
            parameters[param_name] = {
                'type': python_type,
                'required': param_name in required,
                'default': param_default,
                'description': param_desc
            }
        
        return parameters
    
    def create_tool_function(self) -> Callable:
        """Create a function with the proper signature based on the tool's parameters."""
        
        # Create parameter list for the function signature
        params = []
        
        for param_name, param_info in self.parameters.items():
            if param_info['required']:
                # Required parameter
                params.append(inspect.Parameter(
                    param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=param_info['type']
                ))
            else:
                # Optional parameter with default value
                default_value = param_info['default']
                if default_value is None:
                    if param_info['type'] == str:
                        default_value = ""
                    elif param_info['type'] == int:
                        default_value = 0
                    elif param_info['type'] == bool:
                        default_value = False
                    elif param_info['type'] == float:
                        default_value = 0.0
                        
                params.append(inspect.Parameter(
                    param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=default_value,
                    annotation=param_info['type']
                ))
        
        # Create the function signature
        signature = inspect.Signature(params, return_annotation=str)
        
        # Create the actual function
        def tool_func(*args, **kwargs) -> str:
            """Execute MCP tool with proper parameter handling."""
            try:
                # Bind arguments to the signature to get named parameters
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                
                # Convert to the arguments dict expected by MCP
                mcp_args = dict(bound.arguments)
                
                self.logger.info(f"Executing MCP tool {self.name} with args: {mcp_args}")
                
                # Run the async tool call with stderr suppression for shutdown errors
                import sys
                import os
                
                original_stderr = sys.stderr
                try:
                    # Redirect stderr to devnull during tool execution to suppress shutdown errors
                    sys.stderr = open(os.devnull, 'w')
                    result = self._run_async_tool_call(mcp_args)
                finally:
                    # Always restore stderr
                    if sys.stderr != original_stderr:
                        sys.stderr.close()
                    sys.stderr = original_stderr
                
                self.logger.info(f"MCP tool {self.name} completed successfully")
                
                # Convert result to string for LLM
                if isinstance(result, str):
                    return result
                else:
                    return str(result)
                    
            except Exception as e:
                error_msg = f"MCP tool {self.name} failed: {str(e)}"
                self.logger.error(error_msg)
                return f"Error: {error_msg}"
        
        # Set the function signature and metadata
        tool_func.__signature__ = signature
        tool_func.__name__ = self.name
        tool_func.__doc__ = self.description
        
        return tool_func
    
    def _run_async_tool_call(self, arguments: Dict[str, Any]) -> Any:
        """Run the async tool call in a sync context."""
        # Create a function that returns a fresh coroutine each time
        def create_coro():
            return self.server_manager.call_tool(
                self.server_name,
                self.mcp_tool['name'],
                arguments
            )
        
        return run_async_with_factory(create_coro)
    
    async def __call__(self, **kwargs) -> Any:
        """Execute the MCP tool asynchronously."""
        try:
            self.logger.info(f"Executing tool {self.name} with args: {kwargs}")
            
            # Call the tool on the server
            result = await self.server_manager.call_tool(
                self.server_name,
                self.mcp_tool['name'],
                kwargs
            )
            
            self.logger.info(f"Tool {self.name} completed successfully")
            return result
            
        except Exception as e:
            error_msg = f"Tool {self.name} failed: {str(e)}"
            self.logger.error(error_msg)
            
            # Return error information instead of crashing
            return {
                "error": error_msg,
                "tool": self.name,
                "server": self.server_name
            }


class ToolProvider:
    """Provides MCP tools to the LLM system."""
    
    def __init__(self):
        self.server_manager = ServerManager()
        self.logger = logging.getLogger(__name__)
        self.registered_tools: Dict[str, McpLlmTool] = {}
    
    
    def register_tools(self, register: Callable) -> None:
        """Register all available MCP tools with LLM."""
        try:
            # Get tools from all enabled servers
            tools_by_server = run_async_with_factory(
                lambda: self.server_manager.get_tools()
            )
            
            # Register each tool
            for server_name, tools in tools_by_server.items():
                for mcp_tool in tools:
                    try:
                        # Create LLM-compatible tool
                        llm_tool = McpLlmTool(
                            server_name,
                            mcp_tool,
                            self.server_manager,
                            self.logger
                        )
                        
                        # Create function with proper signature based on inputSchema
                        tool_function = llm_tool.create_tool_function()
                        
                        # Register function directly with LLM (just like simpleeval)
                        register(tool_function)
                        self.registered_tools[llm_tool.name] = llm_tool
                        
                        self.logger.info(f"Registered tool: {llm_tool.name}")
                        
                    except Exception as e:
                        self.logger.error(f"Failed to register tool {mcp_tool.name} from {server_name}: {e}")
            
            total_tools = sum(len(tools) for tools in tools_by_server.values())
            self.logger.info(f"Successfully registered {len(self.registered_tools)} tools from {len(tools_by_server)} servers (total available: {total_tools})")
            
        except Exception as e:
            self.logger.error(f"Failed to register MCP tools: {e}")
    
    def refresh_tools(self, register: Callable) -> None:
        """Refresh tool registration by forcing cache refresh."""
        try:
            # Clear existing registrations
            self.registered_tools.clear()
            
            # Get tools with force refresh
            tools_by_server = run_async_with_factory(
                lambda: self.server_manager.get_tools(force_refresh=True)
            )
            
            # Re-register all tools
            self.register_tools(register)
            
            self.logger.info("Tool registration refreshed")
            
        except Exception as e:
            self.logger.error(f"Failed to refresh tools: {e}")
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered tool."""
        if tool_name not in self.registered_tools:
            return None
        
        tool = self.registered_tools[tool_name]
        return {
            "name": tool.name,
            "server": tool.server_name,
            "original_name": tool.mcp_tool['name'],
            "description": tool.description,
            "schema": tool.schema
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with their information."""
        return [self.get_tool_info(name) for name in self.registered_tools.keys()]
    
    def list_tools_by_server(self) -> Dict[str, List[str]]:
        """List tools grouped by server."""
        tools_by_server: Dict[str, List[str]] = {}
        
        for tool_name, tool in self.registered_tools.items():
            server_name = tool.server_name
            if server_name not in tools_by_server:
                tools_by_server[server_name] = []
            tools_by_server[server_name].append(tool_name)
        
        return tools_by_server
    
    async def test_tool(self, tool_name: str, test_arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Test a specific tool with optional arguments."""
        if tool_name not in self.registered_tools:
            return {"error": f"Tool {tool_name} not found"}
        
        tool = self.registered_tools[tool_name]
        
        try:
            # Use provided arguments or empty dict
            args = test_arguments or {}
            
            # Test the tool
            result = await tool(**args)
            
            return {
                "success": True,
                "tool": tool_name,
                "result": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "tool": tool_name,
                "error": str(e)
            }
    
    def shutdown(self) -> None:
        """Shutdown the tool provider and all server connections."""
        try:
            # Shutdown all server connections properly
            run_async_with_factory(
                lambda: self.server_manager.shutdown_all(fast_shutdown=True)
            )
            
            self.registered_tools.clear()
            self.logger.debug("Tool provider shutdown completed")
        except Exception as e:
            # Final catch-all to prevent shutdown errors from propagating
            self.logger.debug(f"Error during tool provider shutdown: {e}")
            # Force clear connections if async shutdown fails
            if hasattr(self.server_manager, 'connections'):
                self.server_manager.connections.clear()


# Global tool provider instance
_tool_provider: Optional[ToolProvider] = None


def get_tool_provider() -> ToolProvider:
    """Get the global tool provider instance."""
    global _tool_provider
    if _tool_provider is None:
        _tool_provider = ToolProvider()
    return _tool_provider
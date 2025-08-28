"""Tool-related CLI commands for MCP servers."""

import asyncio
import json
import sys
from typing import Optional

import click

from .config import ConfigManager
from .server_manager import ServerManager
from .tool_provider import get_tool_provider
from .utils import run_async

# Import the main CLI group to add commands to it
from .commands import mcp_cli


# Additional utility commands
@mcp_cli.command()
@click.option("--server", help="Filter tools by specific server")
@click.option("--names-only", is_flag=True, help="Output just tool names, one per line")
@click.option("--format", type=click.Choice(['list', 'names', 'commands']), default='list', help="Output format")
def tools(server: Optional[str], names_only: bool, format: str):
    """List all available MCP tools."""
    # Handle backwards compatibility: --names-only sets format to names
    if names_only:
        format = 'names'
    
    async def _list_tools():
        try:
            server_manager = ServerManager()
            
            # Get tools directly from all enabled servers
            tools_by_server = await server_manager.get_tools()
            
            if not tools_by_server:
                click.echo("No MCP tools available.")
                click.echo("Make sure you have enabled MCP servers with 'llm mcp list'")
                return
            
            # Filter by server if specified
            if server:
                if server not in tools_by_server:
                    click.echo(f"Server '{server}' not found or has no tools.")
                    available_servers = list(tools_by_server.keys())
                    if available_servers:
                        click.echo(f"Available servers: {', '.join(available_servers)}")
                    sys.exit(1)
                tools_by_server = {server: tools_by_server[server]}
            
            # Generate output based on format
            if format == 'names':
                # Just tool names, one per line
                for server_name, tools in tools_by_server.items():
                    for tool in sorted(tools, key=lambda t: t['name']):
                        click.echo(f"{server_name}__{tool['name']}")
                        
            elif format == 'commands':
                # As -T flags ready for copy/paste
                tool_flags = []
                for server_name, tools in tools_by_server.items():
                    for tool in sorted(tools, key=lambda t: t['name']):
                        tool_flags.append(f"-T {server_name}__{tool['name']}")
                click.echo(" ".join(tool_flags))
                
            else:  # format == 'list' (default)
                # Detailed format (original)
                total_tools = sum(len(tools) for tools in tools_by_server.values())
                if server:
                    click.echo(f"Tools from server '{server}' ({total_tools} tools):")
                else:
                    click.echo(f"Available MCP tools ({total_tools} total):")
                
                for server_name, tools in tools_by_server.items():
                    if tools:  # Only show servers with tools
                        if not server:  # Only show server header if not filtering
                            click.echo(f"\n  From server '{server_name}' ({len(tools)} tools):")
                        for tool in sorted(tools, key=lambda t: t['name']):
                            tool_name = f"{server_name}__{tool['name']}"
                            if server:
                                click.echo(f"  - {tool_name}")
                            else:
                                click.echo(f"    - {tool_name}")
                            if tool.get('description'):
                                # Truncate long descriptions
                                desc = tool['description'][:100] + "..." if len(tool['description']) > 100 else tool['description']
                                indent = "    " if server else "      "
                                click.echo(f"{indent}{desc}")
            
            # Shutdown servers after listing
            await server_manager.shutdown_all(fast_shutdown=True)
                    
        except Exception as e:
            click.echo(f"Error listing tools: {e}", err=True)
            sys.exit(1)
    
    # Run async tool listing
    run_async(_list_tools())


@mcp_cli.command()
@click.argument("tool_name")
@click.option("--args", default="{}", help="JSON arguments for the tool")
def call_tool(tool_name: str, args: str):
    """Call a specific MCP tool directly."""
    async def _call_tool():
        try:
            import json
            
            # Parse tool name
            if "__" not in tool_name:
                click.echo("Error: Tool name must be in format 'server__tool'", err=True)
                sys.exit(1)
            
            server_name, raw_tool_name = tool_name.split("__", 1)
            
            # Parse arguments
            try:
                tool_args = json.loads(args)
                if not isinstance(tool_args, dict):
                    click.echo("Error: Arguments must be a JSON object", err=True)
                    sys.exit(1)
            except json.JSONDecodeError as e:
                click.echo(f"Error parsing arguments JSON: {e}", err=True)
                sys.exit(1)
            
            server_manager = ServerManager()
            
            click.echo(f"Calling tool {tool_name} with args: {tool_args}")
            
            # Call the tool
            result = await server_manager.call_tool(server_name, raw_tool_name, tool_args)
            
            click.echo("Result:")
            click.echo(json.dumps(result, indent=2, default=str))
            
            # Shutdown after calling
            await server_manager.shutdown_all(fast_shutdown=True)
                    
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error calling tool: {e}", err=True)
            sys.exit(1)
    
    # Run async tool call
    run_async(_call_tool())


@mcp_cli.command()
def status():
    """Show overall MCP plugin status."""
    try:
        config_manager = ConfigManager()
        server_manager = ServerManager()
        
        servers = config_manager.list_servers()
        enabled_servers = config_manager.list_servers(enabled_only=True)
        
        click.echo("MCP Plugin Status")
        click.echo("================")
        click.echo(f"Total servers: {len(servers)}")
        click.echo(f"Enabled servers: {len(enabled_servers)}")
        
        if enabled_servers:
            statuses = server_manager.list_server_statuses()
            connected_count = sum(1 for s in statuses if s.get('connected'))
            click.echo(f"Connected servers: {connected_count}")
            
            # Show tool provider info
            tool_provider = get_tool_provider()
            tools_by_server = tool_provider.list_tools_by_server()
            total_tools = sum(len(tools) for tools in tools_by_server.values())
            click.echo(f"Available tools: {total_tools}")
        
        # Show configuration location
        click.echo(f"\nConfiguration directory: {config_manager.mcp_dir}")
        click.echo(f"Log directory: {config_manager.logs_dir}")
            
    except Exception as e:
        click.echo(f"Error getting status: {e}", err=True)
        sys.exit(1)
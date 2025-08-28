"""CLI commands for MCP server management."""

import asyncio
import json
import os
import sys
from typing import Dict, List, Optional

import click
import llm

from .config import ConfigManager
from .server_manager import ServerManager
from .tool_provider import get_tool_provider
from .utils import run_async


@click.group(name="mcp")
def mcp_cli():
    """Manage MCP (Model Context Protocol) servers.
    
    MCP servers provide tools and resources that can be used with LLM models.
    Common workflow:
    
    \b
    1. Add a server:    llm mcp add <name> <command> [args...]
    2. List tools:      llm mcp tools --server <name> --format commands  
    3. Use tools:       llm $(llm mcp tools --server <name> --format commands) -m <model> "<prompt>"
    
    Examples:
    
    \b
    # Add filesystem server
    llm mcp add filesystem npx @modelcontextprotocol/server-filesystem /path/to/directory
    
    # Add GitHub server  
    llm mcp add github npx @modelcontextprotocol/server-github --env GITHUB_PERSONAL_ACCESS_TOKEN=your_token
    
    # Get ready-to-use tool flags
    llm mcp tools --server filesystem --format commands
    """
    pass


@mcp_cli.command()
@click.argument("name")
@click.argument("command")
@click.argument("args", nargs=-1)
@click.option("--env", multiple=True, help="Environment variable KEY=value")
@click.option("--description", default="", help="Server description")
def add(name: str, command: str, args: tuple, env: tuple, description: str):
    """Register a new MCP server.
    
    Arguments are passed to the server command. Use -- to separate command arguments 
    from llm mcp add options if your command uses flags starting with -.
    
    Examples:
    
    \b
    # Filesystem server (single directory)
    llm mcp add filesystem npx -- -y @modelcontextprotocol/server-filesystem /Users/user/Documents
    
    # Alternative without -y flag
    llm mcp add filesystem npx @modelcontextprotocol/server-filesystem /Users/user/Documents
    
    # Filesystem server (multiple directories) 
    llm mcp add files npx @modelcontextprotocol/server-filesystem /Users/user/Documents /Users/user/Projects
    
    # GitHub server with token
    llm mcp add github npx @modelcontextprotocol/server-github --env GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxxx
    
    # Server with description
    llm mcp add myserver "python /path/to/server.py" --description "My custom MCP server"
    
    # Server with environment variables
    llm mcp add myserver ./server --env API_KEY=secret --env DEBUG=true
    """
    try:
        config_manager = ConfigManager()
        
        # Parse environment variables
        env_vars = {}
        for env_var in env:
            if "=" not in env_var:
                click.echo(f"Invalid environment variable format: {env_var}", err=True)
                click.echo("Use format: --env KEY=value", err=True)
                sys.exit(1)
            
            key, value = env_var.split("=", 1)
            env_vars[key] = value
        
        # Add server configuration
        config_manager.add_server(
            name=name,
            command=command,
            args=list(args),
            env_vars=env_vars if env_vars else None,
            description=description
        )
        
        click.echo(f"✓ Added MCP server '{name}'")
        
        if env_vars:
            click.echo(f"  Stored {len(env_vars)} environment variables securely")
        
        click.echo(f"  Command: {command}")
        if args:
            click.echo(f"  Args: {' '.join(args)}")
        if description:
            click.echo(f"  Description: {description}")
            
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@mcp_cli.command()
@click.argument("name")
def remove(name: str):
    """Remove an MCP server."""
    try:
        config_manager = ConfigManager()
        config_manager.remove_server(name)
        click.echo(f"✓ Removed MCP server '{name}'")
        
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@mcp_cli.command("list")
@click.option("--enabled-only", is_flag=True, help="Show only enabled servers")
@click.option("--with-status", is_flag=True, help="Include connection status")
def list_servers(enabled_only: bool, with_status: bool):
    """List registered MCP servers."""
    try:
        config_manager = ConfigManager()
        servers = config_manager.list_servers(enabled_only=enabled_only)
        
        if not servers:
            if enabled_only:
                click.echo("No enabled MCP servers found.")
            else:
                click.echo("No MCP servers registered.")
            return
        
        # Get status information if requested
        statuses = {}
        if with_status:
            server_manager = ServerManager()
            for name in servers.keys():
                statuses[name] = server_manager.get_server_status(name)
        
        # Display servers
        for name, server_config in servers.items():
            status_info = ""
            if with_status and name in statuses:
                status = statuses[name]
                if status.get("connected"):
                    status_info = " [CONNECTED]"
                elif status.get("last_error"):
                    status_info = f" [ERROR: {status['last_error']}]"
                else:
                    status_info = " [DISCONNECTED]"
            
            enabled_marker = "✓" if server_config.enabled else "✗"
            click.echo(f"{enabled_marker} {name}{status_info}")
            click.echo(f"    Command: {server_config.command}")
            
            if server_config.args:
                click.echo(f"    Args: {' '.join(server_config.args)}")
            
            if server_config.description:
                click.echo(f"    Description: {server_config.description}")
            
            if server_config.env:
                click.echo(f"    Environment variables: {len(server_config.env)} configured")
            
            if with_status and name in statuses:
                status = statuses[name]
                if "tools_count" in status:
                    click.echo(f"    Tools: {status['tools_count']} available")
                if status.get("connection_attempts", 0) > 0:
                    click.echo(f"    Connection attempts: {status['connection_attempts']}")
            
            click.echo()
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@mcp_cli.command()
@click.argument("name")
def enable(name: str):
    """Enable an MCP server."""
    try:
        config_manager = ConfigManager()
        config_manager.enable_server(name)
        click.echo(f"✓ Enabled MCP server '{name}'")
        
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@mcp_cli.command()
@click.argument("name")
def disable(name: str):
    """Disable an MCP server."""
    try:
        config_manager = ConfigManager()
        config_manager.disable_server(name)
        click.echo(f"✓ Disabled MCP server '{name}'")
        
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@mcp_cli.command()
@click.argument("name")
def test(name: str):
    """Test connectivity to an MCP server."""
    async def _test_server():
        try:
            server_manager = ServerManager()
            click.echo(f"Testing connection to MCP server '{name}'...")
            
            success, error = await server_manager.test_server(name)
            
            if success:
                click.echo(f"✓ Successfully connected to '{name}'")
                
                # Show available tools
                tools_by_server = await server_manager.get_tools(server_name=name)
                tools = tools_by_server.get(name, [])
                if tools:
                    click.echo(f"  Available tools: {len(tools)}")
                    for tool in tools[:5]:  # Show first 5 tools
                        click.echo(f"    - {tool['name']}")
                    if len(tools) > 5:
                        click.echo(f"    ... and {len(tools) - 5} more")
                else:
                    click.echo("  No tools available")
                    
            else:
                click.echo(f"✗ Failed to connect to '{name}'")
                if error:
                    click.echo(f"  Error: {error}")
                sys.exit(1)
                
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Connection test failed: {e}", err=True)
            sys.exit(1)
    
    # Run async test
    run_async(_test_server())


@mcp_cli.command()
@click.argument("name")
def describe(name: str):
    """Show detailed information about an MCP server."""
    async def _describe_server():
        try:
            config_manager = ConfigManager()
            server_manager = ServerManager()
            
            # Get server configuration
            server_config = config_manager.get_server(name)
            
            # Get server status
            status = server_manager.get_server_status(name)
            
            click.echo(f"MCP Server: {name}")
            click.echo(f"  Status: {'Enabled' if server_config.enabled else 'Disabled'}")
            click.echo(f"  Command: {server_config.command}")
            
            if server_config.args:
                click.echo(f"  Args: {' '.join(server_config.args)}")
            
            if server_config.description:
                click.echo(f"  Description: {server_config.description}")
            
            if server_config.env:
                click.echo(f"  Environment variables:")
                for key in server_config.env.keys():
                    click.echo(f"    - {key}: [STORED SECURELY]")
            
            click.echo(f"  Connection: {'Connected' if status.get('connected') else 'Disconnected'}")
            
            if status.get('last_error'):
                click.echo(f"  Last error: {status['last_error']}")
            
            if status.get('connection_attempts', 0) > 0:
                click.echo(f"  Connection attempts: {status['connection_attempts']}")
            
            # Get and display tools
            if server_config.enabled:
                click.echo("\nTools:")
                try:
                    tools_by_server = await server_manager.get_tools(server_name=name)
                    tools = tools_by_server.get(name, [])
                    
                    if tools:
                        for tool in tools:
                            click.echo(f"  ✓ {name}__{tool['name']}")
                            if tool.get('description'):
                                click.echo(f"      {tool['description']}")
                    else:
                        click.echo("  No tools available")
                        
                except Exception as e:
                    click.echo(f"  Failed to retrieve tools: {e}")
            else:
                click.echo("\nTools: [Server disabled]")
                
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Unexpected error: {e}", err=True)
            sys.exit(1)
    
    # Run async describe
    run_async(_describe_server())


@mcp_cli.command()
@click.argument("name")
def start(name: str):
    """Manually start an MCP server connection."""
    async def _start_server():
        try:
            server_manager = ServerManager()
            click.echo(f"Starting MCP server '{name}'...")
            
            success = await server_manager.start_server(name)
            
            if success:
                click.echo(f"✓ Successfully started '{name}'")
            else:
                click.echo(f"✗ Failed to start '{name}'")
                sys.exit(1)
                
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Failed to start server: {e}", err=True)
            sys.exit(1)
    
    # Run async start
    run_async(_start_server())


@mcp_cli.command()
@click.argument("name")
def stop(name: str):
    """Stop an MCP server connection."""
    async def _stop_server():
        try:
            server_manager = ServerManager()
            click.echo(f"Stopping MCP server '{name}'...")
            
            await server_manager.stop_server(name)
            click.echo(f"✓ Stopped '{name}'")
                
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Failed to stop server: {e}", err=True)
            sys.exit(1)
    
    # Run async stop
    run_async(_stop_server())



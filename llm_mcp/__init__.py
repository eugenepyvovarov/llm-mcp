"""LLM MCP Plugin - Model Context Protocol integration for LLM library."""

import logging

import llm

from .commands import mcp_cli
from . import commands_tools  # Import to register the additional commands
from .tool_provider import get_tool_provider
from .utils import setup_logging

__version__ = "1.0.4"

# Set up logging
logger = setup_logging(__name__)

# Global tool provider instance
_tool_provider = None


def get_global_tool_provider():
    """Get the global tool provider, creating it if necessary."""
    global _tool_provider
    if _tool_provider is None:
        _tool_provider = get_tool_provider()
    return _tool_provider




@llm.hookimpl
def register_commands(cli):
    """Register MCP management commands."""
    try:
        cli.add_command(mcp_cli)
        logger.debug("Registered MCP CLI commands")
    except Exception as e:
        logger.error(f"Failed to register MCP commands: {e}")


@llm.hookimpl
def register_tools(register):
    """Register MCP tools with LLM."""
    try:
        tool_provider = get_global_tool_provider()
        tool_provider.register_tools(register)
        logger.info("MCP tools registered with LLM")
    except Exception as e:
        logger.error(f"Failed to register MCP tools: {e}")


# Plugin metadata
__all__ = [
    "__version__",
    "register_commands", 
    "register_tools",
]
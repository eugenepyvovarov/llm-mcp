"""Basic tests for llm-mcp package."""

import pytest
from llm_mcp import __version__


def test_version():
    """Test that version is defined."""
    assert __version__ == "1.0.4"


def test_import():
    """Test that the package can be imported."""
    import llm_mcp
    assert llm_mcp is not None


def test_register_functions_exist():
    """Test that required register functions exist."""
    from llm_mcp import register_commands, register_tools
    assert callable(register_commands)
    assert callable(register_tools)
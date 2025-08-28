# llm-mcp-cli

A comprehensive LLM CLI plugin for Model Context Protocol (MCP) integration, enabling seamless interaction between the LLM command-line tool and MCP servers.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands Reference](#commands-reference)
  - [Server Management](#server-management)
  - [Tool Commands](#tool-commands)
- [Usage Examples](#usage-examples)
- [Common Workflows](#common-workflows)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## Installation

```bash
pip install llm-mcp-cli
```

### Requirements

- Python 3.8 or higher
- llm >= 0.13.0
- MCP-compatible servers (e.g., `@modelcontextprotocol/server-filesystem`)

## Quick Start

1. **Add an MCP server:**
```bash
llm mcp add filesystem npx @modelcontextprotocol/server-filesystem /path/to/directory
```

2. **List available tools:**
```bash
llm mcp tools --format list
```

3. **Use tools in LLM conversations:**
```bash
llm -m gpt-4 "List all files in my directory" $(llm mcp tools --format commands)
```

if you want to add specific server commands
```bash
llm -m gpt-4 "List all files in my directory" $(llm mcp tools --server fetch --format commands)
```

## Commands Reference

### Server Management

#### `llm mcp add`
Register a new MCP server.

**Syntax:**
```bash
llm mcp add <name> <command> [args...] [options]
```

**Parameters:**
- `name` (required) - Unique identifier for the server
- `command` (required) - Command to execute the server (e.g., `npx`, `python`)
- `args` (optional) - Additional arguments for the server command

**Options:**
- `--env KEY=value` - Set environment variables (can be used multiple times)
- `--description` - Add a description for the server

**Examples:**
```bash
# Add filesystem server
llm mcp add filesystem npx @modelcontextprotocol/server-filesystem /Users/docs

# First store your GitHub token (one-time setup)
llm keys set GITHUB_PERSONAL_ACCESS_TOKEN

# Add GitHub server (API key automatically resolved from LLM storage)
llm mcp add github npx @modelcontextprotocol/server-github

# Add server with description
llm mcp add myserver python /path/to/server.py \
  --description "Custom MCP server for data processing"

# Multiple environment variables
llm mcp add api-server ./server \
  --env API_KEY=secret \
  --env DEBUG=true \
  --env PORT=8080
```

#### `llm mcp remove`
Remove a registered MCP server.

**Syntax:**
```bash
llm mcp remove <name>
```

**Example:**
```bash
llm mcp remove filesystem
```

#### `llm mcp list`
List all registered MCP servers.

**Syntax:**
```bash
llm mcp list [options]
```

**Options:**
- `--enabled-only` - Show only enabled servers
- `--with-status` - Include connection status information

**Output includes:**
- Server name with enabled/disabled indicator (✓/✗)
- Command and arguments
- Description (if provided)
- Environment variable count
- Connection status (with `--with-status`)
- Available tools count (with `--with-status`)

**Examples:**
```bash
# List all servers
llm mcp list

# List only enabled servers with status
llm mcp list --enabled-only --with-status
```

#### `llm mcp enable`
Enable a disabled MCP server.

**Syntax:**
```bash
llm mcp enable <name>
```

**Example:**
```bash
llm mcp enable filesystem
```

#### `llm mcp disable`
Disable an MCP server without removing it.

**Syntax:**
```bash
llm mcp disable <name>
```

**Example:**
```bash
llm mcp disable filesystem
```

#### `llm mcp test`
Test connectivity to an MCP server.

**Syntax:**
```bash
llm mcp test <name>
```

**Output includes:**
- Connection success/failure status
- Available tools count
- First 5 tool names (if available)
- Error messages (if connection fails)

**Example:**
```bash
llm mcp test filesystem
```

#### `llm mcp describe`
Show detailed information about a specific MCP server.

**Syntax:**
```bash
llm mcp describe <name>
```

**Output includes:**
- Server configuration details
- Environment variables (keys only, values hidden)
- Connection status
- Complete list of available tools with descriptions

**Example:**
```bash
llm mcp describe filesystem
```

#### `llm mcp start`
Manually start an MCP server connection.

**Syntax:**
```bash
llm mcp start <name>
```

**Example:**
```bash
llm mcp start filesystem
```

#### `llm mcp stop`
Stop an active MCP server connection.

**Syntax:**
```bash
llm mcp stop <name>
```

**Example:**
```bash
llm mcp stop filesystem
```

### Tool Commands

#### `llm mcp tools`
List all available MCP tools from enabled servers.

**Syntax:**
```bash
llm mcp tools [options]
```

**Options:**
- `--server <name>` - Filter tools by specific server
- `--format <type>` - Output format (default: list)
  - `list` - Detailed format with descriptions
  - `names` - Tool names only, one per line
  - `commands` - As `-T` flags ready for use with llm
- `--names-only` - (Deprecated) Equivalent to `--format names`

**Examples:**
```bash
# List all tools with descriptions
llm mcp tools

# Get tools from specific server
llm mcp tools --server filesystem

# Get tool names only
llm mcp tools --format names

# Get ready-to-use command flags
llm mcp tools --format commands
# Output: -T filesystem__read_file -T filesystem__write_file ...
```

#### `llm mcp call-tool`
Call a specific MCP tool directly.

**Syntax:**
```bash
llm mcp call-tool <tool_name> [options]
```

**Parameters:**
- `tool_name` (required) - Tool name in format `server__tool`

**Options:**
- `--args <json>` - JSON object with tool arguments (default: "{}")

**Examples:**
```bash
# Read a file
llm mcp call-tool filesystem__read_file \
  --args '{"path": "/tmp/example.txt"}'

# List directory contents
llm mcp call-tool filesystem__list_directory \
  --args '{"path": "/Users/docs"}'

# Call with complex arguments
llm mcp call-tool github__search_repositories \
  --args '{"query": "language:python stars:>1000", "limit": 10}'
```

#### `llm mcp status`
Show overall MCP plugin status and statistics.

**Syntax:**
```bash
llm mcp status
```

**Output includes:**
- Total registered servers count
- Enabled servers count
- Connected servers count
- Available tools count
- Configuration directory path
- Log directory path

**Example:**
```bash
llm mcp status
```

## Usage Examples

### Basic Server Setup

```bash
# 1. Add a filesystem server for your documents
llm mcp add docs npx @modelcontextprotocol/server-filesystem ~/Documents

# 2. Store API keys securely (one-time setup)
llm keys set GITHUB_PERSONAL_ACCESS_TOKEN

# 3. Add a GitHub server (API key automatically resolved)
llm mcp add github npx @modelcontextprotocol/server-github

# 4. Verify servers are working
llm mcp test docs
llm mcp test github

# 5. List all available tools
llm mcp tools
```

### Using Tools with LLM

```bash
# Method 1: Use the tools in a conversation
llm -m gpt-4 \
  $(llm mcp tools --server docs --format commands) \
  "What markdown files are in my Documents folder?"

# Method 2: Specify individual tools
llm -m claude-3-opus \
  -T docs__read_file \
  -T docs__write_file \
  "Update the README.md file to include installation instructions"

# Method 3: Use all available tools
llm -m gpt-4 $(llm mcp tools --format commands) \
  "Analyze the project structure and create a summary"
```

### Direct Tool Invocation

```bash
# List files in a directory
llm mcp call-tool docs__list_directory \
  --args '{"path": "/Users/me/Documents"}'

# Read a specific file
llm mcp call-tool docs__read_file \
  --args '{"path": "/Users/me/Documents/notes.md"}'

# Search GitHub repositories
llm mcp call-tool github__search_repositories \
  --args '{"query": "mcp server", "limit": 5}'
```

## Common Workflows

### 1. Document Management Workflow

```bash
# Setup filesystem server for documents
llm mcp add documents npx @modelcontextprotocol/server-filesystem \
  ~/Documents ~/Projects

# Use with LLM to organize files
llm -m gpt-4 $(llm mcp tools --server documents --format commands) \
  "Create a summary of all README files in my Projects folder"
```

### 2. Code Analysis Workflow

```bash
# Add server for code directory
llm mcp add codebase npx @modelcontextprotocol/server-filesystem \
  /path/to/codebase

# Analyze code structure
llm -m claude-3-opus $(llm mcp tools --server codebase --format commands) \
  "Analyze the Python files and identify potential refactoring opportunities"
```

### 3. Multi-Server Workflow

```bash
# Store API keys once
llm keys set GITHUB_PERSONAL_ACCESS_TOKEN

# Add multiple servers (API keys automatically resolved)
llm mcp add docs npx @modelcontextprotocol/server-filesystem ~/Documents
llm mcp add code npx @modelcontextprotocol/server-filesystem ~/Code
llm mcp add github npx @modelcontextprotocol/server-github

# Use all tools together
llm -m gpt-4 $(llm mcp tools --format commands) \
  "Compare my local documentation with similar projects on GitHub"
```

### 4. Automatic API Key Resolution

The plugin automatically resolves common API keys from LLM's secure storage, eliminating the need for `--env` flags:

```bash
# 1. Store API keys securely using LLM's key storage (one-time setup)
llm keys set FIRECRAWL_API_KEY
llm keys set GITHUB_PERSONAL_ACCESS_TOKEN
llm keys set OPENAI_API_KEY

# 2. Add servers without needing to specify --env flags
llm mcp add firecrawl npx -- -y firecrawl-mcp
llm mcp add github npx @modelcontextprotocol/server-github

# 3. Test servers - API keys are automatically resolved
llm mcp test firecrawl  # ✓ Uses FIRECRAWL_API_KEY from storage
llm mcp test github     # ✓ Uses GITHUB_PERSONAL_ACCESS_TOKEN from storage
```

**Supported API Keys (automatically resolved):**
- `FIRECRAWL_API_KEY` - Firecrawl web scraping service
- `GITHUB_PERSONAL_ACCESS_TOKEN`, `GITHUB_TOKEN` - GitHub API access
- `OPENAI_API_KEY` - OpenAI API access
- `ANTHROPIC_API_KEY` - Anthropic API access  
- `GOOGLE_API_KEY` - Google services
- `BRAVE_SEARCH_API_KEY` - Brave Search API
- `TAVILY_API_KEY` - Tavily search API

**Resolution Priority:**
1. Environment variable (if already set)
2. LLM key storage (`llm keys get KEY_NAME`)
3. Server throws error if not found

### 5. Server Management Workflow

```bash
# Check overall status
llm mcp status

# List all servers with their status
llm mcp list --with-status

# Disable unused servers
llm mcp disable old-server

# Test specific server
llm mcp test docs

# Get detailed information
llm mcp describe docs
```

## Configuration

The llm-mcp plugin stores its configuration in the LLM configuration directory:

- **Config Directory**: `~/.config/io.datasette.llm/mcp/` (Unix/Linux/macOS)
- **Config Directory**: `%APPDATA%\io.datasette.llm\mcp\` (Windows)

### Configuration Files

- `servers.json` - Server configurations
- `logs/` - Server connection logs

### Environment Variables

Environment variables for servers are stored securely in the configuration and are not exposed in plain text when listing servers.

To update environment variables:
```bash
# Remove and re-add the server with new variables
llm mcp remove myserver
llm mcp add myserver command args --env NEW_KEY=new_value
```

## Troubleshooting

### Common Issues

#### Server won't connect
```bash
# Test the connection
llm mcp test servername

# Check server status
llm mcp describe servername

# Try restarting the server
llm mcp stop servername
llm mcp start servername
```

#### Tools not appearing
```bash
# Ensure server is enabled
llm mcp enable servername

# List tools for specific server
llm mcp tools --server servername

# Check server has tools available
llm mcp test servername
```

#### Environment variable issues
```bash
# Environment variables must be in KEY=value format
llm mcp add server command --env KEY=value  # ✓ Correct
llm mcp add server command --env KEY value   # ✗ Wrong
```

### Debug Commands

```bash
# Get detailed server information
llm mcp describe servername

# Check overall plugin status
llm mcp status

# View server list with connection status
llm mcp list --with-status

# Test individual server connectivity
llm mcp test servername
```


## Contributing

This is an open-source project. Contributions are welcome!

### Development Setup

```bash
# Clone the repository
git clone https://github.com/eugenepyvovarov/llm-mcp.git
cd llm-mcp

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest
```

## License

Apache 2.0 License - see LICENSE file for details.

## Support

For issues, questions, or suggestions:
- GitHub Issues: [github.com/eugenepyvovarov/llm-mcp/issues](https://github.com/eugenepyvovarov/llm-mcp/issues)
- Documentation: This README
- MCP Specification: [modelcontextprotocol.io](https://modelcontextprotocol.io)
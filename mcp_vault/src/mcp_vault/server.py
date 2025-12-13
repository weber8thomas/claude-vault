"""MCP server setup and tool registration for claude-vault."""

from mcp.server import Server
from mcp.types import Tool, TextContent
from typing import Sequence

# Import all tool handlers
from .tools.read import VaultStatusTool, VaultListTool, VaultGetTool
from .tools.write import VaultSetTool
from .tools.auth import VaultLoginTool, VaultLogoutTool
from .tools.inject import VaultInjectTool


# Create MCP server
app = Server("mcp-vault")

# Initialize all tool handlers
TOOL_HANDLERS = {
    "vault_status": VaultStatusTool(),
    "vault_login": VaultLoginTool(),
    "vault_logout": VaultLogoutTool(),
    "vault_list": VaultListTool(),
    "vault_get": VaultGetTool(),
    "vault_set": VaultSetTool(),
    "vault_inject": VaultInjectTool(),
}


@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    List all available Vault tools.

    Returns:
        List of Tool descriptions for MCP
    """
    return [handler.get_tool_description() for handler in TOOL_HANDLERS.values()]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> Sequence[TextContent]:
    """
    Execute a Vault tool with given arguments.

    Args:
        name: Tool name to execute
        arguments: Tool arguments from MCP

    Returns:
        Sequence of TextContent responses
    """
    handler = TOOL_HANDLERS.get(name)

    if not handler:
        return [TextContent(
            type="text",
            text=f"❌ Unknown tool: {name}\n\nAvailable tools: {', '.join(TOOL_HANDLERS.keys())}"
        )]

    try:
        return handler.run_tool(arguments)
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"""❌ Error executing {name}: {str(e)}

This is an unexpected error. Please check:
1. Tool arguments are correct
2. Vault session is valid (vault_status)
3. Network connectivity to Vault

Error details: {type(e).__name__}: {str(e)}"""
        )]

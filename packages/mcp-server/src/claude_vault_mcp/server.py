"""MCP server setup and tool registration for claude-vault."""

from typing import Sequence

from mcp.server import Server
from mcp.types import TextContent, Tool

from .tools.auth import VaultLoginTool, VaultLogoutTool
from .tools.example import VaultGenerateExampleTool
from .tools.inject import VaultInjectTool

# Import all tool handlers
from .tools.read import VaultGetTool, VaultListTool, VaultStatusTool
from .tools.scan import VaultScanComposeTool, VaultScanEnvTool
from .tools.write import VaultSetTool

# Create MCP server
app = Server("claude-vault")

# Initialize all tool handlers
TOOL_HANDLERS = {
    "vault_status": VaultStatusTool(),
    "vault_login": VaultLoginTool(),
    "vault_logout": VaultLogoutTool(),
    "vault_list": VaultListTool(),
    "vault_get": VaultGetTool(),
    "vault_set": VaultSetTool(),
    "vault_inject": VaultInjectTool(),
    "vault_scan_env": VaultScanEnvTool(),
    "vault_scan_compose": VaultScanComposeTool(),
    "vault_generate_example": VaultGenerateExampleTool(),
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
        return [
            TextContent(
                type="text",
                text="❌ Unknown tool: {}\n\nAvailable tools: {}".format(
                    name, ", ".join(TOOL_HANDLERS.keys())
                ),
            )
        ]

    try:
        return handler.run_tool(arguments)
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"""❌ Error executing {name}: {str(e)}

This is an unexpected error. Please check:
1. Tool arguments are correct
2. Vault session is valid (vault_status)
3. Network connectivity to Vault

Error details: {type(e).__name__}: {str(e)}""",
            )
        ]

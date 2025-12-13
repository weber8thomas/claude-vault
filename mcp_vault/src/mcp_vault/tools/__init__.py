"""Tool registry and base classes for MCP tools."""

from typing import Sequence
from mcp.types import Tool, TextContent


class ToolHandler:
    """Base class for MCP tool handlers."""

    def __init__(self, name: str):
        """Initialize tool handler with name."""
        self.name = name

    def get_tool_description(self) -> Tool:
        """
        Get MCP tool description with input schema.

        Must be implemented by subclasses.

        Returns:
            Tool description for MCP
        """
        raise NotImplementedError

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        """
        Execute the tool with given arguments.

        Must be implemented by subclasses.

        Args:
            arguments: Tool arguments from MCP

        Returns:
            Sequence of TextContent responses
        """
        raise NotImplementedError

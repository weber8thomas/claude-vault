"""MCP-Vault: Model Context Protocol server for HashiCorp Vault secret management."""

import asyncio
import sys
from .server import app


async def main():
    """
    Main entry point for MCP-Vault server.

    Sets up stdio-based MCP server and runs it.
    """
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def run():
    """Synchronous wrapper for main() to use as console script entry point."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMCP-Vault server stopped.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


__version__ = "1.0.0"
__all__ = ["main", "run", "app"]

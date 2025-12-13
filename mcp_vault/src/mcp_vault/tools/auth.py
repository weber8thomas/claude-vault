"""Authentication tools: vault_login, vault_logout."""

import subprocess
import os
from typing import Sequence
from pathlib import Path
from mcp.types import Tool, TextContent

from ..tools import ToolHandler
from ..session import VaultSession
from ..vault_client import VaultClient


class VaultLoginTool(ToolHandler):
    """Tool for guiding user through OIDC authentication."""

    def __init__(self):
        super().__init__("vault_login")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Authenticate to HashiCorp Vault via OIDC. This guides the user through the
browser-based authentication flow and updates environment variables.

⚠️ IMPORTANT: This tool cannot directly update environment variables for a running MCP server.
It will provide instructions for the user to complete the authentication, after which they must
restart the MCP server to pick up the new token.

The tool calls the existing vault-login-simple.sh script to handle the complex OIDC flow.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        # Check if VAULT_ADDR is set
        vault_addr = os.getenv('VAULT_ADDR')
        if not vault_addr:
            return [TextContent(
                type="text",
                text="""❌ VAULT_ADDR environment variable not set.

Before authenticating, the user must set:
  export VAULT_ADDR='https://vault.example.com'

Then run vault_login again."""
            )]

        return [TextContent(
            type="text",
            text=f"""🔐 Vault OIDC Authentication

To authenticate, the **user** must run the following in their terminal:

```bash
source claude-vault login
```

This will:
1. Open the Vault UI in your browser ({vault_addr}/ui/vault/auth?with=oidc)
2. Prompt you to sign in with OIDC via Authentik (MFA required)
3. Ask you to copy the token from the Vault UI
4. Export VAULT_TOKEN and VAULT_TOKEN_EXPIRY to your environment

**After authentication:**
1. The environment variables will be set in your terminal session
2. Claude Code will automatically inherit the new token
3. You can verify with: vault_status

**Session duration:** 60 minutes

⚠️ Note: This MCP server cannot execute the login script directly because it would run
in a subprocess with a separate environment. The user must source the script in their
shell to export the variables properly."""
            )]


class VaultLogoutTool(ToolHandler):
    """Tool for revoking token and providing cleanup instructions."""

    def __init__(self):
        super().__init__("vault_logout")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Revoke the current Vault token and provide instructions to clear environment
variables. This invalidates the session and requires re-authentication for future operations.

⚠️ IMPORTANT: After logout, the user must manually unset environment variables and restart
the MCP server.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        # Load session
        session = VaultSession.from_environment()
        if not session:
            return [TextContent(
                type="text",
                text="""ℹ️ No active Vault session found.

Environment variables are not set. If you previously authenticated,
they may have already been cleared."""
            )]

        # Attempt to revoke token
        client = VaultClient(session.vault_addr, session.vault_token)
        response = client.revoke_token()

        if response.success:
            revoke_message = "✅ Token successfully revoked in Vault."
        else:
            revoke_message = f"⚠️ Could not revoke token: {response.error}\n(Token may have already been revoked or expired)"

        return [TextContent(
            type="text",
            text=f"""{revoke_message}

**To complete logout, the user must:**

1. **Unset environment variables** in their terminal:
```bash
unset VAULT_TOKEN
unset VAULT_TOKEN_EXPIRY
unset VAULT_ADDR
```

2. **Restart this MCP server** to clear the session.

3. Verify logout with: vault_status
   (Should show "No Vault session found")

**Note:** Environment variables in this MCP server process remain set until restart.
The token has been revoked in Vault but environment cleanup requires user action."""
        )]

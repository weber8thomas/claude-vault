"""Read-only Vault tools: vault_status, vault_list, vault_get."""

import json
import time
from typing import Sequence
from mcp.types import Tool, TextContent

from ..tools import ToolHandler
from ..session import VaultSession
from ..vault_client import VaultClient
from ..security import SecurityValidator, ValidationError


class VaultStatusTool(ToolHandler):
    """Tool for checking Vault session status."""

    def __init__(self):
        super().__init__("vault_status")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Check the current Vault session status including:
- Token validity (active/expired/missing)
- User identity and policies
- Time remaining until expiry
- Vault connectivity

Returns detailed session information or error if not authenticated.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        # Load session from environment
        session = VaultSession.from_environment()
        if not session:
            return [TextContent(
                type="text",
                text="""❌ No Vault session found.

To authenticate, the user must run in their terminal:
  export VAULT_ADDR='https://vault.example.com'
  source claude-vault login

Then restart this MCP server to pick up the new token."""
            )]

        # Check expiry
        error = session.validate_or_error()
        if error:
            return [TextContent(type="text", text=f"❌ {error}")]

        # Validate token with Vault
        client = VaultClient(session.vault_addr, session.vault_token)
        response = client.lookup_token()

        if not response.success:
            return [TextContent(
                type="text",
                text=f"""❌ Token validation failed: {response.error}

The token may be invalid or revoked. Please re-authenticate:
  source claude-vault login"""
            )]

        # Extract token metadata
        token_data = response.data
        display_name = token_data.get('display_name', 'unknown')
        policies = ', '.join(token_data.get('policies', []))
        ttl = token_data.get('ttl', 0)
        entity_id = token_data.get('entity_id', 'none')

        # Format remaining time
        remaining = session.time_remaining()
        if remaining == -1:
            remaining_str = "Not tracked"
        elif remaining < 300:  # Less than 5 minutes
            remaining_str = f"⚠️  {remaining // 60}m {remaining % 60}s (expiring soon)"
        else:
            remaining_str = f"{remaining // 60}m {remaining % 60}s"

        return [TextContent(
            type="text",
            text=f"""✅ Vault Session Active

**Connection:**
- Vault Address: {session.vault_addr}
- Status: Connected

**Authentication:**
- User: {display_name}
- Entity ID: {entity_id}
- Policies: {policies}

**Session:**
- Time Remaining: {remaining_str}
- Token TTL: {ttl}s

The session is valid and ready for operations."""
        )]


class VaultListTool(ToolHandler):
    """Tool for listing services or secrets."""

    def __init__(self):
        super().__init__("vault_list")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""List services or secrets in Vault.
- Without service: Lists all available services under proxmox-services/
- With service: Lists secret keys (names only, no values) for that service

Returns structured data including metadata (version, timestamps).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Optional service name to list secrets for. If omitted, lists all services.",
                    }
                },
                "required": []
            }
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        # Load and validate session
        session = VaultSession.from_environment()
        if not session:
            error = VaultSession(vault_addr="", vault_token="", vault_token_expiry=0).validate_or_error()
            return [TextContent(type="text", text=f"❌ {error}")]

        error = session.validate_or_error()
        if error:
            return [TextContent(type="text", text=f"❌ {error}")]

        client = VaultClient(session.vault_addr, session.vault_token)
        service = arguments.get('service')

        if not service:
            # List all services
            response = client.list_services()
            if not response.success:
                return [TextContent(type="text", text=f"❌ Error listing services: {response.error}")]

            services = response.data['services']
            if not services:
                return [TextContent(
                    type="text",
                    text="""No services found in Vault.

To register a new service:
  vault_set tool with service name and secrets"""
                )]

            services_list = '\n'.join(f"  • {s}" for s in services)
            return [TextContent(
                type="text",
                text=f"""📋 Services in Vault ({len(services)} total):

{services_list}

To list secrets for a service:
  vault_list with service parameter"""
            )]
        else:
            # Validate service name
            try:
                SecurityValidator.validate_service_name(service)
            except ValidationError as e:
                return [TextContent(type="text", text=f"❌ Invalid service name: {e}")]

            # Get service secrets and metadata
            secret_response = client.get_secret(service)
            if not secret_response.success:
                return [TextContent(
                    type="text",
                    text=f"""❌ {secret_response.error}

To register this service:
  vault_set with service='{service}' and key=value pairs"""
                )]

            secrets = secret_response.data['secrets']
            metadata = secret_response.data['metadata']

            # Format metadata
            version = metadata.get('version', 'N/A')
            created_time = metadata.get('created_time', 'N/A')
            updated_time = metadata.get('updated_time', created_time)

            keys_list = '\n'.join(f"  • {key}" for key in secrets.keys())

            return [TextContent(
                type="text",
                text=f"""📋 Secrets for service: {service}

**Metadata:**
- Version: {version}
- Created: {created_time}
- Updated: {updated_time}

**Secret Keys ({len(secrets)} total):**
{keys_list}

To retrieve secret values:
  vault_get with service='{service}'"""
            )]


class VaultGetTool(ToolHandler):
    """Tool for retrieving secret values."""

    def __init__(self):
        super().__init__("vault_get")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Retrieve secret values from Vault for a specific service.
- Without key: Returns all secrets for the service
- With key: Returns only the specified secret value

⚠️ WARNING: This returns actual secret values. Use with caution.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name to retrieve secrets from",
                    },
                    "key": {
                        "type": "string",
                        "description": "Optional specific secret key to retrieve. If omitted, returns all secrets.",
                    }
                },
                "required": ["service"]
            }
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        # Load and validate session
        session = VaultSession.from_environment()
        if not session:
            error = VaultSession(vault_addr="", vault_token="", vault_token_expiry=0).validate_or_error()
            return [TextContent(type="text", text=f"❌ {error}")]

        error = session.validate_or_error()
        if error:
            return [TextContent(type="text", text=f"❌ {error}")]

        service = arguments.get('service')
        key = arguments.get('key')

        # Validate inputs
        try:
            SecurityValidator.validate_service_name(service)
            if key:
                SecurityValidator.validate_key_name(key)
        except ValidationError as e:
            return [TextContent(type="text", text=f"❌ Validation error: {e}")]

        client = VaultClient(session.vault_addr, session.vault_token)
        response = client.get_secret(service)

        if not response.success:
            return [TextContent(type="text", text=f"❌ {response.error}")]

        secrets = response.data['secrets']

        if key:
            # Return specific key
            if key not in secrets:
                available_keys = ', '.join(secrets.keys())
                return [TextContent(
                    type="text",
                    text=f"""❌ Key '{key}' not found in service '{service}'.

Available keys: {available_keys}"""
                )]

            return [TextContent(
                type="text",
                text=f"""🔐 Secret value for {service}/{key}:

```
{secrets[key]}
```"""
            )]
        else:
            # Return all secrets
            secrets_formatted = '\n'.join(
                f"  {k}: {v}" for k, v in secrets.items()
            )

            return [TextContent(
                type="text",
                text=f"""⚠️ WARNING: Displaying secret values!

🔐 Secrets for service: {service}

```
{secrets_formatted}
```

Total: {len(secrets)} secrets"""
            )]

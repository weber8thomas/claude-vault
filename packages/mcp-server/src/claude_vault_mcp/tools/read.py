"""Read-only Vault tools: vault_status, vault_list, vault_get."""

import json
import os
import time
from typing import Sequence

from mcp.types import TextContent, Tool

from ..security import SecurityValidator, ValidationError
from ..session import VaultSession
from ..tokenization import get_token_vault, should_tokenize_value
from ..tools import ToolHandler
from ..vault_client import VaultClient


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
            inputSchema={"type": "object", "properties": {}, "required": []},
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        # Load session from environment
        session = VaultSession.from_environment()
        if not session:
            return [
                TextContent(
                    type="text",
                    text="""❌ No Vault session found.

To authenticate, the user must run in their terminal:
  export VAULT_ADDR='https://vault.example.com'
  source claude-vault login

Then restart this MCP server to pick up the new token.""",
                )
            ]

        # Check expiry
        error = session.validate_or_error()
        if error:
            return [TextContent(type="text", text=f"❌ {error}")]

        # Validate token with Vault
        client = VaultClient(session.vault_addr, session.vault_token)
        response = client.lookup_token()

        if not response.success:
            return [
                TextContent(
                    type="text",
                    text=f"""❌ Token validation failed: {response.error}

The token may be invalid or revoked. Please re-authenticate:
  source claude-vault login""",
                )
            ]

        # Extract token metadata
        token_data = response.data
        display_name = token_data.get("display_name", "unknown")
        policies = ", ".join(token_data.get("policies", []))
        ttl = token_data.get("ttl", 0)
        entity_id = token_data.get("entity_id", "none")

        # Format remaining time
        remaining = session.time_remaining()
        if remaining == -1:
            remaining_str = "Not tracked"
        elif remaining < 300:  # Less than 5 minutes
            remaining_str = f"⚠️  {remaining // 60}m {remaining % 60}s (expiring soon)"
        else:
            remaining_str = f"{remaining // 60}m {remaining % 60}s"

        return [
            TextContent(
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

The session is valid and ready for operations.""",
            )
        ]


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
                "required": [],
            },
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        # Load and validate session
        session = VaultSession.from_environment()
        if not session:
            error = VaultSession(
                vault_addr="", vault_token="", vault_token_expiry=0
            ).validate_or_error()
            return [TextContent(type="text", text=f"❌ {error}")]

        error = session.validate_or_error()
        if error:
            return [TextContent(type="text", text=f"❌ {error}")]

        client = VaultClient(session.vault_addr, session.vault_token)
        service = arguments.get("service")

        if not service:
            # List all services
            response = client.list_services()
            if not response.success:
                return [
                    TextContent(type="text", text=f"❌ Error listing services: {response.error}")
                ]

            services = response.data["services"]
            if not services:
                return [
                    TextContent(
                        type="text",
                        text="""No services found in Vault.

To register a new service:
  vault_set tool with service name and secrets""",
                    )
                ]

            services_list = "\n".join(f"  • {s}" for s in services)
            return [
                TextContent(
                    type="text",
                    text=f"""📋 Services in Vault ({len(services)} total):

{services_list}

To list secrets for a service:
  vault_list with service parameter""",
                )
            ]
        else:
            # Validate service name
            try:
                SecurityValidator.validate_service_name(service)
            except ValidationError as e:
                return [TextContent(type="text", text=f"❌ Invalid service name: {e}")]

            # Get service secrets and metadata
            secret_response = client.get_secret(service)
            if not secret_response.success:
                return [
                    TextContent(
                        type="text",
                        text=f"""❌ {secret_response.error}

To register this service:
  vault_set with service='{service}' and key=value pairs""",
                    )
                ]

            secrets = secret_response.data["secrets"]
            metadata = secret_response.data["metadata"]

            # Format metadata
            version = metadata.get("version", "N/A")
            created_time = metadata.get("created_time", "N/A")
            updated_time = metadata.get("updated_time", created_time)

            keys_list = "\n".join(f"  • {key}" for key in secrets.keys())

            return [
                TextContent(
                    type="text",
                    text=f"""📋 Secrets for service: {service}

**Metadata:**
- Version: {version}
- Created: {created_time}
- Updated: {updated_time}

**Secret Keys ({len(secrets)} total):**
{keys_list}

To retrieve secret values:
  vault_get with service='{service}'""",
                )
            ]


class VaultGetTool(ToolHandler):
    """Tool for retrieving secret values."""

    def __init__(self):
        super().__init__("vault_get")

    def get_tool_description(self) -> Tool:
        security_mode = os.getenv("VAULT_SECURITY_MODE", "tokenized")

        if security_mode == "tokenized":
            description = """Retrieve secrets from Vault with values TOKENIZED for security.
- Returns secret keys with values replaced by temporary tokens (@token-xxx)
- Tokens are valid only for this session (2h default)
- Secret values never sent to Claude API
- Use vault_inject to generate .env files (tokens resolved locally)

Example:
  vault_get jellyfin
  → API_KEY: @token-a8f3d9e1b2c4f7a9
  → DB_PASSWORD: @token-b2c4f7a9c5d6e8f9

This allows AI to help with structure without exposing credentials."""
        elif security_mode == "redacted":
            description = """Retrieve secret KEYS (not values) from Vault for a specific service.
- Returns secret key names with values shown as <REDACTED>
- Secret values never sent to AI (security feature)
- Use vault_inject to generate .env files with actual values

This tool helps you understand secret structure without exposing credentials."""
        else:  # plaintext
            description = """Retrieve secret values from Vault for a specific service.
- Without key: Returns all secrets for the service
- With key: Returns only the specified secret value

⚠️ WARNING: This returns actual secret values to AI. Use with caution."""

        return Tool(
            name=self.name,
            description=description,
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
                    },
                },
                "required": ["service"],
            },
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        # Load and validate session
        session = VaultSession.from_environment()
        if not session:
            error = VaultSession(
                vault_addr="", vault_token="", vault_token_expiry=0
            ).validate_or_error()
            return [TextContent(type="text", text=f"❌ {error}")]

        error = session.validate_or_error()
        if error:
            return [TextContent(type="text", text=f"❌ {error}")]

        service = arguments.get("service")
        key = arguments.get("key")

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

        secrets = response.data["secrets"]

        # Check security mode (default: tokenized)
        security_mode = os.getenv("VAULT_SECURITY_MODE", "tokenized")

        if key:
            # Return specific key
            if key not in secrets:
                available_keys = ", ".join(secrets.keys())
                return [
                    TextContent(
                        type="text",
                        text=f"""❌ Key '{key}' not found in service '{service}'.

Available keys: {available_keys}""",
                    )
                ]

            value = secrets[key]

            if security_mode == "tokenized":
                # Tokenize the value
                vault = get_token_vault()
                if should_tokenize_value(key, value):
                    token = vault.tokenize(
                        value, metadata={"service": service, "key": key, "type": "vault_secret"}
                    )
                    display_value = token
                else:
                    # Non-sensitive value, send as-is
                    display_value = value

                return [
                    TextContent(
                        type="text",
                        text=f"""🔐 Secret: {service}/{key}

Value: {display_value}

ℹ️  Tokenization: {"Active" if display_value.startswith("@token-") else "Skipped (non-sensitive)"}

**To use this secret:**
- vault_inject: Generates .env file (token resolved locally)
- Token valid for session: {vault.session_id}
- Expires in: {vault.get_stats()['session_remaining_seconds']}s""",
                    )
                ]

            elif security_mode == "redacted":
                return [
                    TextContent(
                        type="text",
                        text=f"""🔐 Secret key: {service}/{key}

Value: <REDACTED>

ℹ️  Secret values are hidden for security. To use this secret:
- Use vault_inject to generate .env file (values written locally)
- Or change mode: VAULT_SECURITY_MODE=tokenized or plaintext""",
                    )
                ]

            else:  # plaintext
                return [
                    TextContent(
                        type="text",
                        text=f"""🔐 Secret value for {service}/{key}:

```
{value}
```

⚠️  Value sent to Claude API in plaintext!""",
                    )
                ]

        else:
            # Return all secrets
            if security_mode == "tokenized":
                # Tokenize all values
                vault = get_token_vault()
                tokenized = {}
                stats = {"tokenized": 0, "plaintext": 0}

                for k, v in secrets.items():
                    if should_tokenize_value(k, v):
                        tokenized[k] = vault.tokenize(
                            v, metadata={"service": service, "key": k, "type": "vault_secret"}
                        )
                        stats["tokenized"] += 1
                    else:
                        tokenized[k] = v
                        stats["plaintext"] += 1

                secrets_formatted = "\n".join(f"  {k}: {v}" for k, v in tokenized.items())

                return [
                    TextContent(
                        type="text",
                        text=f"""🔐 Secrets for service: {service} ({len(secrets)} total)

```
{secrets_formatted}
```

ℹ️  Tokenization active - secret values protected

**Statistics:**
- Tokenized: {stats['tokenized']} secrets
- Plaintext: {stats['plaintext']} (non-sensitive config)
- Session: {vault.session_id}
- Expires in: {vault.get_stats()['session_remaining_seconds']}s

**To use these secrets:**
- vault_inject: Generates .env file (all tokens resolved locally)

**AI can help with:**
- Understanding secret structure
- Creating migration plans
- Organizing services
- Generating configuration templates""",
                    )
                ]

            elif security_mode == "redacted":
                # Show keys only, redact values
                secrets_formatted = "\n".join(f"  {k}: <REDACTED>" for k in secrets.keys())

                return [
                    TextContent(
                        type="text",
                        text=f"""🔐 Secret keys for service: {service} ({len(secrets)} secrets)

```
{secrets_formatted}
```

ℹ️  Secret values are hidden for security.

**To use these secrets:**
- vault_inject: Generate .env file (values written locally, never sent to AI)

**AI can help with:**
- Understanding what secrets exist
- Organizing secret structure
- Creating migration plans
- Generating .env templates""",
                    )
                ]

            else:  # plaintext
                secrets_formatted = "\n".join(f"  {k}: {v}" for k, v in secrets.items())

                return [
                    TextContent(
                        type="text",
                        text=f"""⚠️ WARNING: Displaying secret values!

🔐 Secrets for service: {service}

```
{secrets_formatted}
```

Total: {len(secrets)} secrets

⚠️  All values sent to Claude API in plaintext!
Consider using VAULT_SECURITY_MODE=tokenized for better security.""",
                    )
                ]

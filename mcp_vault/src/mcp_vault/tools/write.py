"""Write tool: vault_set with security confirmation."""

import json
from typing import Sequence, Dict
from mcp.types import Tool, TextContent

from ..tools import ToolHandler
from ..session import VaultSession
from ..vault_client import VaultClient
from ..security import SecurityValidator, ValidationError, ConfirmationPrompt, AuditLogger


class VaultSetTool(ToolHandler):
    """Tool for creating or updating secrets with security confirmation."""

    def __init__(self):
        super().__init__("vault_set")
        self.audit_logger = AuditLogger()

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Create or update secrets in Vault for a service.

⚠️ SECURITY: This operation REQUIRES human confirmation. The tool will:
1. Validate all inputs (service name, keys, values)
2. Check for dangerous patterns (command injection, etc.)
3. Show a preview of changes
4. Prompt the user to type 'yes' to confirm
5. Write to audit log

The confirmation prompt will be displayed to the user and Claude MUST wait for the response.
DO NOT attempt to automatically confirm - this is a critical security checkpoint.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name to register secrets for",
                    },
                    "secrets": {
                        "type": "object",
                        "description": "Key-value pairs of secrets to register. Keys must be alphanumeric with dash/underscore.",
                        "additionalProperties": {
                            "type": "string"
                        }
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show preview without writing to Vault",
                        "default": False
                    }
                },
                "required": ["service", "secrets"]
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
        secrets = arguments.get('secrets', {})
        dry_run = arguments.get('dry_run', False)

        # Validate service name
        try:
            SecurityValidator.validate_service_name(service)
        except ValidationError as e:
            self.audit_logger.log("VALIDATION_FAILED", service, f"Service name: {e}")
            return [TextContent(type="text", text=f"❌ Invalid service name: {e}")]

        if not secrets:
            return [TextContent(type="text", text="❌ No secrets provided. 'secrets' must be a non-empty dictionary.")]

        # Validate all keys and values
        all_warnings = []
        try:
            for key, value in secrets.items():
                # Validate key name
                SecurityValidator.validate_key_name(key)

                # Validate value constraints
                SecurityValidator.validate_secret_value(value)

                # Detect dangerous patterns
                warnings = SecurityValidator.detect_dangerous_patterns(value)
                if warnings:
                    all_warnings.extend([f"{key}: {w}" for w in warnings])

        except ValidationError as e:
            self.audit_logger.log("VALIDATION_FAILED", service, str(e))
            return [TextContent(type="text", text=f"❌ Validation failed: {e}")]

        # Check if service exists (to determine CREATE vs UPDATE)
        client = VaultClient(session.vault_addr, session.vault_token)
        existing_response = client.get_secret(service)
        action = "UPDATE" if existing_response.success else "CREATE"

        # Merge with existing secrets if updating
        if action == "UPDATE":
            existing_secrets = existing_response.data['secrets']
            merged_secrets = {**existing_secrets, **secrets}
            new_keys = set(secrets.keys()) - set(existing_secrets.keys())
            updated_keys = set(secrets.keys()) & set(existing_secrets.keys())
        else:
            merged_secrets = secrets
            new_keys = set(secrets.keys())
            updated_keys = set()

        # Show preview
        preview_lines = [f"🔐 Preview: {action} secrets for service '{service}'", ""]

        if new_keys:
            preview_lines.append(f"New keys ({len(new_keys)}):")
            for key in new_keys:
                preview_lines.append(f"  + {key}")
            preview_lines.append("")

        if updated_keys:
            preview_lines.append(f"Updated keys ({len(updated_keys)}):")
            for key in updated_keys:
                preview_lines.append(f"  ~ {key}")
            preview_lines.append("")

        if all_warnings:
            preview_lines.append("⚠️  Security Warnings:")
            for warning in all_warnings:
                preview_lines.append(f"  - {warning}")
            preview_lines.append("")

        preview_lines.append("Data to write:")
        preview_lines.append(f"```json\n{json.dumps(merged_secrets, indent=2)}\n```")

        preview_text = '\n'.join(preview_lines)

        # Dry run mode - just show preview
        if dry_run:
            self.audit_logger.log("DRY_RUN", service, f"{action} with {len(secrets)} secrets")
            return [TextContent(
                type="text",
                text=f"""{preview_text}

🔍 DRY RUN MODE - No changes made.

To actually write these secrets, call vault_set without dry_run=true."""
            )]

        # SECURITY CHECKPOINT: Require human confirmation
        self.audit_logger.log("CONFIRMATION_REQUIRED", service, f"{action} with {len(secrets)} secrets")

        confirmed = ConfirmationPrompt.prompt_user(
            service=service,
            action=action,
            secrets=merged_secrets,
            warnings=all_warnings if all_warnings else None
        )

        if not confirmed:
            self.audit_logger.log("ABORTED", service, "User declined confirmation")
            return [TextContent(
                type="text",
                text=f"""❌ Operation aborted by user.

{preview_text}

No changes were made to Vault."""
            )]

        # User confirmed - proceed with write
        self.audit_logger.log("CONFIRMED", service, f"User confirmed {action}")

        write_response = client.write_secret(service, merged_secrets)

        if not write_response.success:
            self.audit_logger.log("FAILED", service, f"Write error: {write_response.error}")
            return [TextContent(
                type="text",
                text=f"""❌ Failed to write secrets: {write_response.error}

{preview_text}"""
            )]

        # Success!
        version = write_response.data.get('version', 'N/A')
        keys_written = ', '.join(secrets.keys())
        self.audit_logger.log("SUCCESS", service, f"{action} version={version} keys={keys_written}")

        return [TextContent(
            type="text",
            text=f"""✅ Success!

Service: {service}
Action: {action}
Version: {version}

Secrets registered:
{chr(10).join(f'  • {k}' for k in secrets.keys())}

Next steps:
  1. List secrets: vault_list with service='{service}'
  2. Inject to .env: vault_inject with service='{service}'

Audit log: Operation logged to .claude-vault-audit.log"""
        )]

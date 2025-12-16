"""Write tool: vault_set with security confirmation."""

import json
import os
from typing import Sequence

from mcp.types import TextContent, Tool

from ..approval_server import get_approval_server
from ..security import AuditLogger, SecurityValidator, ValidationError
from ..session import VaultSession
from ..tokenization import get_token_vault
from ..tools import ToolHandler
from ..vault_client import VaultClient


class VaultSetTool(ToolHandler):
    """Tool for creating or updating secrets with security confirmation."""

    def __init__(self):
        super().__init__("vault_set")
        self.audit_logger = AuditLogger()

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Create or update secrets in Vault for a service.

⚠️ SECURITY: WebAuthn approval workflow required:

PHASE 1 - Create Pending Operation:
  Call vault_set WITHOUT approval_token:
  - Validates all inputs (service name, keys, values)
  - Checks for dangerous patterns (command injection, etc.)
  - Creates pending operation in approval server
  - Returns approval URL (http://localhost:8091/approve/{op_id})

PHASE 2 - User Approves (Out of Band):
  User opens the approval URL in browser:
  - Reviews operation details (service, secrets, warnings)
  - Clicks "Approve with WebAuthn"
  - Authenticates using TouchID/Windows Hello/YubiKey
  - Server stores approval

PHASE 3 - Execute:
  Call vault_set WITH approval_token="{op_id}":
  - Verifies WebAuthn approval exists
  - Writes secrets to Vault
  - Logs to audit trail

Claude Code MUST:
1. First call without approval_token
2. Show approval URL to user
3. Wait for user to complete WebAuthn authentication
4. Only call with approval_token after user confirms
5. NEVER skip WebAuthn approval""",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name to register secrets for",
                    },
                    "secrets": {
                        "type": "object",
                        "description": (
                            "Key-value pairs of secrets to register. "
                            "Keys must be alphanumeric with dash/underscore."
                        ),
                        "additionalProperties": {"type": "string"},
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show preview without writing to Vault",
                        "default": False,
                    },
                    "approval_token": {
                        "type": "string",
                        "description": (
                            "Approval token from WebAuthn authentication. "
                            "Only provide after user has approved via the web UI."
                        ),
                    },
                },
                "required": ["service", "secrets"],
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
        secrets = arguments.get("secrets", {})
        dry_run = arguments.get("dry_run", False)
        approval_token = arguments.get("approval_token")

        # Validate service name
        try:
            SecurityValidator.validate_service_name(service)
        except ValidationError as e:
            self.audit_logger.log("VALIDATION_FAILED", service, f"Service name: {e}")
            return [TextContent(type="text", text=f"❌ Invalid service name: {e}")]

        if not secrets:
            return [
                TextContent(
                    type="text",
                    text="❌ No secrets provided. 'secrets' must be a non-empty dictionary.",
                )
            ]

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
            existing_secrets = existing_response.data["secrets"]
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

        preview_text = "\n".join(preview_lines)

        # Dry run mode - just show preview
        if dry_run:
            self.audit_logger.log("DRY_RUN", service, f"{action} with {len(secrets)} secrets")
            return [
                TextContent(
                    type="text",
                    text=f"""{preview_text}

🔍 DRY RUN MODE - No changes made.

To actually write these secrets, call vault_set without dry_run=true.""",
                )
            ]

        # SECURITY CHECKPOINT: Require WebAuthn approval
        if not approval_token:
            # Detokenize secrets for approval UI display
            # The approval UI is local-only, so it's safe to show real values
            # This allows users to verify what they're approving
            detokenized_secrets = {}
            tokens_map = {}  # Maps key -> token for display

            # Check if any values are tokens
            has_tokens = any(
                isinstance(v, str) and v.startswith("@token-") for v in merged_secrets.values()
            )

            if has_tokens:
                token_vault = get_token_vault()
                for key, value in merged_secrets.items():
                    if isinstance(value, str) and value.startswith("@token-"):
                        # Store the token for display
                        tokens_map[key] = value
                        # Detokenize the value
                        try:
                            detokenized_secrets[key] = token_vault.detokenize(value)
                        except Exception as e:
                            print(f"[VaultSet] Warning: Failed to detokenize {key}: {e}")
                            detokenized_secrets[key] = value  # Keep token if failed
                    else:
                        detokenized_secrets[key] = value
            else:
                detokenized_secrets = merged_secrets

            # Create pending operation and get approval server
            approval_server = get_approval_server()
            op_id, approval_url = approval_server.create_pending_operation(
                service=service,
                action=action,
                secrets=detokenized_secrets,  # Pass detokenized values
                warnings=all_warnings if all_warnings else None,
                tokens_map=tokens_map if tokens_map else None,  # Pass token mapping
            )

            self.audit_logger.log(
                "CONFIRMATION_REQUIRED",
                service,
                f"{action} with {len(secrets)} secrets, op_id={op_id}",
            )

            return [
                TextContent(
                    type="text",
                    text=f"""{preview_text}

⚠️  SECURITY CHECKPOINT - WEBAUTHN APPROVAL REQUIRED

This operation requires WebAuthn authentication (TouchID, Windows Hello, or YubiKey).

To approve:
  1. Open in browser: {approval_url}
  2. Review the operation details
  3. Click "Approve with WebAuthn"
  4. Authenticate with your device

After approval, call vault_set again with:
  vault_set(service="{service}", secrets={{...}}, approval_token="{op_id}")

Operation expires in 5 minutes.""",
                )
            ]

        # Check approval
        approval_server = get_approval_server()

        if not approval_server.is_approved(approval_token):
            msg = (
                "❌ Operation not approved\n\n"
                "Approval token: {}\n\n"
                "Please open: {}/approve/{}\n\n"
                "And complete WebAuthn authentication to approve "
                "this operation."
            ).format(approval_token, approval_server.origin, approval_token)
            return [TextContent(type="text", text=msg)]

        # User confirmed via WebAuthn - proceed with write
        self.audit_logger.log(
            "CONFIRMED",
            service,
            "User confirmed {} via WebAuthn, token={}".format(action, approval_token),
        )

        # Detokenize if in tokenized mode
        security_mode = os.getenv("VAULT_SECURITY_MODE", "tokenized")

        if security_mode == "tokenized":
            vault = get_token_vault()

            # Detokenize all token values
            detokenized_secrets = vault.detokenize_dict(merged_secrets)

            # Count how many were detokenized
            token_count = sum(
                1 for v in merged_secrets.values() if isinstance(v, str) and v.startswith("@token-")
            )

            if token_count > 0:
                self.audit_logger.log(
                    "DETOKENIZATION",
                    service,
                    f"Detokenized {token_count} token(s) before writing to Vault",
                )
        else:
            detokenized_secrets = merged_secrets

        # Write detokenized secrets to Vault
        write_response = client.write_secret(service, detokenized_secrets)

        if not write_response.success:
            self.audit_logger.log("FAILED", service, f"Write error: {write_response.error}")
            return [
                TextContent(
                    type="text",
                    text=f"""❌ Failed to write secrets: {write_response.error}

{preview_text}""",
                )
            ]

        # Success! Clean up pending operation
        approval_server.cleanup_operation(approval_token)

        version = write_response.data.get("version", "N/A")
        keys_written = ", ".join(secrets.keys())
        self.audit_logger.log("SUCCESS", service, f"{action} version={version} keys={keys_written}")

        return [
            TextContent(
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

Audit log: Operation logged to .claude-vault-audit.log""",
            )
        ]

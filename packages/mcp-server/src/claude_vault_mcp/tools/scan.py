"""Scan tools: vault_scan_env, vault_scan_compose."""

from pathlib import Path
from typing import Sequence

from mcp.types import TextContent, Tool

from ..approval_server import get_approval_server
from ..file_parsers import (
    classify_secret,
    extract_compose_secrets,
    get_env_file_references,
    parse_docker_compose,
    parse_env_file,
)
from ..security import AuditLogger, SecurityValidator, ValidationError
from ..session import VaultSession
from ..tokenization import get_token_vault
from ..tools import ToolHandler


class VaultScanEnvTool(ToolHandler):
    """Tool for scanning .env files and tokenizing secrets."""

    def __init__(self):
        super().__init__("vault_scan_env")
        self.audit_logger = AuditLogger()

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Scan .env files for secrets and tokenize them before sending to AI.

⚠️ SECURITY: WebAuthn approval workflow required:

PHASE 1 - Create Pending Scan:
  Call vault_scan_env WITHOUT approval_token:
  - Validates service name and file path
  - Checks file exists and is readable
  - Parses file to detect potential secrets
  - Creates pending scan operation in approval server
  - Returns approval URL (http://localhost:8091/approve/{op_id})

PHASE 2 - User Approves (Out of Band):
  User opens the approval URL in browser:
  - Reviews file path and number of secrets detected
  - Clicks "Approve with WebAuthn"
  - Authenticates using TouchID/Windows Hello/YubiKey
  - Server stores approval

PHASE 3 - Execute Scan:
  Call vault_scan_env WITH approval_token="{op_id}":
  - Verifies WebAuthn approval exists
  - Re-reads and parses file
  - Tokenizes detected secrets (AI never sees plaintext)
  - Returns structured data with tokens

Claude Code MUST:
1. First call without approval_token
2. Show approval URL to user
3. Wait for user to complete WebAuthn authentication
4. Only call with approval_token after user confirms
5. NEVER skip WebAuthn approval

Tokenization:
- Secret values replaced with @token-xxx tokens
- Non-sensitive config (ports, URLs, booleans) sent as plaintext
- Tokens valid for session lifetime (2h default)
- Use vault_set to store tokenized secrets to Vault""",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name (e.g., 'jellyfin', 'sonarr')",
                    },
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Optional: Path to .env file "
                            "(default: /workspace/proxmox-services/{service}/.env)"
                        ),
                    },
                    "approval_token": {
                        "type": "string",
                        "description": (
                            "Approval token from WebAuthn authentication. "
                            "Only provide after user has approved via the web UI."
                        ),
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
        file_path = arguments.get("file_path")
        approval_token = arguments.get("approval_token")

        # Validate service name
        try:
            SecurityValidator.validate_service_name(service)
        except ValidationError as e:
            return [TextContent(type="text", text=f"❌ Validation failed: {e}")]

        # Determine file path
        if not file_path:
            file_path = f"/workspace/proxmox-services/{service}/.env"

        # Validate file path
        try:
            SecurityValidator.validate_file_path(file_path, service)
        except ValidationError as e:
            return [TextContent(type="text", text=f"❌ {e}")]

        # Check if file exists
        if not Path(file_path).exists():
            return [
                TextContent(
                    type="text",
                    text=f"""❌ File not found: {file_path}

Please verify:
1. Service directory exists: /workspace/proxmox-services/{service}/
2. .env file exists in service directory
3. File path is correct if using custom path

You can use vault_list to see available services.""",
                )
            ]

        # PHASE 1: Create pending scan operation
        if not approval_token:
            return self._create_pending_scan(service, file_path)

        # PHASE 3: Execute scan with approval
        return self._execute_scan(service, file_path, approval_token)

    def _create_pending_scan(self, service: str, file_path: str) -> Sequence[TextContent]:
        """Phase 1: Create pending scan operation."""
        try:
            # Validate file size
            SecurityValidator.validate_file_size(file_path, max_size_mb=5)

            # Parse file to get count of secrets (don't tokenize yet)
            env_data = parse_env_file(file_path)

            # Classify secrets
            secret_count = 0
            config_count = 0

            for key, value in env_data.items():
                if classify_secret(key, value):
                    secret_count += 1
                else:
                    config_count += 1

            # Create pending operation
            approval_server = get_approval_server()

            op_id = approval_server.create_operation(
                service=service,
                action="SCAN_ENV",
                secrets={},  # Don't include actual values in pending op
                warnings=[],
                scan_file_path=file_path,
                metadata={"secret_count": secret_count, "config_count": config_count},
            )

            # Get approval URL
            approval_url = approval_server.get_approval_url(op_id)

            # Audit log
            self.audit_logger.log(
                service=service,
                action="SCAN_ENV_REQUESTED",
                details="file={} potential_secrets={} config={} op_id={}".format(
                    file_path, secret_count, config_count, op_id
                ),
            )

            msg = (
                "⚠️ SECURITY CHECKPOINT - SCAN APPROVAL REQUIRED\n\n"
                "This operation will read secrets from:\n"
                "  File: {}\n"
                "  Detected: {} potential secret(s)\n"
                "  Config values: {}\n\n"
                "The secrets will be tokenized (replaced with @token-xxx tokens) "
                "so AI never sees plaintext values.\n\n"
                "To approve this scan:\n"
                "  1. Open: {}\n"
                "  2. Review scan details\n"
                "  3. Authenticate with WebAuthn (TouchID/Windows Hello/YubiKey)\n\n"
                "After approval, call:\n"
                '  vault_scan_env(service="{}", approval_token="{}")'
            ).format(file_path, secret_count, config_count, approval_url, service, op_id)
            return [TextContent(type="text", text=msg)]

        except ValidationError as e:
            return [TextContent(type="text", text=f"❌ {e}")]
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"❌ Error creating scan operation: {e}",
                )
            ]

    def _execute_scan(
        self, service: str, file_path: str, approval_token: str
    ) -> Sequence[TextContent]:
        """Phase 3: Execute scan with approval."""
        try:
            # Verify approval
            approval_server = get_approval_server()

            if not approval_server.check_approval(approval_token):
                msg = (
                    "❌ Operation not approved or expired.\n\n"
                    "Please restart the approval workflow:\n"
                    '  1. Call vault_scan_env(service="{}") without approval_token\n'
                    "  2. Open the approval URL in your browser\n"
                    "  3. Complete WebAuthn authentication\n"
                    "  4. Call again with the approval token"
                ).format(service)
                return [TextContent(type="text", text=msg)]

            # Re-read and parse file
            env_data = parse_env_file(file_path)

            # Get TokenVault
            vault = get_token_vault()

            # Classify and tokenize secrets
            tokenized_secrets = {}
            non_secrets = {}

            for key, value in env_data.items():
                if classify_secret(key, value):
                    # Tokenize secret
                    token = vault.tokenize(
                        value,
                        metadata={
                            "service": service,
                            "key": key,
                            "source": "env_scan",
                            "file": file_path,
                        },
                    )
                    tokenized_secrets[key] = token
                else:
                    # Non-secret config - send as plaintext
                    non_secrets[key] = value

            # Audit log
            self.audit_logger.log(
                service=service,
                action="SCAN_ENV_SUCCESS",
                details="file={} secrets={} config={}".format(
                    file_path, len(tokenized_secrets), len(non_secrets)
                ),
            )

            # Mark as scanned in migration state
            from ..migration_state import mark_scanned

            mark_scanned(service, [file_path], len(tokenized_secrets))

            # Cleanup approved operation
            approval_server.cleanup_operation(approval_token)

            # Format response
            response_parts = [
                "✅ Scan completed successfully!\n\n",
                "**Service:** {}\n".format(service),
                "**File:** {}\n\n".format(file_path),
                "**Secrets Found (tokenized):**\n",
            ]

            for key, token in tokenized_secrets.items():
                response_parts.append("  • {}: {}\n".format(key, token))

            if non_secrets:
                response_parts.append("\n**Configuration Values (plaintext):**\n")
                for key, value in non_secrets.items():
                    # Truncate long values
                    display_value = value[:50] + "..." if len(value) > 50 else value
                    response_parts.append("  • {}: {}\n".format(key, display_value))

            response_parts.append(
                "\n**Summary:**\n"
                "- Total keys: {}\n"
                "- Secrets tokenized: {}\n"
                "- Config values: {}\n\n"
                "**Next Steps:**\n"
                "1. Review the secrets and decide which to migrate to Vault\n"
                "2. Use vault_set to store tokenized secrets\n\n"
                "**Tokenization Info:**\n"
                "Tokens are session-scoped and expire with your Vault session "
                "(2h default).\n"
                "The tokenization system ensures AI never sees plaintext "
                "secret values.".format(len(env_data), len(tokenized_secrets), len(non_secrets))
            )

            return [TextContent(type="text", text="".join(response_parts))]

        except Exception as e:
            self.audit_logger.log(service=service, action="SCAN_ENV_FAILED", details=str(e))
            return [
                TextContent(
                    type="text",
                    text=f"❌ Error executing scan: {e}",
                )
            ]


class VaultScanComposeTool(ToolHandler):
    """Tool for scanning docker-compose.yml files and extracting secrets."""

    def __init__(self):
        super().__init__("vault_scan_compose")
        self.audit_logger = AuditLogger()

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Scan docker-compose.yml files for secrets and tokenize them.

⚠️ SECURITY: WebAuthn approval workflow required (same as vault_scan_env):

PHASE 1 - Create Pending Scan:
  Call vault_scan_compose WITHOUT approval_token
  - Returns approval URL

PHASE 2 - User Approves:
  User opens URL and authenticates with WebAuthn

PHASE 3 - Execute Scan:
  Call vault_scan_compose WITH approval_token
  - Scans docker-compose.yml for secrets in environment variables
  - Tokenizes detected secrets
  - Returns structured data

Extracts secrets from:
- services.{name}.environment (dict or list format)
- Inline environment variable values

Notes:
- env_file references are noted but not scanned (use vault_scan_env for those)
- Secrets section (Docker Swarm) is noted but not extracted""",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name (e.g., 'jellyfin', 'sonarr')",
                    },
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Optional: Path to docker-compose.yml "
                            "(default: /workspace/proxmox-services/{service}/"
                            "docker-compose.yml)"
                        ),
                    },
                    "approval_token": {
                        "type": "string",
                        "description": (
                            "Approval token from WebAuthn authentication. "
                            "Only provide after user has approved via the web UI."
                        ),
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
        file_path = arguments.get("file_path")
        approval_token = arguments.get("approval_token")

        # Validate service name
        try:
            SecurityValidator.validate_service_name(service)
        except ValidationError as e:
            return [TextContent(type="text", text=f"❌ Validation failed: {e}")]

        # Determine file path
        if not file_path:
            file_path = f"/workspace/proxmox-services/{service}/docker-compose.yml"

        # Validate file path
        try:
            SecurityValidator.validate_file_path(file_path, service)
        except ValidationError as e:
            return [TextContent(type="text", text=f"❌ {e}")]

        # Check if file exists
        if not Path(file_path).exists():
            # Try alternative names
            alt_paths = [
                f"/workspace/proxmox-services/{service}/docker-compose.yaml",
                f"/workspace/proxmox-services/{service}/compose.yml",
                f"/workspace/proxmox-services/{service}/compose.yaml",
            ]

            for alt_path in alt_paths:
                if Path(alt_path).exists():
                    file_path = alt_path
                    break
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"""❌ Docker compose file not found.

Tried:
- {file_path}
- {chr(10).join('- ' + p for p in alt_paths)}

Please verify the service directory exists and contains a docker-compose file.""",
                    )
                ]

        # PHASE 1: Create pending scan operation
        if not approval_token:
            return self._create_pending_scan(service, file_path)

        # PHASE 3: Execute scan with approval
        return self._execute_scan(service, file_path, approval_token)

    def _create_pending_scan(self, service: str, file_path: str) -> Sequence[TextContent]:
        """Phase 1: Create pending scan operation."""
        try:
            # Validate file size
            SecurityValidator.validate_file_size(file_path, max_size_mb=5)

            # Parse compose file
            compose_data = parse_docker_compose(file_path)

            # Extract secrets to get count
            all_secrets = {}
            services_with_secrets = []

            services = compose_data.get("services", {})
            for svc_name, svc_config in services.items():
                svc_secrets = extract_compose_secrets(compose_data, svc_name)
                if svc_secrets:
                    all_secrets.update(svc_secrets)
                    services_with_secrets.append(svc_name)

            secret_count = len(all_secrets)

            # Create pending operation
            approval_server = get_approval_server()

            op_id = approval_server.create_operation(
                service=service,
                action="SCAN_COMPOSE",
                secrets={},
                warnings=[],
                scan_file_path=file_path,
                metadata={
                    "secret_count": secret_count,
                    "services_with_secrets": services_with_secrets,
                },
            )

            # Get approval URL
            approval_url = approval_server.get_approval_url(op_id)

            # Audit log
            self.audit_logger.log(
                service=service,
                action="SCAN_COMPOSE_REQUESTED",
                details=("file={} potential_secrets={} containers={} op_id={}").format(
                    file_path, secret_count, len(services_with_secrets), op_id
                ),
            )

            msg = (
                "⚠️ SECURITY CHECKPOINT - SCAN APPROVAL REQUIRED\n\n"
                "This operation will read secrets from:\n"
                "  File: {}\n"
                "  Detected: {} potential secret(s) in {} container(s)\n"
                "  Containers: {}\n\n"
                "The secrets will be tokenized (replaced with @token-xxx tokens).\n\n"
                "To approve this scan:\n"
                "  1. Open: {}\n"
                "  2. Review scan details\n"
                "  3. Authenticate with WebAuthn\n\n"
                "After approval, call:\n"
                '  vault_scan_compose(service="{}", approval_token="{}")'
            ).format(
                file_path,
                secret_count,
                len(services_with_secrets),
                ", ".join(services_with_secrets) if services_with_secrets else "none",
                approval_url,
                service,
                op_id,
            )
            return [TextContent(type="text", text=msg)]

        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"❌ Error creating scan operation: {e}",
                )
            ]

    def _execute_scan(
        self, service: str, file_path: str, approval_token: str
    ) -> Sequence[TextContent]:
        """Phase 3: Execute scan with approval."""
        try:
            # Verify approval
            approval_server = get_approval_server()

            if not approval_server.check_approval(approval_token):
                return [
                    TextContent(
                        type="text",
                        text=(
                            "❌ Operation not approved or expired.\n\n"
                            "Please restart the approval workflow."
                        ),
                    )
                ]

            # Parse compose file
            compose_data = parse_docker_compose(file_path)

            # Get TokenVault
            vault = get_token_vault()

            # Extract and tokenize secrets by container
            secrets_by_container = {}

            services = compose_data.get("services", {})
            for svc_name, svc_config in services.items():
                svc_secrets = extract_compose_secrets(compose_data, svc_name)

                if svc_secrets:
                    # Tokenize secrets
                    tokenized = {}
                    for key, value in svc_secrets.items():
                        token = vault.tokenize(
                            value,
                            metadata={
                                "service": service,
                                "container": svc_name,
                                "key": key,
                                "source": "compose_scan",
                                "file": file_path,
                            },
                        )
                        tokenized[key] = token

                    secrets_by_container[svc_name] = tokenized

            # Get env_file references
            env_files = []
            for svc_name in services:
                env_refs = get_env_file_references(compose_data, svc_name)
                env_files.extend(env_refs)

            env_files = list(set(env_files))  # Deduplicate

            # Get compose version
            compose_version = compose_data.get("version", "unknown")

            # Count total secrets
            total_secrets = sum(len(s) for s in secrets_by_container.values())

            # Audit log
            self.audit_logger.log(
                service=service,
                action="SCAN_COMPOSE_SUCCESS",
                details="file={} secrets={} containers={}".format(
                    file_path, total_secrets, len(secrets_by_container)
                ),
            )

            # Mark as scanned
            from ..migration_state import mark_scanned

            mark_scanned(service, [file_path], total_secrets)

            # Cleanup approved operation
            approval_server.cleanup_operation(approval_token)

            # Format response
            response_parts = [
                "✅ Docker Compose scan completed!\n\n",
                "**Service:** {}\n".format(service),
                "**File:** {}\n".format(file_path),
                "**Compose Version:** {}\n\n".format(compose_version),
                "**Secrets Found (tokenized):**\n",
            ]

            if secrets_by_container:
                for container, secrets in secrets_by_container.items():
                    response_parts.append("\n*Container: {}*\n".format(container))
                    for key, token in secrets.items():
                        response_parts.append("  • {}: {}\n".format(key, token))
            else:
                response_parts.append("  No inline secrets detected\n")

            if env_files:
                response_parts.append("\n**env_file References:**\n")
                for ef in env_files:
                    response_parts.append("  • {}\n".format(ef))
                response_parts.append(
                    "\nℹ️ Use vault_scan_env to scan these .env files " "separately.\n"
                )

            response_parts.append(
                "\n**Summary:**\n"
                "- Total containers: {}\n"
                "- Secrets found: {}\n\n"
                "**Next Steps:**\n"
                "1. If env_file references found, scan those files with "
                "vault_scan_env\n"
                "2. Use vault_set to store tokenized secrets to Vault\n"
                "3. Consider updating compose file to use vault_inject "
                "generated .env files".format(len(services), total_secrets)
            )

            return [TextContent(type="text", text="".join(response_parts))]

        except Exception as e:
            self.audit_logger.log(service=service, action="SCAN_COMPOSE_FAILED", details=str(e))
            return [
                TextContent(
                    type="text",
                    text=f"❌ Error executing scan: {e}",
                )
            ]

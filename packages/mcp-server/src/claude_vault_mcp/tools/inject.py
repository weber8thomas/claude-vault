"""Injection tool: vault_inject to generate .env or secrets.yaml files."""

import os
import subprocess
from pathlib import Path
from typing import Sequence

from mcp.types import TextContent, Tool

from ..security import SecurityValidator, ValidationError
from ..session import VaultSession
from ..tokenization import get_token_vault
from ..tools import ToolHandler
from ..vault_client import VaultClient


class VaultInjectTool(ToolHandler):
    """Tool for injecting secrets from Vault to local configuration files."""

    def __init__(self):
        super().__init__("vault_inject")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="""Inject secrets from Vault into local configuration files (.env or secrets.yaml).

This reads secrets from Vault and generates configuration files with actual values:
- .env file for services using environment variables
- config/secrets.yaml for services using YAML configuration (e.g., ESPHome)

**Tokenization support:**
- If VAULT_SECURITY_MODE=tokenized, this tool automatically resolves all @token-xxx references
- Secret values are detokenized locally (never sent to Claude API)
- Final .env file contains plaintext values for the service to use

**File handling:**
- Format auto-detected from service directory structure, or can be specified
- Existing files are backed up with timestamp before being replaced
- Generated files should be in .gitignore (DO NOT COMMIT)

**Security:** This is the only tool that writes plaintext secrets to disk. All detokenization happens locally on your machine.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name to inject secrets for",
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format (env or yaml). If 'auto', detects from service directory.",
                        "enum": ["auto", "env", "yaml"],
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
        format_type = arguments.get("format", "auto")
        template = arguments.get("template")  # Optional: AI-provided template with tokens

        # Validate service name
        try:
            SecurityValidator.validate_service_name(service)
        except ValidationError as e:
            return [TextContent(type="text", text=f"❌ Invalid service name: {e}")]

        # If AI provided a template with tokens, use it directly
        if template:
            return self._inject_from_template(service, template, format_type)

        # Otherwise, use the legacy inject script
        # Find the inject-secrets.sh script
        script_path = Path("/workspace/proxmox-services/scripts/inject-secrets.sh")

        if not script_path.exists():
            return [
                TextContent(
                    type="text",
                    text=f"""❌ Injection script not found at {script_path}

The inject-secrets.sh script is required for generating configuration files.

Manual injection steps:
1. Get secrets: vault_get with service='{service}'
2. Create .env or secrets.yaml file manually
3. Copy secret values into the file""",
                )
            ]

        # Build command
        cmd = ["bash", str(script_path), service]
        if format_type != "auto":
            cmd.append(format_type)

        # Set up environment with Vault credentials
        env = {
            **subprocess.os.environ,
            "VAULT_ADDR": session.vault_addr,
            "VAULT_TOKEN": session.vault_token,
        }

        if session.vault_token_expiry:
            env["VAULT_TOKEN_EXPIRY"] = str(session.vault_token_expiry)

        try:
            # Run the inject script
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
                cwd="/workspace/proxmox-services",
            )

            if result.returncode == 0:
                # Success
                output = result.stdout
                return [
                    TextContent(
                        type="text",
                        text=f"""✅ Secrets injected successfully for service: {service}

{output}

The configuration file has been generated with secrets from Vault.

**Next steps:**
1. Review the generated file for correctness
2. Start or restart the service to pick up the new configuration
3. Verify the service is working correctly

**Security reminder:**
- The generated file contains sensitive data
- It should be in .gitignore (DO NOT COMMIT)
- Original file was backed up if it existed""",
                    )
                ]
            else:
                # Error
                error_output = result.stderr or result.stdout
                return [
                    TextContent(
                        type="text",
                        text=f"""❌ Injection failed for service: {service}

Error:
```
{error_output}
```

Possible causes:
- Service '{service}' not found in Vault (register with vault_set first)
- Service directory doesn't exist at /workspace/proxmox-services/{service}/
- Permission issues writing to the target directory

To debug:
1. Check if service exists: vault_list with service='{service}'
2. Verify service directory exists
3. Check file permissions""",
                    )
                ]

        except subprocess.TimeoutExpired:
            return [
                TextContent(
                    type="text",
                    text=f"""❌ Injection timed out after 30 seconds.

The inject-secrets.sh script took too long to complete.

Try:
1. Check Vault connectivity: vault_status
2. Run injection manually: bash {script_path} {service}""",
                )
            ]
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"""❌ Unexpected error during injection: {str(e)}

This may indicate an issue with the inject-secrets.sh script or environment.

Manual fallback:
1. Get secrets: vault_get with service='{service}'
2. Create configuration file manually""",
                )
            ]

    def _inject_from_template(
        self, service: str, template: str, format_type: str
    ) -> Sequence[TextContent]:
        """
        Inject secrets using an AI-provided template (with tokens).

        Args:
            service: Service name
            template: Template content (may contain @token-xxx references)
            format_type: Output format (env/yaml/auto)

        Returns:
            Result message
        """
        # Detokenize the template
        security_mode = os.getenv("VAULT_SECURITY_MODE", "tokenized")

        if security_mode == "tokenized":
            try:
                vault = get_token_vault()
                detokenized_content = vault.detokenize_text(template)
                tokens_resolved = template.count("@token-")
            except ValueError as e:
                return [
                    TextContent(
                        type="text",
                        text=f"""❌ Token resolution failed: {str(e)}

This may mean:
- Token session expired (restart MCP server)
- Unknown token in template
- Template contains invalid token format""",
                    )
                ]
        else:
            # No tokenization, use template as-is
            detokenized_content = template
            tokens_resolved = 0

        # Determine output path
        if format_type == "yaml":
            output_path = f"{service}/config/secrets.yaml"
        else:  # env or auto
            output_path = f"{service}/.env"

        # Write the file
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Backup existing file if it exists
            if output_file.exists():
                import shutil
                from datetime import datetime

                backup_path = f"{output_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(output_file, backup_path)
                backed_up = True
            else:
                backed_up = False

            # Write new content
            output_file.write_text(detokenized_content)

            return [
                TextContent(
                    type="text",
                    text=f"""✅ Generated {output_path}

**Summary:**
- Tokens resolved: {tokens_resolved}
- Security mode: {security_mode}
- File backed up: {"Yes" if backed_up else "No (new file)"}
- Lines written: {len(detokenized_content.splitlines())}

⚠️  File contains sensitive data:
- Do not commit to git
- Verify .gitignore includes {output_path.split('/')[-1]}
- Secrets written in plaintext for service use

**Next steps:**
1. Review the generated file
2. Restart the {service} service to load new configuration
3. Verify service is working correctly""",
                )
            ]

        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"""❌ Failed to write file: {str(e)}

**Possible causes:**
- Permission denied writing to {output_path}
- Service directory doesn't exist
- Disk space issues

**To debug:**
1. Check directory exists: ls -la {service}/
2. Check permissions: ls -la {output_path}
3. Manually create: mkdir -p {service}/config/""",
                )
            ]

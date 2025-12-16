"""
Tool for generating .env.example files with secrets redacted.

This tool creates example/template files from .env or docker-compose.yml files
by replacing secret values with <REDACTED> placeholders while preserving
configuration values and file structure.
"""

from pathlib import Path
from typing import Sequence

from mcp.types import TextContent, Tool

from ..file_parsers import (
    classify_secret,
    parse_docker_compose,
    parse_env_file_with_structure,
)
from ..security import AuditLogger, SecurityValidator
from . import ToolHandler


class VaultGenerateExampleTool(ToolHandler):
    """Generate .env.example or docker-compose.example.yml files."""

    def __init__(self):
        super().__init__("vault_generate_example")
        self.audit_logger = AuditLogger()

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Generate .env.example or docker-compose.example.yml files "
                "with secrets redacted.\n\n"
                "This tool reads configuration files and creates example/template "
                "versions by:\n"
                "- Replacing secret values with <REDACTED> placeholders\n"
                "- Preserving configuration values (ports, hosts, feature flags, etc.)\n"
                "- Maintaining all comments and file structure\n"
                "- Useful for committing to git as documentation\n\n"
                "No WebAuthn approval required "
                "(only reads file structure, not secret values).\n\n"
                "Example usage:\n"
                '  vault_generate_example(service="jellyfin")\n'
                '  vault_generate_example(service="sonarr", '
                'file_path="/custom/path/.env")\n'
                '  vault_generate_example(service="jellyfin", format="yaml")'
            ),
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
                            "Optional: Path to source file "
                            "(default: /workspace/proxmox-services/{service}/.env)"
                        ),
                    },
                    "format": {
                        "type": "string",
                        "enum": ["auto", "env", "yaml"],
                        "description": (
                            "File format: 'auto' (detect), 'env', or 'yaml' " "(default: auto)"
                        ),
                    },
                    "output_path": {
                        "type": "string",
                        "description": (
                            "Optional: Output path "
                            "(default: same directory with .example extension)"
                        ),
                    },
                },
                "required": ["service"],
            },
        )

    def run_tool(self, arguments: dict) -> Sequence[TextContent]:
        """Execute the example file generation."""
        service = arguments.get("service")
        file_path = arguments.get("file_path")
        file_format = arguments.get("format", "auto")
        output_path = arguments.get("output_path")

        # Determine source file path
        if not file_path:
            file_path = f"/workspace/proxmox-services/{service}/.env"

        file_path_obj = Path(file_path)

        # Validate file path
        try:
            SecurityValidator.validate_file_path(file_path, service)
        except Exception as e:
            return [TextContent(type="text", text="❌ Security validation failed: {}".format(e))]

        # Check file exists
        if not file_path_obj.exists():
            return [TextContent(type="text", text="❌ File not found: {}".format(file_path))]

        # Auto-detect format if needed
        if file_format == "auto":
            if file_path.endswith(".yml") or file_path.endswith(".yaml"):
                file_format = "yaml"
            else:
                file_format = "env"

        # Determine output path
        if not output_path:
            if file_format == "env":
                output_path = str(file_path_obj.parent / ".env.example")
            else:
                # For YAML files
                stem = file_path_obj.stem
                output_path = str(file_path_obj.parent / f"{stem}.example.yml")

        # Generate example file
        try:
            if file_format == "env":
                self._generate_env_example(file_path, output_path, service)
            else:
                self._generate_yaml_example(file_path, output_path, service)

            # Log operation
            self.audit_logger.log(
                "GENERATE_EXAMPLE",
                service,
                "Generated example file: {}".format(output_path),
            )

            return [
                TextContent(
                    type="text",
                    text=self._format_success_message(service, file_path, output_path, file_format),
                )
            ]

        except Exception as e:
            self.audit_logger.log(
                "GENERATE_EXAMPLE_ERROR",
                service,
                "Failed: {}".format(str(e)),
            )
            return [
                TextContent(type="text", text="❌ Failed to generate example file: {}".format(e))
            ]

    def _generate_env_example(self, source_path: str, output_path: str, service: str):
        """Generate .env.example file."""
        # Parse source file with structure
        env_lines = parse_env_file_with_structure(source_path)

        # Build example file content
        lines = []

        # Add header
        lines.append("# Example Environment Variables")
        lines.append("# Service: {}".format(service))
        lines.append("# Copy to .env and fill in actual values")
        lines.append("#")
        lines.append("# Values marked with <REDACTED> are secrets that must be provided")
        lines.append("# Other values are safe defaults that can be used as-is or customized")
        lines.append("")

        # Process each line
        for env_line in env_lines:
            if env_line.type == "comment":
                lines.append(env_line.raw_line)
            elif env_line.type == "blank":
                lines.append("")
            elif env_line.type in ("assignment", "export"):
                key = env_line.key
                value = env_line.value

                # Classify as secret or config
                is_secret = classify_secret(key, value)

                if is_secret:
                    # Replace with redacted placeholder
                    if env_line.type == "export":
                        lines.append("export {}=<REDACTED>".format(key))
                    else:
                        lines.append("{}=<REDACTED>".format(key))
                else:
                    # Keep config value as-is
                    if env_line.type == "export":
                        lines.append("export {}={}".format(key, value))
                    else:
                        lines.append("{}={}".format(key, value))

        # Write to output file
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
            if lines:  # Add trailing newline if file has content
                f.write("\n")

    def _generate_yaml_example(self, source_path: str, output_path: str, service: str):
        """Generate docker-compose.example.yml file."""
        import yaml  # noqa: F401

        # Parse source file - using yaml module via parse_docker_compose
        parse_docker_compose(source_path)

        # Load original YAML to preserve structure
        with open(source_path, "r") as f:
            compose_data = yaml.safe_load(f)

        # Process environment variables in each service
        if "services" in compose_data:
            for service_name, service_config in compose_data["services"].items():
                if "environment" in service_config:
                    env = service_config["environment"]

                    if isinstance(env, dict):
                        # Dict format: key: value
                        for key, value in env.items():
                            if isinstance(value, str):
                                if classify_secret(key, value):
                                    env[key] = "<REDACTED>"

                    elif isinstance(env, list):
                        # List format: ["KEY=value", ...]
                        new_env = []
                        for item in env:
                            if "=" in item:
                                key, value = item.split("=", 1)
                                if classify_secret(key, value):
                                    new_env.append("{}=<REDACTED>".format(key))
                                else:
                                    new_env.append(item)
                            else:
                                new_env.append(item)
                        service_config["environment"] = new_env

        # Write to output file with header comment
        with open(output_path, "w") as f:
            f.write("# Example Docker Compose Configuration\n")
            f.write("# Service: {}\n".format(service))
            f.write("# Copy to docker-compose.yml and fill in actual values\n")
            f.write("#\n")
            f.write("# Values marked with <REDACTED> are secrets that must be provided\n")
            f.write("# Other values are safe defaults\n")
            f.write("\n")
            yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)

    def _format_success_message(
        self, service: str, source_path: str, output_path: str, file_format: str
    ) -> str:
        """Format success message."""
        # Read the generated file to count secrets
        secrets_count = 0
        config_count = 0

        if file_format == "env":
            with open(output_path, "r") as f:
                for line in f:
                    line_stripped = line.strip()
                    if "=" in line_stripped and not line_stripped.startswith("#"):
                        value = line_stripped.split("=", 1)[1]
                        if value == "<REDACTED>":
                            secrets_count += 1
                        else:
                            config_count += 1

        return (
            "✅ Example file generated successfully!\n\n"
            "**Service:** {}\n"
            "**Source:** {}\n"
            "**Output:** {}\n"
            "**Format:** {}\n\n"
            "**Summary:**\n"
            "  • Secret values redacted: {}\n"
            "  • Config values preserved: {}\n\n"
            "**Next steps:**\n"
            "1. Review the example file: {}\n"
            "2. Commit it to git for documentation\n"
            "3. Add {} to .gitignore\n\n"
            "**Usage for new deployments:**\n"
            "1. Copy .example file to actual config file\n"
            "2. Fill in <REDACTED> values with actual secrets\n"
            "3. Or use vault_inject to populate from Vault"
        ).format(
            service,
            source_path,
            output_path,
            file_format,
            secrets_count,
            config_count,
            output_path,
            Path(source_path).name,
        )

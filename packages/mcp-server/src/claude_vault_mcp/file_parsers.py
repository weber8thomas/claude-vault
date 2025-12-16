"""File parsing utilities for .env and docker-compose files."""

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class EnvLine:
    """Represents a line in a .env file for structure preservation."""

    type: str  # "comment", "blank", "assignment", "export"
    key: Optional[str] = None
    value: Optional[str] = None
    raw_line: str = ""
    comment: Optional[str] = None  # Inline comment after value


def parse_env_file(file_path: str) -> Dict[str, str]:
    """
    Parse .env file into key-value pairs.

    Handles:
    - Comments (# prefix)
    - Quoted values ("..." or '...')
    - Multiline values (with quotes)
    - Blank lines
    - export prefix (export KEY=value)

    Args:
        file_path: Path to .env file

    Returns:
        Dict of key-value pairs

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file cannot be parsed
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    result = {}
    path = Path(file_path)

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse line by line
    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()

        # Skip blank lines and comments
        if not line or line.strip().startswith("#"):
            i += 1
            continue

        # Match KEY=VALUE pattern (with optional export prefix)
        match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)

        if match:
            key = match.group(1)
            value = match.group(2)

            # Handle quoted values (single or double quotes)
            if value.startswith('"') or value.startswith("'"):
                quote_char = value[0]

                # Check if quote is closed on same line
                if len(value) > 1 and value.endswith(quote_char):
                    # Remove quotes
                    value = value[1:-1]
                else:
                    # Multiline value - collect until closing quote
                    multiline_value = value[1:]  # Remove opening quote
                    i += 1

                    while i < len(lines):
                        next_line = lines[i]
                        multiline_value += "\n" + next_line

                        if next_line.rstrip().endswith(quote_char):
                            # Remove closing quote
                            multiline_value = multiline_value[:-1]
                            break

                        i += 1

                    value = multiline_value
            else:
                # Unquoted value - strip inline comments
                comment_match = re.match(r"^([^#]*?)\s*#", value)
                if comment_match:
                    value = comment_match.group(1).strip()
                else:
                    value = value.strip()

            result[key] = value

        i += 1

    return result


def parse_env_file_with_structure(file_path: str) -> List[EnvLine]:
    """
    Parse .env file preserving structure (comments, blank lines, order).

    Args:
        file_path: Path to .env file

    Returns:
        List of EnvLine objects
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    lines_data = []
    path = Path(file_path)

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blank line
        if not stripped:
            lines_data.append(EnvLine(type="blank", raw_line=line))
            i += 1
            continue

        # Comment line
        if stripped.startswith("#"):
            lines_data.append(EnvLine(type="comment", raw_line=line))
            i += 1
            continue

        # Assignment line
        match = re.match(r"^(\s*)(?:(export)\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)

        if match:
            # indent = match.group(1)  # Reserved for future use
            is_export = match.group(2) is not None
            key = match.group(3)
            value = match.group(4)

            # Handle quoted multiline values
            if (value.startswith('"') or value.startswith("'")) and len(value) > 0:
                quote_char = value[0]

                # Check if quote is closed
                if len(value) > 1 and value.endswith(quote_char):
                    # Single line quoted value - remove quotes for storage
                    parsed_value = value[1:-1]
                    lines_data.append(
                        EnvLine(
                            type="export" if is_export else "assignment",
                            key=key,
                            value=parsed_value,
                            raw_line=line,
                        )
                    )
                else:
                    # Multiline value
                    multiline_value = value[1:]  # Remove opening quote
                    original_lines = [line]
                    i += 1

                    while i < len(lines):
                        next_line = lines[i]
                        original_lines.append(next_line)
                        multiline_value += "\n" + next_line

                        if next_line.rstrip().endswith(quote_char):
                            multiline_value = multiline_value[:-1]
                            break

                        i += 1

                    lines_data.append(
                        EnvLine(
                            type="export" if is_export else "assignment",
                            key=key,
                            value=multiline_value,
                            raw_line="\n".join(original_lines),
                        )
                    )
            else:
                # Unquoted value
                comment_match = re.match(r"^([^#]*?)\s*(#.*)$", value)
                if comment_match:
                    parsed_value = comment_match.group(1).strip()
                    inline_comment = comment_match.group(2)
                else:
                    parsed_value = value.strip()
                    inline_comment = None

                lines_data.append(
                    EnvLine(
                        type="export" if is_export else "assignment",
                        key=key,
                        value=parsed_value,
                        raw_line=line,
                        comment=inline_comment,
                    )
                )

        else:
            # Unrecognized line format - keep as-is
            lines_data.append(EnvLine(type="unknown", raw_line=line))

        i += 1

    return lines_data


def write_env_file(
    file_path: str,
    data: Dict[str, str],
    preserve_structure: bool = False,
    original_structure: Optional[List[EnvLine]] = None,
) -> None:
    """
    Write .env file, optionally preserving structure.

    Args:
        file_path: Output file path
        data: Key-value pairs to write
        preserve_structure: If True, use original_structure as template
        original_structure: Original EnvLine list for structure preservation
    """
    path = Path(file_path)

    if preserve_structure and original_structure:
        # Preserve original structure
        lines = []

        for env_line in original_structure:
            if env_line.type in ["comment", "blank", "unknown"]:
                # Keep as-is
                lines.append(env_line.raw_line)
            elif env_line.type in ["assignment", "export"]:
                # Replace value if key exists in data
                if env_line.key in data:
                    new_value = data[env_line.key]

                    # Check if value needs quoting (contains spaces, special chars)
                    needs_quotes = (
                        " " in new_value
                        or "\n" in new_value
                        or '"' in new_value
                        or "#" in new_value
                    )

                    if needs_quotes:
                        # Use double quotes, escape any internal quotes
                        escaped_value = new_value.replace('"', '\\"')
                        value_str = f'"{escaped_value}"'
                    else:
                        value_str = new_value

                    # Reconstruct line
                    prefix = "export " if env_line.type == "export" else ""
                    suffix = f" {env_line.comment}" if env_line.comment else ""
                    lines.append(f"{prefix}{env_line.key}={value_str}{suffix}")
                else:
                    # Key not in new data - keep original line
                    lines.append(env_line.raw_line)

        # Add any new keys not in original structure
        existing_keys = {line.key for line in original_structure if line.key is not None}
        new_keys = set(data.keys()) - existing_keys

        if new_keys:
            if lines and lines[-1].strip():  # Add blank line before new keys
                lines.append("")

            for key in sorted(new_keys):
                value = data[key]
                needs_quotes = " " in value or "\n" in value or '"' in value or "#" in value

                if needs_quotes:
                    escaped_value = value.replace('"', '\\"')
                    lines.append(f'{key}="{escaped_value}"')
                else:
                    lines.append(f"{key}={value}")

        content = "\n".join(lines)
    else:
        # Simple write without structure preservation
        lines = []

        for key, value in sorted(data.items()):
            needs_quotes = " " in value or "\n" in value or '"' in value or "#" in value

            if needs_quotes:
                escaped_value = value.replace('"', '\\"')
                lines.append(f'{key}="{escaped_value}"')
            else:
                lines.append(f"{key}={value}")

        content = "\n".join(lines)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        if content and not content.endswith("\n"):
            f.write("\n")


def parse_docker_compose(file_path: str) -> Dict:
    """
    Parse docker-compose.yml file.

    Args:
        file_path: Path to docker-compose.yml

    Returns:
        Dict with parsed compose file structure including:
        - version: Compose file version
        - services: Service definitions
        - secrets: Top-level secrets section (if present)

    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If YAML is invalid
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return {}

    return data


def write_docker_compose(file_path: str, data: Dict) -> None:
    """
    Write docker-compose.yml preserving structure.

    Args:
        file_path: Output file path
        data: Docker compose data structure
    """
    path = Path(file_path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write YAML with nice formatting
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )


def classify_secret(key: str, value: str) -> bool:
    """
    Determine if a key-value pair is likely a secret.

    Returns True if the value should be tokenized (likely a secret),
    False if it should be sent as plaintext (likely configuration).

    Args:
        key: Environment variable key
        value: Environment variable value

    Returns:
        True if likely a secret, False if likely config
    """
    if not value or not isinstance(value, str):
        return False

    # Normalize for comparison
    key_upper = key.upper()
    value_lower = value.lower()

    # 1. Non-secret key patterns (common configuration keys)
    NON_SECRET_KEYS = {
        "PORT",
        "PORTS",
        "HOST",
        "HOSTNAME",
        "DOMAIN",
        "URL",
        "ENVIRONMENT",
        "ENV",
        "NODE_ENV",
        "DEBUG",
        "LOG_LEVEL",
        "LOGLEVEL",
        "TIMEZONE",
        "TZ",
        "PUID",
        "PGID",
        "UMASK",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "PATH",
        "HOME",
        "USER",
        "UID",
        "GID",
        "WORKDIR",
        "VERSION",
    }

    if key_upper in NON_SECRET_KEYS:
        return False

    # 2. Public URLs (not secrets)
    if value.startswith(("http://", "https://", "ftp://", "ws://", "wss://")):
        return False

    # 3. Boolean/simple values (not secrets)
    if value_lower in (
        "true",
        "false",
        "yes",
        "no",
        "1",
        "0",
        "enabled",
        "disabled",
        "on",
        "off",
    ):
        return False

    # 4. Too short to be a secret (< 8 characters)
    if len(value) < 8:
        return False

    # 5. Numeric-only values (ports, IDs, etc.)
    if value.isdigit():
        return False

    # 6. Path patterns (file paths, not secrets)
    if value.startswith(("/", "./", "../")) and "/" in value:
        return False

    # 7. Variable expansion syntax (references, not secrets)
    if "${" in value or "$(" in value:
        return False

    # 8. Secret key patterns (strong indicators of secrets)
    SECRET_KEY_PATTERNS = [
        "PASSWORD",
        "PASSWD",
        "PWD",
        "SECRET",
        "TOKEN",
        "API_KEY",
        "APIKEY",
        "API",
        "KEY",
        "PRIVATE_KEY",
        "PRIV_KEY",
        "AUTH",
        "CREDENTIAL",
        "CREDS",
        "SALT",
        "HASH",
        "ENCRYPTION_KEY",
        "ENCRYPT",
        "SIGNATURE",
        "CERT",
        "CERTIFICATE",
        "LICENSE",
        "SESSION",
    ]

    for pattern in SECRET_KEY_PATTERNS:
        if pattern in key_upper:
            return True

    # 9. High entropy check (potential random secrets)
    # Only for longer values (>= 16 chars)
    if len(value) >= 16:
        try:
            # Calculate Shannon entropy
            freq = Counter(value)
            entropy = -sum(
                (count / len(value)) * math.log2(count / len(value)) for count in freq.values()
            )

            # High entropy (>= 3.5 bits per character) suggests random string
            # This catches API keys, tokens, UUIDs, etc.
            if entropy >= 3.5:
                return True
        except (ValueError, ZeroDivisionError):
            pass

    # 10. Default: if uncertain and long enough, treat as secret (safer)
    # This ensures we don't accidentally expose secrets
    if len(value) >= 20:
        return True

    return False


def backup_file(file_path: str) -> str:
    """
    Create timestamped backup of file.

    Args:
        file_path: Path to file to backup

    Returns:
        Backup file path

    Raises:
        FileNotFoundError: If original file doesn't exist
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent file: {file_path}")

    # Generate timestamp: YYYYMMDD_HHMMSS
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create backup path
    backup_path = path.parent / f"{path.name}.backup.{timestamp}"

    # Copy file
    from shutil import copy2

    copy2(path, backup_path)

    return str(backup_path)


def extract_compose_secrets(compose_data: Dict, service_name: str) -> Dict[str, str]:
    """
    Extract secrets from docker-compose service definition.

    Args:
        compose_data: Parsed docker-compose data
        service_name: Service name to extract secrets from

    Returns:
        Dict of environment variable secrets found in the service
    """
    secrets = {}

    services = compose_data.get("services", {})
    service = services.get(service_name, {})

    # Extract from environment section
    environment = service.get("environment", {})

    # Environment can be dict or list format
    if isinstance(environment, dict):
        for key, value in environment.items():
            if isinstance(value, str) and classify_secret(key, value):
                secrets[key] = value
    elif isinstance(environment, list):
        for item in environment:
            if "=" in item:
                key, value = item.split("=", 1)
                if classify_secret(key, value):
                    secrets[key] = value

    return secrets


def get_env_file_references(compose_data: Dict, service_name: str) -> List[str]:
    """
    Get list of env_file references from docker-compose service.

    Args:
        compose_data: Parsed docker-compose data
        service_name: Service name

    Returns:
        List of env_file paths referenced
    """
    services = compose_data.get("services", {})
    service = services.get(service_name, {})

    env_file = service.get("env_file", [])

    # env_file can be string or list
    if isinstance(env_file, str):
        return [env_file]
    elif isinstance(env_file, list):
        return env_file

    return []

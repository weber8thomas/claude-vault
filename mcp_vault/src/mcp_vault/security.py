"""Security validation, confirmation prompts, and audit logging."""

import re
import sys
import json
from datetime import datetime
from typing import List, Dict
from pathlib import Path


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


class SecurityValidator:
    """Validates inputs to prevent injection attacks and enforce naming rules."""

    # Dangerous patterns that might indicate command injection
    DANGEROUS_PATTERNS = [
        (r'\$\(', 'command substitution: $(...)'),
        (r'`', 'backticks (command execution)'),
        (r'\$\{', 'variable expansion: ${...}'),
        (r'&&', 'command chaining: &&'),
        (r'\|\|', 'command chaining: ||'),
        (r';', 'command separator: ;'),
        (r'\n', 'newline character'),
        (r'\r', 'carriage return'),
    ]

    @staticmethod
    def validate_service_name(name: str) -> None:
        """
        Validate service name format.

        Args:
            name: Service name to validate

        Raises:
            ValidationError if name is invalid
        """
        if not name:
            raise ValidationError("Service name cannot be empty")

        if len(name) > 64:
            raise ValidationError("Service name too long (max 64 characters)")

        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise ValidationError(
                "Service name must contain only letters, numbers, dash, and underscore. "
                "This prevents path traversal and injection attacks."
            )

        # Prevent dangerous patterns
        if '..' in name or name.startswith('/') or '/' in name:
            raise ValidationError(
                "Service name cannot contain '..' or '/' (path traversal prevention)"
            )

    @staticmethod
    def validate_key_name(name: str) -> None:
        """
        Validate secret key name format.

        Args:
            name: Key name to validate

        Raises:
            ValidationError if name is invalid
        """
        if not name:
            raise ValidationError("Key name cannot be empty")

        if len(name) > 128:
            raise ValidationError("Key name too long (max 128 characters)")

        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise ValidationError(
                "Key name must contain only letters, numbers, dash, and underscore"
            )

    @staticmethod
    def detect_dangerous_patterns(value: str) -> List[str]:
        """
        Scan a value for dangerous patterns that might indicate injection.

        Args:
            value: Secret value to scan

        Returns:
            List of detected pattern descriptions (empty if clean)
        """
        warnings = []
        for pattern, description in SecurityValidator.DANGEROUS_PATTERNS:
            if re.search(pattern, value):
                warnings.append(description)
        return warnings

    @staticmethod
    def validate_secret_value(value: str) -> None:
        """
        Validate secret value constraints.

        Args:
            value: Secret value to validate

        Raises:
            ValidationError if value is invalid
        """
        if len(value) > 8192:
            raise ValidationError("Secret value too long (max 8KB to prevent DoS)")


class ConfirmationPrompt:
    """Interactive confirmation for write operations."""

    @staticmethod
    def prompt_user(service: str, action: str, secrets: Dict[str, str], warnings: List[str] = None) -> bool:
        """
        Display security checkpoint and get user confirmation.

        Args:
            service: Service name
            action: Action being performed (CREATE or UPDATE)
            secrets: Dictionary of secrets to be written
            warnings: List of security warnings (dangerous patterns)

        Returns:
            True if user confirmed with "yes", False otherwise
        """
        print("\n" + "=" * 70)
        print("⚠️  SECURITY CHECKPOINT - MANUAL VALIDATION REQUIRED")
        print("=" * 70)
        print()
        print(f"You are about to write secrets to Vault:")
        print(f"  Service: {service}")
        print(f"  Action: {action}")
        print(f"  Path: secret/proxmox-services/{service}")
        print()

        if warnings:
            print("⚠️  WARNING: Potentially dangerous patterns detected:")
            for warning in warnings:
                print(f"  - {warning}")
            print()

        print("Secrets to be written:")
        for key in secrets.keys():
            print(f"  + {key}")
        print()

        print("Preview (first 50 chars of each value):")
        for key, value in secrets.items():
            preview = value[:50] + "..." if len(value) > 50 else value
            print(f"  {key}: {preview}")
        print()

        print("⚠️  If you are Claude Code (AI assistant):")
        print("  - STOP and show this prompt to the human user")
        print("  - DO NOT automatically answer 'yes'")
        print("  - Wait for explicit human confirmation")
        print()
        print("=" * 70)

        try:
            response = input("Type 'yes' to proceed, or anything else to abort: ").strip()
            return response == "yes"
        except (EOFError, KeyboardInterrupt):
            print("\nAborted by user (Ctrl+C)")
            return False


class AuditLogger:
    """Audit logging for all Vault operations."""

    def __init__(self, log_path: str = None):
        """
        Initialize audit logger.

        Args:
            log_path: Path to audit log file (default: .claude-vault-audit.log in repo root)
        """
        if log_path is None:
            # Default to repo root
            repo_root = Path(__file__).parent.parent.parent.parent
            self.log_path = repo_root / ".claude-vault-audit.log"
        else:
            self.log_path = Path(log_path)

    def log(self, action: str, service: str, details: str, user: str = "mcp-server"):
        """
        Write audit log entry.

        Args:
            action: Action performed (SUCCESS, FAILED, CONFIRMED, ABORTED, etc.)
            service: Service name
            details: Additional details
            user: User/source of the action
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        log_entry = f"[{timestamp}] USER={user} ACTION={action} SERVICE={service} DETAILS={details}\n"

        try:
            with open(self.log_path, 'a') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Warning: Could not write to audit log: {e}", file=sys.stderr)

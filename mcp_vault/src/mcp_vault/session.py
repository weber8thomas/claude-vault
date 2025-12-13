"""Session management for Vault authentication via environment variables."""

import os
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class VaultSession:
    """Represents a Vault session loaded from environment variables."""

    vault_addr: str
    vault_token: str
    vault_token_expiry: int  # Unix timestamp

    @classmethod
    def from_environment(cls) -> Optional['VaultSession']:
        """
        Load Vault session from environment variables.

        Returns:
            VaultSession if all required env vars are present, None otherwise
        """
        vault_addr = os.getenv('VAULT_ADDR')
        vault_token = os.getenv('VAULT_TOKEN')
        vault_token_expiry = os.getenv('VAULT_TOKEN_EXPIRY')

        if not vault_addr or not vault_token:
            return None

        # Parse expiry timestamp (optional, but recommended)
        expiry = None
        if vault_token_expiry:
            try:
                expiry = int(vault_token_expiry)
            except ValueError:
                # Invalid format, treat as no expiry set
                pass

        return cls(
            vault_addr=vault_addr,
            vault_token=vault_token,
            vault_token_expiry=expiry if expiry else 0
        )

    def is_valid(self) -> bool:
        """
        Check if the session is still valid (not expired).

        Returns:
            True if session is valid, False if expired or invalid
        """
        if not self.vault_token or not self.vault_addr:
            return False

        # If no expiry set, consider it valid (legacy tokens)
        if self.vault_token_expiry == 0:
            return True

        current_time = int(time.time())
        return current_time < self.vault_token_expiry

    def time_remaining(self) -> int:
        """
        Get remaining time in seconds until expiry.

        Returns:
            Seconds remaining, or 0 if expired, or -1 if no expiry set
        """
        if self.vault_token_expiry == 0:
            return -1  # No expiry tracking

        current_time = int(time.time())
        remaining = self.vault_token_expiry - current_time
        return max(0, remaining)

    def validate_or_error(self) -> str:
        """
        Validate session and return error message if invalid.

        Returns:
            Empty string if valid, error message if invalid
        """
        if not self.vault_token:
            return """No Vault session found.

To authenticate, the user must run in their terminal:
  export VAULT_ADDR='https://vault.example.com'
  source claude-vault login

Then restart this MCP server to pick up the new token."""

        if not self.is_valid():
            if self.vault_token_expiry > 0:
                expired_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.vault_token_expiry))
                return f"""Vault session expired at {expired_at}.

To re-authenticate, the user must run:
  source claude-vault login

Then restart this MCP server."""
            else:
                return """Vault session is invalid.

Please re-authenticate:
  source claude-vault login"""

        return ""  # Valid

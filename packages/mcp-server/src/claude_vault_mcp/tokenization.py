"""
Token-based secret protection for Claude-Vault.

Tokenization replaces sensitive secret values with temporary tokens that only
the local MCP server can resolve. This ensures secrets never reach Claude API
while still allowing AI to help with structure and migration.
"""

import hashlib
import re
import secrets
import time
from datetime import datetime
from typing import Any, Dict, Optional


class TokenVault:
    """
    Manages tokenization/detokenization of secrets.

    Tokens are session-scoped and expire after configurable TTL.
    All storage is in-memory only (never persisted to disk).

    Example:
        vault = TokenVault()
        token = vault.tokenize("sk-1234567890abcdef")
        # → "@token-a8f3d9e1b2c4f7a9"

        value = vault.detokenize(token)
        # → "sk-1234567890abcdef"
    """

    def __init__(self, session_ttl: int = 7200):
        """
        Initialize token vault.

        Args:
            session_ttl: Session time-to-live in seconds (default: 2 hours)
        """
        self.session_id = f"sess-{secrets.token_hex(8)}"
        self.session_created = time.time()
        self.session_ttl = session_ttl

        # Token → Plaintext mapping
        self.token_map: Dict[str, str] = {}

        # Hash(plaintext) → Token mapping (for deduplication)
        # Same secret always gets same token within a session
        self.value_to_token: Dict[str, str] = {}

        # Metadata for audit/debugging
        self.token_metadata: Dict[str, dict] = {}

    def _is_expired(self) -> bool:
        """Check if session has expired."""
        return (time.time() - self.session_created) > self.session_ttl

    def _hash_value(self, value: str) -> str:
        """Create stable hash of value for deduplication."""
        return hashlib.sha256(value.encode()).hexdigest()

    def tokenize(self, value: str, metadata: Optional[dict] = None) -> str:
        """
        Replace sensitive value with a token.

        Args:
            value: The secret value to tokenize
            metadata: Optional metadata (service, key name, etc.)

        Returns:
            Token string like "@token-a8f3d9e1b2c4f7a9"

        Raises:
            ValueError: If session has expired
        """
        if self._is_expired():
            raise ValueError(
                f"Token session {self.session_id} expired. Restart MCP server."
            )

        # Check if we've already tokenized this exact value
        # This ensures consistent tokens for duplicate values
        value_hash = self._hash_value(value)
        if value_hash in self.value_to_token:
            return self.value_to_token[value_hash]

        # Generate new cryptographically random token
        token_id = secrets.token_hex(8)  # 16 hex chars = 64 bits entropy
        token = f"@token-{token_id}"

        # Store mappings
        self.token_map[token] = value
        self.value_to_token[value_hash] = token

        # Store metadata for audit trail
        if metadata:
            self.token_metadata[token] = {
                **metadata,
                "created_at": datetime.now().isoformat(),
            }

        return token

    def detokenize(self, token: str) -> str:
        """
        Resolve token back to original value.

        Args:
            token: Token string like "@token-a8f3d9e1b2c4f7a9"

        Returns:
            Original secret value

        Raises:
            ValueError: If token not found or session expired
        """
        if self._is_expired():
            raise ValueError(
                f"Token session {self.session_id} expired. Restart MCP server."
            )

        if not token.startswith("@token-"):
            # Not a token, return as-is
            return token

        if token not in self.token_map:
            raise ValueError(f"Unknown token: {token}")

        return self.token_map[token]

    def detokenize_dict(self, data: dict) -> dict:
        """
        Recursively detokenize all tokens in a dict.

        Args:
            data: Dictionary potentially containing tokens

        Returns:
            Dictionary with all tokens replaced by values
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("@token-"):
                result[key] = self.detokenize(value)
            elif isinstance(value, dict):
                result[key] = self.detokenize_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.detokenize(v) if isinstance(v, str) and v.startswith("@token-") else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def detokenize_text(self, text: str) -> str:
        """
        Replace all tokens in a text string.

        Useful for .env files:
            API_KEY=@token-a8f3d9e1b2c4f7a9
            DB_PASSWORD=@token-b2c4f7a9c5d6e8f9

        Becomes:
            API_KEY=sk-1234567890abcdef
            DB_PASSWORD=supersecret123

        Args:
            text: Text containing tokens

        Returns:
            Text with tokens replaced by values
        """

        def replace_token(match):
            token = match.group(0)
            try:
                return self.detokenize(token)
            except ValueError:
                return token  # Keep unknown tokens as-is

        return re.sub(r"@token-[a-f0-9]{16}", replace_token, text)

    def get_stats(self) -> dict:
        """Get session statistics."""
        age = time.time() - self.session_created
        remaining = max(0, self.session_ttl - age)

        return {
            "session_id": self.session_id,
            "tokens_created": len(self.token_map),
            "unique_values": len(self.value_to_token),
            "session_age_seconds": int(age),
            "session_remaining_seconds": int(remaining),
            "is_expired": self._is_expired(),
        }

    def clear(self):
        """Clear all tokens (for security)."""
        self.token_map.clear()
        self.value_to_token.clear()
        self.token_metadata.clear()


# Global instance (created per MCP server process)
_token_vault: Optional[TokenVault] = None


def get_token_vault(ttl: Optional[int] = None) -> TokenVault:
    """
    Get or create the global token vault.

    Args:
        ttl: Optional session TTL in seconds (default from env or 7200)

    Returns:
        TokenVault instance
    """
    import os

    global _token_vault

    if ttl is None:
        ttl = int(os.getenv("VAULT_TOKEN_SESSION_TTL", "7200"))

    if _token_vault is None or _token_vault._is_expired():
        _token_vault = TokenVault(session_ttl=ttl)

    return _token_vault


def should_tokenize_value(key: str, value: str) -> bool:
    """
    Decide if a value should be tokenized.

    Non-sensitive values (ports, public URLs, etc.) can be sent plaintext.

    Args:
        key: Secret key name
        value: Secret value

    Returns:
        True if value should be tokenized
    """
    # Don't tokenize common non-sensitive config
    non_sensitive_keys = {
        "PORT",
        "HOST",
        "HOSTNAME",
        "ENVIRONMENT",
        "ENV",
        "DEBUG",
        "LOG_LEVEL",
        "TIMEZONE",
        "TZ",
    }

    if key.upper() in non_sensitive_keys:
        return False

    # Don't tokenize public URLs
    if value.startswith(("http://", "https://", "ftp://")):
        return False

    # Don't tokenize boolean values
    if value.lower() in ("true", "false", "yes", "no", "1", "0"):
        return False

    # Don't tokenize very short values (probably not secrets)
    if len(value) < 8:
        return False

    return True

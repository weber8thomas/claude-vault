"""HTTP client for HashiCorp Vault API interactions."""

import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class VaultResponse:
    """Structured response from Vault API."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    http_code: Optional[int] = None


class VaultClient:
    """Client for interacting with HashiCorp Vault KV v2 secrets engine."""

    def __init__(self, vault_addr: str, vault_token: str):
        """
        Initialize Vault client.

        Args:
            vault_addr: Vault server URL (e.g., https://vault.example.com)
            vault_token: Vault authentication token
        """
        self.vault_addr = vault_addr.rstrip('/')
        self.vault_token = vault_token
        self.session = requests.Session()
        self.session.headers.update({
            'X-Vault-Token': vault_token,
            'Content-Type': 'application/json'
        })
        self.timeout = 10  # seconds

    def lookup_token(self) -> VaultResponse:
        """
        Validate token and get metadata.

        Returns:
            VaultResponse with token metadata or error
        """
        url = f"{self.vault_addr}/v1/auth/token/lookup-self"
        try:
            response = self.session.post(url, timeout=self.timeout)

            if response.status_code == 200:
                return VaultResponse(success=True, data=response.json().get('data'), http_code=200)
            elif response.status_code == 403:
                return VaultResponse(success=False, error="Permission denied. Token may be invalid or lack required policies.", http_code=403)
            else:
                return VaultResponse(success=False, error=f"Unexpected HTTP {response.status_code}", http_code=response.status_code)

        except requests.ConnectionError:
            return VaultResponse(success=False, error=f"Cannot reach Vault at {self.vault_addr}. Check network connectivity.")
        except requests.Timeout:
            return VaultResponse(success=False, error="Vault request timed out. Server may be overloaded.")
        except Exception as e:
            return VaultResponse(success=False, error=f"Unexpected error: {str(e)}")

    def revoke_token(self) -> VaultResponse:
        """
        Revoke the current token.

        Returns:
            VaultResponse indicating success or failure
        """
        url = f"{self.vault_addr}/v1/auth/token/revoke-self"
        try:
            response = self.session.post(url, timeout=self.timeout)

            if response.status_code in [200, 204]:
                return VaultResponse(success=True, http_code=response.status_code)
            else:
                return VaultResponse(success=False, error=f"HTTP {response.status_code}", http_code=response.status_code)

        except Exception as e:
            return VaultResponse(success=False, error=f"Error revoking token: {str(e)}")

    def list_services(self) -> VaultResponse:
        """
        List all services under proxmox-services/.

        Returns:
            VaultResponse with list of service names or error
        """
        url = f"{self.vault_addr}/v1/secret/metadata/proxmox-services?list=true"
        try:
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                services = data.get('data', {}).get('keys', [])
                return VaultResponse(success=True, data={'services': services}, http_code=200)
            elif response.status_code == 404:
                return VaultResponse(success=True, data={'services': []}, http_code=200)  # No services yet
            else:
                return VaultResponse(success=False, error=f"HTTP {response.status_code}", http_code=response.status_code)

        except Exception as e:
            return VaultResponse(success=False, error=f"Error listing services: {str(e)}")

    def get_secret_metadata(self, service: str) -> VaultResponse:
        """
        Get metadata for a service (version, timestamps).

        Args:
            service: Service name

        Returns:
            VaultResponse with metadata or error
        """
        url = f"{self.vault_addr}/v1/secret/metadata/proxmox-services/{service}"
        try:
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 200:
                return VaultResponse(success=True, data=response.json().get('data'), http_code=200)
            elif response.status_code == 404:
                return VaultResponse(success=False, error=f"Service '{service}' not found in Vault", http_code=404)
            else:
                return VaultResponse(success=False, error=f"HTTP {response.status_code}", http_code=response.status_code)

        except Exception as e:
            return VaultResponse(success=False, error=f"Error getting metadata: {str(e)}")

    def get_secret(self, service: str) -> VaultResponse:
        """
        Get secret data for a service.

        Args:
            service: Service name

        Returns:
            VaultResponse with secret data or error
        """
        url = f"{self.vault_addr}/v1/secret/data/proxmox-services/{service}"
        try:
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                return VaultResponse(
                    success=True,
                    data={
                        'secrets': data.get('data', {}).get('data', {}),
                        'metadata': data.get('data', {}).get('metadata', {})
                    },
                    http_code=200
                )
            elif response.status_code == 404:
                return VaultResponse(success=False, error=f"Service '{service}' not found in Vault", http_code=404)
            else:
                return VaultResponse(success=False, error=f"HTTP {response.status_code}", http_code=response.status_code)

        except Exception as e:
            return VaultResponse(success=False, error=f"Error getting secret: {str(e)}")

    def write_secret(self, service: str, secrets: Dict[str, str]) -> VaultResponse:
        """
        Write or update secrets for a service.

        Args:
            service: Service name
            secrets: Dictionary of key-value pairs to write

        Returns:
            VaultResponse with version info or error
        """
        url = f"{self.vault_addr}/v1/secret/data/proxmox-services/{service}"
        payload = {"data": secrets}

        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)

            if response.status_code in [200, 204]:
                data = response.json() if response.status_code == 200 else {}
                version = data.get('data', {}).get('version', 'N/A')
                return VaultResponse(success=True, data={'version': version}, http_code=response.status_code)
            elif response.status_code == 403:
                return VaultResponse(success=False, error="Permission denied. Token may lack write permissions.", http_code=403)
            else:
                return VaultResponse(success=False, error=f"HTTP {response.status_code}", http_code=response.status_code)

        except Exception as e:
            return VaultResponse(success=False, error=f"Error writing secret: {str(e)}")

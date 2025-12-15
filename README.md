# Claude-Vault

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Vibe Coded](https://img.shields.io/badge/vibe--coded-with%20Claude-blueviolet)](https://claude.ai)

**Secure HashiCorp Vault management for Docker services with AI-assisted workflows**

Claude-Vault provides two complementary tools:
- **MCP Server** - Model Context Protocol integration for Claude Code AI assistance (recommended)
- **CLI** - Bash scripts for session-based Vault authentication and secret management

## Why This Exists

**The Problem:**
Managing many Docker/docker-compose services, each with their own `.env` files and hardcoded credentials scattered everywhere. Not scalable, not secure, not production-ready.

**The Goal:**
Migrate from non-production chaos (passwords in docker-compose files, untracked `.env` files) to a production-oriented HashiCorp Vault setup that's:
- **Cloud-compatible** - Works across infrastructure
- **AI-assisted** - Claude Code helps migrate services and manage secrets
- **Secure by default** - Human-in-the-loop validation via WebAuthn prevents unauthorized AI writes

**The Result:**
AI handles the tedious migration work (reading old configs, registering secrets), but **cannot make unauthorized changes** to production secrets without your biometric approval.

> **Note:** This entire project was built with Claude Code - designed through conversation, combining human intent with AI implementation.

## Features

### MCP Server (`packages/mcp-server/`)
- **Claude Code integration** - Expose Vault operations as AI tools
- **WebAuthn approval workflow** - Biometric confirmation (TouchID/Windows Hello) for secret writes
- **Prompt injection protection** - Human-in-the-loop checkpoints prevent AI from making unauthorized changes
- **Operation history** - Track approved and pending operations via web UI
- **Device management** - Register and manage WebAuthn devices (security keys, biometrics)

### CLI Tool (`packages/cli/`)
- **Session-based authentication** - OIDC + MFA with 60-minute token expiry
- **Zero persistent credentials** - Tokens stored only in memory for security
- **Comprehensive audit logging** - Complete operation trail for compliance
- **Input validation** - Prevents path traversal and command injection vulnerabilities
- **Service-oriented** - Designed for managing Docker service secrets

## Repository Structure

```
claude-vault/
├── packages/
│   ├── mcp-server/       # Python MCP server for Claude Code integration (recommended)
│   └── cli/              # Bash CLI scripts for Vault operations
└── docs/                 # Documentation
```

## Quick Start

### Option 1: MCP Server (AI-Assisted Management) - Recommended

**Installation:**
```bash
cd packages/mcp-server
pip install -e .
```

**Configure for Claude Code:**

Add to your project's `.mcp.json`:
```json
{
  "mcpServers": {
    "claude-vault": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "/path/to/claude-vault/packages/mcp-server",
        "claude-vault-mcp"
      ],
      "env": {
        "VAULT_ADDR": "https://vault.example.com"
      }
    }
  }
}
```

**Start approval server:**
```bash
vault-approve-server  # Starts on http://localhost:8091
```

Now Claude Code can help you manage secrets, with WebAuthn approval for write operations.

### Option 2: CLI Only (Manual Vault Management)

**Quick install (recommended):**
```bash
# Install latest release
curl -fsSL https://github.com/weber8thomas/claude-vault/releases/latest/download/install.sh | sudo bash

# Or install to ~/.local/bin (no sudo)
curl -fsSL https://github.com/weber8thomas/claude-vault/releases/latest/download/install.sh | PREFIX="$HOME/.local/bin" bash
```

**Install specific version:**
```bash
VERSION="v1.0.0"
curl -fsSL "https://github.com/weber8thomas/claude-vault/releases/download/${VERSION}/install.sh" | sudo bash
```

**Manual installation:**
```bash
# Clone from source
git clone https://github.com/weber8thomas/claude-vault.git
cd claude-vault
sudo ./install.sh
```

**Authentication:**
```bash
source claude-vault login
```

**Usage:**
```bash
claude-vault list                  # List all services
claude-vault get esphome           # Get secret values
claude-vault set myapp KEY=val     # Register secrets
claude-vault inject authentik      # Inject to .env file
```

**Available commands:**
- `login` - Authenticate via OIDC
- `status` - Check session status
- `logout` - Revoke token
- `list` - List services/secrets
- `get` - Get secret values
- `set` - Create/update secrets
- `inject` - Inject secrets to .env file

## WebAuthn Approval Workflow

<table>
  <tr>
    <td width="50%">
      <img src="docs/images/home-page.png" alt="Home Page" />
      <p align="center"><strong>1. Home Dashboard</strong></p>
      <p><em>Monitor server status, view pending approvals, and manage registered WebAuthn devices.</em></p>
    </td>
    <td width="50%">
      <img src="docs/images/approval-page.png" alt="Approval Page" />
      <p align="center"><strong>2. Review Operation</strong></p>
      <p><em>Examine the service name, operation type, and preview secret values before approving.</em></p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="docs/images/approval-page-touchid.png" alt="TouchID Prompt" />
      <p align="center"><strong>3. Biometric Authentication</strong></p>
      <p><em>Confirm with TouchID, Windows Hello, or hardware security key for cryptographic verification.</em></p>
    </td>
    <td width="50%">
      <img src="docs/images/approval-page-success.png" alt="Success Message" />
      <p align="center"><strong>4. Approval Complete</strong></p>
      <p><em>Success confirmation with audit trail. The operation is now processed and logged.</em></p>
    </td>
  </tr>
</table>

## Security Considerations

**AI can read secrets** - This is necessary for migration workflows. AI helps you:
- Migrate from docker-compose/.env files to Vault
- Generate .env files from Vault secrets
- Organize and structure your secrets

**AI cannot write secrets** - WebAuthn approval required for all write operations.

**For ultra-sensitive production secrets:**
- Use the CLI directly without AI assistance
- Use a hybrid approach (AI for structure, manual for values)
- See [Security FAQ](packages/mcp-server/WEBAUTHN_SETUP.md#security-faq) for details

## Documentation

### MCP Server
- [MCP Integration](docs/MCP.md) - Model Context Protocol server setup
- [WebAuthn Setup](packages/mcp-server/WEBAUTHN_SETUP.md) - Security architecture & FAQ
- [MCP Server README](packages/mcp-server/README.md) - MCP package details

### CLI Tool
- [Setup Guide](docs/SETUP.md) - Complete installation and configuration
- [Quick Start](docs/QUICK_START.md) - CLI reference guide
- [CLI README](packages/cli/README.md) - CLI package details

## Releases

Releases are automatically created when new version tags are pushed. Each release includes:

- `install.sh` - Standalone installer (downloads latest from GitHub)
- `claude-vault-vX.X.X-linux-amd64.tar.gz` - Full tarball archive
- `claude-vault-vX.X.X-linux-amd64.zip` - Full ZIP archive
- `checksums.txt` - SHA256 checksums for verification

**One-command installation from release:**
```bash
curl -fsSL https://github.com/weber8thomas/claude-vault/releases/latest/download/install.sh | sudo bash
```

**To create a new release:**
```bash
git tag -a v1.1.0 -m "Release version 1.1.0"
git push origin v1.1.0
```

GitHub Actions will automatically build and publish the release.

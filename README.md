# Claude-Vault

Session-based CLI for HashiCorp Vault with AI assistant integration.

## Features

• Session-based authentication via OIDC + MFA (60-minute token expiry)
• No persistent credentials (tokens stored only in memory)
• Manual confirmation checkpoints (protection against prompt injection)
• Comprehensive audit logging (complete operation trail)
• Input validation (prevents path traversal and command injection)
• AI assistant friendly (designed for Claude Code integration)

## Quick Start

### Installation
```bash
cd ./claude-vault
sudo ./install.sh
```

### Authentication
```bash
source claude-vault login
```

### Usage
```bash
claude-vault list                  # List all services
claude-vault get esphome           # Get secret values
claude-vault set myapp KEY=val     # Register secrets
claude-vault inject authentik      # Inject to .env file
```

## Documentation

- [Setup Guide](docs/SETUP.md) - Complete installation and configuration
- [Quick Start](docs/QUICK_START.md) - AI assistant reference
- [MCP Integration](docs/MCP.md) - Model Context Protocol server setup

## Commands

- `login` - Authenticate via OIDC
- `status` - Check session status
- `logout` - Revoke token
- `list` - List services/secrets
- `get` - Get secret values
- `set` - Create/update secrets
- `inject` - Inject secrets to .env file

## MCP Server

This repository also includes an MCP (Model Context Protocol) server for Vault integration with Claude Code. See [mcp_vault/](mcp_vault/) for details.

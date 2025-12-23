# MCP-Vault

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)

**AI-assisted HashiCorp Vault management with zero secrets sent to AI providers**

🔐 **Your secrets never leave your infrastructure** - Any MCP-compatible AI (Claude, Gemini, Qwen, OpenAI) can help you manage Vault through a local MCP server that keeps all sensitive data on your machine. The AI sees structure and workflow, never actual secrets.

🤖 **Works with ANY MCP client:** Claude Code, Gemini CLI, OpenAI Agents, Qwen-Agent, BoltAI, Chatbox, and [469+ MCP clients](https://modelcontextprotocol.io/clients)

MCP-Vault provides two complementary tools:
- **🤖 MCP Server** - Model Context Protocol integration for AI assistance (works with any MCP client)
- **💻 CLI** - Bash scripts for session-based Vault authentication and secret management

## Why This Exists

> **Personal Context:** This project was born from managing a Proxmox homelab with 20+ services, each with scattered credentials that needed proper centralized secret management and a way to clean up the infrastructure chaos.

**The Problem:**
Managing many Docker/docker-compose services, each with their own `.env` files and hardcoded credentials scattered everywhere. Not scalable, not secure, not production-ready.

**The Goal:**
Migrate from non-production chaos (passwords in docker-compose files, untracked `.env` files) to a production-oriented HashiCorp Vault setup meeting these requirements:
- **Cloud-compatible** - Must work across infrastructure
- **AI-assisted** - Need your AI agent to help migrate services and manage secrets
- **Secure by default** - Require human-in-the-loop validation via WebAuthn to prevent unauthorized AI writes

**The Result:**
AI handles the tedious migration work (reading old configs, registering secrets), but **cannot make unauthorized changes** to production secrets without your biometric approval.

> **Note:** This entire project was built with Claude Code - designed through conversation, combining human intent with AI implementation.

## 🌟 Key Features

### How It Works

```
┌─────────────────┐
│   You ask AI    │  "Scan my .env files and migrate to Vault"
│  (MCP Client)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   MCP Server    │  → Tokenizes secrets: PASSWORD="super_secret"
│  (Your Machine) │     becomes PASSWORD="@token-abc123"
└────────┬────────┘  → AI never sees real values
         │
         ├──────────────────────────────────────┐
         │                                      │
         ▼                                      ▼
┌─────────────────┐                   ┌─────────────────┐
│  AI Provider    │                   │  Approval Page  │
│    (Remote)     │                   │  (Your Browser) │
└─────────────────┘                   └────────┬────────┘
Sees: @token-abc123                            │
Never sees: super_secret              Approve with TouchID
                                               │
         ┌─────────────────────────────────────┘
         ▼
┌─────────────────┐
│ HashiCorp Vault │  ✓ Secrets stored securely
│  (Your Infra)   │  ✓ Changes approved by you
└─────────────────┘  ✓ Full audit trail
```

### Core Capabilities

**🔒 Zero-Knowledge AI** - Secrets tokenized before reaching the AI provider; MCP server runs locally, real values never leave your infrastructure

**🤖 AI-Assisted Migration** - Natural language commands to scan `.env` files, docker-compose configs, and migrate secrets to Vault automatically

**🛡️ Human-in-the-Loop Security** - WebAuthn biometric approval (TouchID/Windows Hello/YubiKey) required for all write operations

**💻 Production-Ready** - OIDC+MFA authentication, comprehensive audit trails, operation history tracking (100 ops, permanent retention)

## 🎯 Use Cases

### Primary: Migrate Docker Services to Vault
**Problem:** You have 20+ docker-compose services with hardcoded passwords and scattered `.env` files.

**Complete Workflow:**

1. **You:** "Scan the docker-compose.yml in /services/jellyfin and migrate secrets to Vault"

2. **AI:** Calls `vault_scan_compose(service="jellyfin")`
   - MCP server reads your docker-compose.yml
   - Detects secrets (passwords, API keys, etc.)
   - **Tokenizes them**: `JELLYFIN_PASSWORD="@token-a8f3d9e1"`
   - Creates operation requiring WebAuthn approval

3. **AI:** Shows you:
   ```
   📋 Found 5 secrets in jellyfin/docker-compose.yml:
   - JELLYFIN_PASSWORD: @token-a8f3d9e1
   - API_KEY: @token-b2c4f7a9
   - DB_PASSWORD: @token-c5d6e8f9

   ⚠️  Approve at: http://localhost:8091/approve/xyz123
   ```

4. **You:** Open approval URL in browser
   - **See real values** (not tokens) in approval page
   - Review: service name, operation type, all secrets
   - Click "Approve with WebAuthn"
   - Authenticate with TouchID/Windows Hello

5. **AI:** After approval, calls `vault_set()`
   - Registers secrets in Vault at `secret/proxmox-services/jellyfin`
   - Generates `.env.example` with `<REDACTED>` placeholders
   - Creates documentation

**Result:** Secrets migrated to Vault, old .env file documented but can be deleted

### Other Common Tasks

**Audit and Rotate Secrets**

Need to find all services using a specific database password? Ask your AI naturally:
```
"Which services are using the old database password?"
"Help me rotate the database credentials for all affected services"
```
The AI reads Vault through the MCP server to help you understand your secret landscape, but any changes require your biometric approval.

**Generate Service Configurations**

Setting up a new service that needs 10+ environment variables from Vault? Let your AI handle it:
```
"Create a .env file for my new API service using secrets from Vault"
```
The MCP server injects real values locally - AI never sees them, just orchestrates the workflow.

**Infrastructure as Code**

Version-control your service structure without exposing secrets:
- Commit `.env.example` files with `<REDACTED>` placeholders to git
- Keep actual secrets in Vault
- AI helps generate example files from your existing setup

## 📦 Installation

### Prerequisites
- **HashiCorp Vault** server with OIDC authentication configured
- **Python 3.12+** (for MCP server)
- **MCP-compatible AI client** (Claude Code, Gemini CLI, OpenAI Agents, etc.)
- Modern browser with WebAuthn support (Chrome, Firefox, Safari, Edge)

### Installation Options

#### Option A: MCP Server from PyPI (Recommended - No Repo Clone Needed!)
```bash
# Install directly from PyPI
pip install mcp-vault

# Or using uvx (recommended - auto-managed environment)
uvx --from mcp-vault vault-approve-server --help
```

**Add to your MCP client** - Configure in `.mcp.json`:
```json
{
  "mcpServers": {
    "mcp-vault": {
      "command": "uvx",
      "args": ["mcp-vault"],
      "env": {
        "VAULT_ADDR": "https://vault.example.com",
        "VAULT_TOKEN": "${VAULT_TOKEN}",
        "VAULT_SECURITY_MODE": "tokenized"
      }
    }
  }
}
```

**Compatible with:**
- Claude Code / Claude Desktop
- Gemini CLI (`gemini-cli --mcp-server mcp-vault`)
- OpenAI Agents SDK
- BoltAI, Chatbox, and [all MCP clients](https://modelcontextprotocol.io/clients)

**Find this server on MCP directories:**
- [Smithery.ai](https://smithery.ai) - Official Anthropic-maintained catalog
- [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers) - Curated community list (high visibility)
- [mcp.so](https://mcp.so) - Community platform with 17K+ servers

#### Option B: CLI Only (For Direct Vault Management)
```bash
# Quick install from release
curl -fsSL https://github.com/weber8thomas/mcp-vault/releases/latest/download/install.sh | sudo bash

# Or install to ~/.local/bin (no sudo)
curl -fsSL https://github.com/weber8thomas/mcp-vault/releases/latest/download/install.sh | PREFIX="$HOME/.local/bin" bash

# Verify installation
vault-session --help
```

#### Option C: Development Installation (From Source)
```bash
# Clone repository
git clone https://github.com/weber8thomas/mcp-vault.git
cd mcp-vault

# Install MCP server in editable mode
cd packages/mcp-server
pip install -e .

# Install CLI tools (optional)
cd ../..
sudo ./install.sh

# Verify installations
vault-approve-server --help
vault-session --help
```

## Repository Structure

```
mcp-vault/
├── packages/
│   ├── mcp-server/       # Python MCP server for any MCP client (recommended)
│   └── cli/              # Bash CLI scripts for Vault operations
└── docs/                 # Documentation
```

## 🚀 Quick Start

### Complete MCP Server Workflow (AI-Assisted Management)

*Assumes you've installed the MCP server (see Installation section above)*

#### Step 1: Start the Approval Server
**The approval server must be running before using the MCP server:**
```bash
vault-approve-server
```

This starts a web server on **http://localhost:8091** where you'll:
- Register your WebAuthn device (TouchID/Windows Hello/YubiKey)
- Review and approve AI-requested operations
- View operation history and pending approvals

**Keep this running in a separate terminal while using your MCP client.**

#### Step 2: Authenticate to Vault
In another terminal, authenticate your session:
```bash
source vault-session login
```

This will:
1. Open your Vault OIDC login page in browser
2. Prompt for MFA authentication (e.g., Authentik)
3. Set `VAULT_TOKEN` and `VAULT_TOKEN_EXPIRY` in your environment
4. Session lasts 60 minutes (configurable)

**Verify authentication:**
```bash
vault-session status
```

#### Step 3: Configure Your MCP Client
Add to your `.mcp.json`:
```json
{
  "mcpServers": {
    "mcp-vault": {
      "command": "uvx",
      "args": ["mcp-vault"],
      "env": {
        "VAULT_ADDR": "https://vault.example.com",
        "VAULT_TOKEN": "${VAULT_TOKEN}",
        "VAULT_SECURITY_MODE": "tokenized"
      }
    }
  }
}
```

**Important:** The MCP server inherits `VAULT_TOKEN` from your shell environment.

> **Note:** If you installed from source (Option C), use the full path: `"args": ["--from", "/path/to/mcp-vault/packages/mcp-server", "mcp-vault"]`

**Production Deployment (Nginx/HTTPS):**
If you're using nginx reverse proxy with HTTPS, configure the approval server domain:
```json
{
  "mcpServers": {
    "mcp-vault": {
      "env": {
        "VAULT_ADDR": "https://vault.example.com",
        "VAULT_TOKEN": "${VAULT_TOKEN}",
        "VAULT_SECURITY_MODE": "tokenized",
        "VAULT_APPROVE_DOMAIN": "vault-approve.yourdomain.com",
        "VAULT_APPROVE_ORIGIN": "https://vault-approve.yourdomain.com"
      }
    }
  }
}
```
See [WEBAUTHN_SETUP.md](packages/mcp-server/WEBAUTHN_SETUP.md#production-deployment-with-nginxhttps) for full nginx configuration.

**For other MCP clients:**
- **Gemini CLI:** `gemini-cli --mcp-server mcp-vault`
- **OpenAI Agents:** Configure in agents config file
- **BoltAI/Chatbox:** Add server in app settings

#### Step 4: Register WebAuthn Device
1. Open http://localhost:8091 in your browser
2. Click **"Register Authenticator"**
3. Follow prompts to register your biometric device
4. You're ready to use your AI assistant with secure approvals!

#### Step 5: Use with Your AI Assistant
Now ask your AI to help manage your secrets:
```
"Scan my docker-compose.yml for secrets and help me migrate them to Vault"
```

When the AI needs to write secrets, it will:
1. Show you a tokenized preview (secrets replaced with `@token-xxx`)
2. Provide an approval URL: http://localhost:8091/approve/{operation-id}
3. Wait for your WebAuthn approval
4. Process the operation after you approve

### CLI Workflow (Manual Vault Management)

*Assumes you've installed the CLI (see Installation section above)*

#### Step 1: Authenticate to Vault
```bash
source vault-session login
```

This will:
1. Open your Vault OIDC login in browser
2. Prompt for MFA (e.g., Authentik)
3. Set `VAULT_TOKEN` in your environment
4. Session lasts 60 minutes

#### Step 2: Verify Session
```bash
vault-session status
```

Expected output:
```
✅ Vault Session Active
User: your-username
Policies: default, homelab-services
Time Remaining: 59m 30s
```

#### Step 3: Use CLI Commands

**List all services:**
```bash
vault-session list
```

**Get secrets for a service:**
```bash
vault-session get jellyfin
# Returns: API_KEY, DB_PASSWORD, etc.
```

**Register new secrets:**
```bash
vault-session set myapp API_KEY=abc123 DB_PASS=secret
```

**Inject secrets to .env file:**
```bash
vault-session inject myapp
# Creates myapp/.env with real values from Vault
```

**Logout (revoke token):**
```bash
vault-session logout
```

#### Available Commands
| Command | Description | Example |
|---------|-------------|---------|
| `login` | Authenticate via OIDC+MFA | `source vault-session login` |
| `status` | Check session validity | `vault-session status` |
| `logout` | Revoke Vault token | `vault-session logout` |
| `list` | List services/secrets | `vault-session list` or `vault-session list myapp` |
| `get` | Get secret values | `vault-session get myapp` |
| `set` | Create/update secrets | `vault-session set myapp KEY=value` |
| `inject` | Write secrets to .env | `vault-session inject myapp` |

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

## 🔐 Security Architecture

### How Tokenization Works
**Your secrets are NEVER sent to Claude's API:**

1. **Scanning phase** (when AI needs to see secrets):
   ```
   Original: DATABASE_PASSWORD="super_secret_123"
   Sent to AI: DATABASE_PASSWORD="@token-a8f3d9e1b2c4"
   ```
   - MCP server tokenizes values before sending to AI
   - Tokens are temporary and session-specific (2 hour expiry)
   - AI sees structure and keys, never actual secrets

2. **Writing phase** (when AI wants to save secrets):
   ```
   AI sends: vault_set(service="myapp", secrets={"KEY": "value"})
   Your action: Review on http://localhost:8091 and approve with TouchID
   Result: Only written to Vault after your biometric confirmation
   ```

### Security Model

| Operation | AI Sees | Human Approval | Notes |
|-----------|---------|----------------|-------|
| **List services** | Service names only | ❌ Not required | Safe metadata |
| **Read secrets** | Tokens like `@token-xxx` | ❌ Not required | Values stay in MCP server |
| **Write secrets** | Structure and keys | ✅ **WebAuthn required** | You review real values in browser |
| **Scan configs** | Tokens for detected secrets | ✅ **WebAuthn required** | Tokenization prevents leakage |
| **Inject to .env** | File path only | ❌ Not required | Real values injected locally |

### Trust Boundaries

```
┌──────────────────┐
│   Claude API     │  ← Sees: Tokens, structure, metadata
│  (Cloud/Remote)  │     Never sees: Actual secret values
└────────┬─────────┘
         │ MCP Protocol
         │ (only tokens sent)
         │
┌────────▼─────────┐
│   MCP Server     │  ← Has: Full access to secrets
│ (Your Machine)   │     Enforces: WebAuthn approval for writes
└────────┬─────────┘
         │ Vault API
         │ (with your token)
         │
┌────────▼─────────┐
│  HashiCorp Vault │  ← Stores: All secrets encrypted
│ (Your Infra)     │     Access: Controlled by your OIDC/MFA
└──────────────────┘
```

### For Ultra-Sensitive Secrets

If you have secrets that should never be accessible to AI tooling at all:

1. **Use CLI directly** - Bypass MCP server entirely:
   ```bash
   source vault-session login
   vault-session set prod-db MASTER_KEY="..."
   ```

2. **Hybrid approach** - Let AI structure, you provide values:
   ```
   AI: "I'll set up the Vault structure for your database service"
   You: Manually provide sensitive values via CLI
   ```

3. **Separate Vault paths** - Keep ultra-sensitive secrets in a different path that the MCP server can't access

See [Security FAQ](packages/mcp-server/WEBAUTHN_SETUP.md#security-faq) for detailed threat model analysis.

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
- `vault-session-vX.X.X-linux-amd64.tar.gz` - Full tarball archive
- `vault-session-vX.X.X-linux-amd64.zip` - Full ZIP archive
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

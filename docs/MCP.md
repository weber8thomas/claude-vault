# Claude Code MCP Integration Guide

This guide explains how to use the MCP-Vault server with Claude Code CLI for AI-assisted secret management.

## What is MCP?

**Model Context Protocol (MCP)** is Anthropic's standard for exposing tools to Claude. The mcp-vault server exposes 7 Vault operations as tools that Claude Code can use automatically:

- `vault_login` - Authentication guidance
- `vault_status` - Session validation
- `vault_logout` - Token revocation
- `vault_list` - List services/secrets
- `vault_get` - Retrieve secret values
- `vault_set` - Create/update secrets (with human confirmation)
- `vault_inject` - Generate .env files

## Setup (One-time)

### 1. MCP Server Configuration

The MCP server is **already configured** in this repository via `.mcp.json`:

```bash
# Verify it's configured
claude mcp get mcp-vault
```

You should see:
```
mcp-vault:
  Scope: Project config (shared via .mcp.json)
  Status: ✓ Connected
  Type: stdio
  Command: uvx
  Args: --from /workspace/proxmox-services/mcp-vault mcp-vault
  Environment:
    VAULT_ADDR=https://vault.laboiteaframboises.duckdns.org
```

### 2. For New Team Members

If you're setting up on a fresh system:

```bash
cd /workspace/proxmox-services

# The .mcp.json file should already exist (committed to git)
# Claude Code will auto-detect it

# Verify the server is available
claude mcp get mcp-vault
```

## Daily Usage

### Step 1: Authenticate to Vault

**Before using vault tools**, authenticate to get a session token:

```bash
# This opens your browser for OIDC + MFA authentication
source claude-vault login
```

**Why `source`?** The login command exports `VAULT_TOKEN` to your environment. Using `source` ensures the token is available in your current shell, which Claude Code inherits.

Verify your session:
```bash
claude-vault status
```

Expected output:
```
✅ Active Vault session
User: your-username
Token expires: 2024-XX-XX XX:XX:XX (59 minutes remaining)
```

### Step 2: Use Vault Tools in Claude Code

The MCP server is now active. Claude can automatically use vault tools when relevant:

**Example conversations:**

```
You: Claude, list all services in Vault
→ Uses vault_list tool

You: Claude, what's the wifi password for esphome?
→ Uses vault_get(service="esphome", key="wifi_password")

You: Claude, register these secrets for my new app:
     DB_HOST="localhost"
     DB_USER="admin"
     DB_PASS="secret123"
→ Uses vault_set tool, prompts you to confirm by typing "yes"

You: Claude, inject the authentik secrets to its .env file
→ Uses vault_inject tool
```

### Step 3: View Available Tools

Type `/mcp` in Claude Code to see all available MCP servers and tools:

```
/mcp
```

This shows:
- All configured MCP servers
- Connection status
- Available tools per server

## Security Model

### Human Confirmation Required

When Claude uses `vault_set` to write secrets, **you must confirm**:

```
⚠️  SECURITY CHECKPOINT - MANUAL VALIDATION REQUIRED

You are about to write secrets to Vault:
  Service: myapp
  Action: CREATE
  Path: secret/proxmox-services/myapp

Secrets to be written:
  + DB_HOST
  + DB_USER
  + DB_PASS

⚠️  DANGEROUS PATTERNS DETECTED:
  - DB_PASS contains: special characters

Type 'yes' to proceed, or anything else to abort:
```

Type `yes` to proceed, or anything else to abort.

### Session Expiry

Sessions are valid for **60 minutes**:

- After 60 minutes, tools will return "Session expired"
- Re-authenticate: `source claude-vault login`
- MCP server automatically reconnects with new token

### Audit Logging

All operations are logged to `.claude-vault-audit.log`:

```bash
# View recent operations
tail -20 .claude-vault-audit.log
```

Format:
```
[2024-XX-XX XX:XX:XX] USER=mcp-server ACTION=CONFIRMED SERVICE=myapp DETAILS=Wrote 3 secrets
```

## Troubleshooting

### "No Vault session found"

**Cause:** You haven't authenticated yet

**Solution:**
```bash
source claude-vault login
```

### "Session expired"

**Cause:** 60-minute TTL exceeded

**Solution:**
```bash
source claude-vault login
# MCP server automatically reconnects
```

### "MCP server not connected"

**Cause:** Configuration issue

**Solution:**
```bash
# 1. Check if .mcp.json exists
ls -la /workspace/proxmox-services/.mcp.json

# 2. Verify MCP server status
claude mcp get mcp-vault

# 3. If disconnected, check you're in the right directory
cd /workspace/proxmox-services
```

### "Permission denied" (HTTP 403)

**Cause:** Your Vault token lacks required policies or the policy has incorrect capabilities

**Common Issue:** The `auth/token/lookup-self` endpoint requires **`update`** capability (for POST requests), not `read`.

**Solution:**

1. **Verify your Vault policy includes:**
   ```hcl
   # Allow token self-lookup for status checks
   # CRITICAL: Must use "update" capability, not "read"
   path "auth/token/lookup-self" {
     capabilities = ["update"]
   }

   # Allow reading and managing homelab service secrets
   path "secret/data/proxmox-services/*" {
     capabilities = ["read", "list", "update", "create"]
   }

   # Allow listing secret metadata
   path "secret/metadata/proxmox-services/*" {
     capabilities = ["read", "list"]
   }
   ```

2. **Update the policy in Vault** (requires admin access)
   - Changes take effect immediately for existing tokens
   - No need to re-authenticate after policy updates

3. **Verify your token has the `homelab-services` policy:**
   ```bash
   claude-vault status
   ```

See [CLAUDE_VAULT_SETUP.md](./CLAUDE_VAULT_SETUP.md#prerequisites) for complete policy requirements.

### Tools not appearing

**Check:**
1. Type `/mcp` to see if mcp-vault is listed
2. Verify connection status: `claude mcp get mcp-vault`
3. Ensure you're in `/workspace/proxmox-services` directory
4. Try removing and re-adding:
   ```bash
   claude mcp remove mcp-vault -s project
   claude mcp add --transport stdio mcp-vault --scope project \
     --env VAULT_ADDR=https://vault.laboiteaframboises.duckdns.org \
     -- uvx --from /workspace/proxmox-services/mcp-vault mcp-vault
   ```

## How It Works

### Architecture

```
┌─────────────────┐
│  Claude Code    │
│  (you are here) │
└────────┬────────┘
         │ Uses MCP tools
         ▼
┌─────────────────┐
│  MCP-Vault      │ Reads VAULT_TOKEN
│  Server         │ from environment
└────────┬────────┘
         │ HTTP API
         ▼
┌─────────────────┐
│  HashiCorp      │
│  Vault          │ OIDC + MFA
└────────┬────────┘
         │
    Your browser
```

### Data Flow

1. **Authentication (once per session):**
   - You run: `source claude-vault login`
   - Browser opens → OIDC → Authentik → MFA
   - Token stored in `VAULT_TOKEN` environment variable
   - Expiry stored in `VAULT_TOKEN_EXPIRY`

2. **Using tools (automated by Claude):**
   - You ask Claude to interact with secrets
   - Claude calls MCP tool (e.g., `vault_get`)
   - MCP server reads `VAULT_TOKEN` from environment
   - Makes HTTP request to Vault API
   - Returns result to Claude
   - Claude uses result in response

3. **Write operations (human-in-the-loop):**
   - Claude calls `vault_set` tool
   - MCP server validates inputs
   - Displays security checkpoint
   - **Waits for you to type "yes"**
   - Only proceeds if confirmed
   - Logs operation to audit file

### Security Guarantees

✅ **No persistent credentials** - Tokens in memory only (environment variables)
✅ **Short-lived sessions** - 60-minute expiry enforced
✅ **Human confirmation** - Write operations require manual approval
✅ **Input validation** - Service/key names validated, dangerous patterns detected
✅ **Audit trail** - All operations logged with timestamp and details
✅ **MFA protected** - Initial authentication requires Authentik MFA

## Configuration Reference

### .mcp.json Structure

```json
{
  "mcpServers": {
    "mcp-vault": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "/workspace/proxmox-services/mcp-vault",
        "mcp-vault"
      ],
      "env": {
        "VAULT_ADDR": "https://vault.laboiteaframboises.duckdns.org"
      }
    }
  }
}
```

**Key fields:**
- `type`: "stdio" (MCP server uses stdin/stdout for communication)
- `command`: "uvx" (Python package runner by Astral)
- `args`: Path to mcp-vault package
- `env.VAULT_ADDR`: Public Vault URL (not sensitive, safe to commit)

**Not in config:**
- `VAULT_TOKEN` - Stored in shell environment, inherited by MCP server
- `VAULT_TOKEN_EXPIRY` - Also in environment

### Scope Levels

MCP servers can be configured at three scopes:

1. **Project** (this repository): `.mcp.json` in project root
   - Shared with team via git
   - Auto-detected by Claude Code when in this directory

2. **Local**: `~/.claude.json` (per-project, per-user)
   - Private configuration
   - Not shared with team

3. **User**: `~/.config/claude/config.json`
   - Available across all projects
   - User-wide configuration

**We use project scope** so all team members get the same MCP configuration automatically.

## Advanced Usage

### Testing Tools Manually

Use MCP Inspector for debugging:

```bash
npx @modelcontextprotocol/inspector uvx --from /workspace/proxmox-services/mcp-vault mcp-vault
```

This opens a web UI where you can:
- See all available tools
- Test tools with custom inputs
- View raw JSON responses
- Debug connection issues

### Developing New Tools

See `/workspace/proxmox-services/mcp-vault/README.md` for developer documentation.

### Environment Variables

The MCP server reads:

- `VAULT_ADDR` - Vault server URL (from .mcp.json env)
- `VAULT_TOKEN` - Session token (from `source claude-vault login`)
- `VAULT_TOKEN_EXPIRY` - Unix timestamp (from `source claude-vault login`)

To debug:
```bash
echo "VAULT_ADDR: $VAULT_ADDR"
echo "VAULT_TOKEN: ${VAULT_TOKEN:0:10}..." # First 10 chars only
echo "VAULT_TOKEN_EXPIRY: $VAULT_TOKEN_EXPIRY"
```

## See Also

- [Vault Quick Start Guide](./VAULT_QUICK_START.md) - Basic claude-vault commands
- [MCP-Vault README](../mcp-vault/README.md) - Full server documentation
- [Claude Code Docs](https://docs.claude.ai/claude-code) - Official Claude Code documentation

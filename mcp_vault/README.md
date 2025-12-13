# MCP-Vault

Model Context Protocol (MCP) server for HashiCorp Vault secret management via claude-vault.

This MCP server exposes Vault operations as tools that Claude Code can use for AI-assisted secret management, while maintaining the existing security model with human confirmation for write operations.

## Features

- ✅ **7 MCP Tools**: Complete Vault operations (login, status, logout, list, get, set, inject)
- 🔐 **Security-First**: Human confirmation required for write operations
- 📝 **Audit Logging**: All operations logged to `.claude-vault-audit.log`
- ⏱️ **Session-Based**: 60-minute token expiry, no persistent credentials
- 🛡️ **Input Validation**: Prevents injection attacks and path traversal
- 🔍 **Pattern Detection**: Scans for dangerous patterns in secret values

## Architecture

```
User authenticates → VAULT_TOKEN exported → MCP server reads env → Claude uses tools
```

**Security Model:**
1. Human authenticates via OIDC + MFA (`source claude-vault login`)
2. Token stored in environment variables (memory only, 60 min TTL)
3. MCP server reads token from environment
4. Write operations require human to type "yes"
5. All operations audited

## Quick Start

### 1. Installation

```bash
cd /workspace/proxmox-services/mcp-vault

# Install in development mode
pip install -e .

# Or install from PyPI (when published)
pip install mcp-vault
```

### 2. Configure MCP Server (One-time)

The MCP server is already configured in this repository via `.mcp.json` (project scope):

```bash
# Verify MCP server is configured
claude mcp get mcp-vault

# Should show: Status: ✓ Connected
```

**For new team members or fresh installs:**

```bash
cd /workspace/proxmox-services

# Add MCP server with project scope
claude mcp add --transport stdio mcp-vault --scope project \
  --env VAULT_ADDR=https://vault.laboiteaframboises.duckdns.org \
  -- uvx --from /workspace/proxmox-services/mcp-vault mcp-vault
```

### 3. Authenticate to Vault (Daily)

```bash
# Authenticate (opens browser for OIDC + MFA)
source claude-vault login

# Verify session (shows token expiry time)
claude-vault status
```

**Session Management:**
- Sessions are valid for 60 minutes
- VAULT_TOKEN is stored in environment variables (memory only)
- Claude Code inherits the token from your current shell
- If session expires: Re-authenticate with `source claude-vault login`

### 4. Use Vault Tools in Claude Code

The MCP server exposes 7 tools that Claude can use automatically:

```
# Ask Claude to interact with Vault:
Claude, list all services in Vault
Claude, get the wifi_ssid secret for esphome
Claude, register DB credentials for myapp: DB_USER="admin" DB_PASS="secret"
Claude, inject esphome secrets to .env file
```

**Available via `/mcp` command:**
- Type `/mcp` in Claude Code to see all available MCP servers and tools
- Tools appear automatically in Claude's context when relevant

## Available Tools

### Authentication

**`vault_login`** - Guide user through OIDC authentication
- Provides instructions for `source claude-vault login`
- Cannot directly update environment (requires MCP restart)

**`vault_status`** - Check session validity
- Shows user, policies, time remaining
- Validates token with Vault

**`vault_logout`** - Revoke token
- Invalidates session in Vault
- Provides cleanup instructions

### Read Operations

**`vault_list`** - List services or secrets
- No arguments: Lists all services
- With `service`: Lists secret keys (names only)

**`vault_get`** - Retrieve secret values
- Required: `service`
- Optional: `key` (specific secret)
- ⚠️ Returns actual secret values

### Write Operations

**`vault_set`** - Create or update secrets
- Required: `service`, `secrets` (dict)
- Optional: `dry_run` (boolean)
- **Requires human confirmation** (must type "yes")
- Validates inputs, detects dangerous patterns
- Logs to audit file

### Injection

**`vault_inject`** - Generate .env or secrets.yaml
- Required: `service`
- Optional: `format` (auto/env/yaml)
- Backs up existing files
- Calls existing `inject-secrets.sh` script

## Security Features

### Input Validation

- **Service names**: `^[a-zA-Z0-9_-]{1,64}$`
- **Key names**: `^[a-zA-Z0-9_-]{1,128}$`
- **Value size**: Max 8KB
- **No path traversal**: Rejects `..`, `/`

### Dangerous Pattern Detection

Scans secret values for:
- Command substitution: `$(...)`, backticks
- Shell operators: `&&`, `||`, `;`
- Variable expansion: `${...}`
- Control characters: newlines, carriage returns

### Confirmation Checkpoint

For `vault_set`, displays:
```
⚠️  SECURITY CHECKPOINT - MANUAL VALIDATION REQUIRED

You are about to write secrets to Vault:
  Service: myapp
  Action: CREATE
  Path: secret/proxmox-services/myapp

Secrets to be written:
  + DB_PASSWORD
  + API_KEY

Type 'yes' to proceed, or anything else to abort:
```

Claude MUST wait for human response - cannot automatically confirm.

### Audit Logging

Format: `[timestamp] USER=mcp-server ACTION=X SERVICE=Y DETAILS=Z`

Logged actions:
- `CONFIRMATION_REQUIRED` - Waiting for user
- `CONFIRMED` - User typed "yes"
- `ABORTED` - User declined
- `SUCCESS` - Write succeeded
- `FAILED` - Write failed
- `VALIDATION_FAILED` - Input rejected

## Daily Workflow

### Morning Setup

```bash
# Authenticate (opens browser for OIDC + MFA)
source claude-vault login

# Verify session
claude-vault status

# Start working with Claude Code (MCP server auto-connects)
```

### During Work

- Session valid for 60 minutes
- Claude Code automatically uses vault tools when relevant
- Write operations pause for confirmation (you must type "yes")
- Check available tools: Type `/mcp` in Claude Code
- If session expires: Re-authenticate with `source claude-vault login`

### End of Day

```bash
# Optional: Explicitly logout
source claude-vault logout

# Or: Session auto-expires after 60 minutes
```

## Example Usage

### List all services
```
Claude: "List all services in Vault"
→ vault_list (no arguments)
→ Shows: esphome, authentik, bitwarden, ...
```

### Get secrets for a service
```
Claude: "Get the wifi_ssid secret for esphome"
→ vault_get(service="esphome", key="wifi_ssid")
→ Returns: "MyHomeWiFi"
```

### Register new secrets
```
Claude: "Register DB credentials for myapp"
→ vault_set(service="myapp", secrets={"DB_USER": "admin", "DB_PASS": "secret"})
→ Displays confirmation prompt
→ User types "yes"
→ Writes to Vault
```

### Inject to .env
```
Claude: "Inject esphome secrets to .env file"
→ vault_inject(service="esphome", format="env")
→ Creates esphome/.env with all secrets
```

## Troubleshooting

### "No Vault session found"

**Cause:** VAULT_TOKEN not in environment

**Solution:**
```bash
source claude-vault login
# Restart MCP server
```

### "Session expired"

**Cause:** 60-minute TTL exceeded

**Solution:**
```bash
source claude-vault login
# MCP server will automatically reconnect with new token
```

### "Permission denied" (HTTP 403)

**Cause:** Token lacks required policies

**Solution:**
- Verify policies in Vault UI
- Ensure token has `homelab-services` policy
- Re-authenticate if needed

### Tools not appearing in Claude Code

**Cause:** MCP server not started or misconfigured

**Solution:**
1. Verify MCP server is configured: `claude mcp get mcp-vault`
2. Check connection status (should show "✓ Connected")
3. Type `/mcp` in Claude Code to see all available tools
4. If not working, try: `claude mcp remove mcp-vault -s project` then re-add
5. Check you're in the `/workspace/proxmox-services` directory (where `.mcp.json` exists)

## Development

### Project Structure

```
mcp-vault/
├── pyproject.toml          # Package config
├── README.md               # This file
├── src/
│   └── mcp_vault/
│       ├── __init__.py     # Entry point with main()
│       ├── server.py       # MCP server setup
│       ├── session.py      # Env-based auth
│       ├── vault_client.py # HTTP API client
│       ├── security.py     # Validation & audit
│       └── tools/
│           ├── read.py     # status, list, get
│           ├── write.py    # set (with confirmation)
│           ├── auth.py     # login, logout
│           └── inject.py   # inject
```

### Testing

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run MCP Inspector for debugging
npx @modelcontextprotocol/inspector mcp-vault

# Manual test
mcp-vault
# (Starts stdio server, send JSON-RPC requests)
```

### Adding a New Tool

1. Create tool handler in appropriate file (read/write/auth/inject)
2. Inherit from `ToolHandler` base class
3. Implement `get_tool_description()` and `run_tool()`
4. Register in `server.py` TOOL_HANDLERS dict

## Security Considerations

### DO:
- ✅ Always require human confirmation for writes
- ✅ Validate all inputs
- ✅ Log all operations
- ✅ Use environment variables for tokens (memory only)
- ✅ Set short TTL (60 minutes)

### DON'T:
- ❌ Store tokens in files
- ❌ Skip confirmation prompts
- ❌ Allow Claude to auto-confirm writes
- ❌ Disable input validation
- ❌ Ignore dangerous patterns

## License

MIT

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests
4. Submit pull request

## Support

For issues or questions:
- Check troubleshooting section
- Review audit logs: `.claude-vault-audit.log`
- Verify Vault session: `claude-vault status`
- Check Claude logs for MCP errors

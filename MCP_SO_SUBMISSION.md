# mcp.so Submission Guide

Based on [mcp.so](https://mcp.so) requirements and [MCP best practices](https://www.merge.dev/blog/mcp-tool-description).

## Submission Process

1. Visit https://mcp.so
2. Click "Submit" in navigation bar
3. Create GitHub issue with server details
4. Server appears in 17K+ directory after review

## Required Information

### Basic Details
- **Name:** claude-vault
- **Repository:** https://github.com/weber8thomas/claude-vault
- **PyPI Package:** https://pypi.org/project/claude-vault-mcp/
- **Category:** Security, DevOps, Infrastructure
- **License:** MIT
- **Language:** Python 3.12+

### Description
AI-assisted HashiCorp Vault management with zero secrets sent to AI providers. Features tokenization (secrets replaced with temporary tokens), WebAuthn biometric approval for write operations, and Docker/docker-compose config migration.

### Key Features
- **Zero-knowledge AI assistance** - Secrets tokenized before reaching Claude API
- **WebAuthn security** - TouchID/Windows Hello/YubiKey approval required for writes
- **AI-assisted migration** - Scan and migrate `.env` files and docker-compose configs
- **Comprehensive audit trail** - Operation history tracking (100 ops, permanent retention)

## Tool Listings

### 📖 Read-Only Tools (Safe)

#### vault_status
**Description:** Check Vault session status including token validity, user identity, policies, time remaining until expiry, and connectivity.

**Safety:** ✅ Read-only - No destructive actions

**Input Schema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Example Usage:**
```
User: "Check my Vault session status"
AI: vault_status()
```

---

#### vault_list
**Description:** List services or secrets in Vault. Without service parameter, lists all available services under proxmox-services/. With service, lists secret keys (names only, no values) for that service.

**Safety:** ✅ Read-only - Returns structure/metadata only

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "service": {
      "type": "string",
      "description": "Optional service name to list secrets for"
    }
  },
  "required": []
}
```

**Example Usage:**
```
User: "What services do I have in Vault?"
AI: vault_list()

User: "What secrets are configured for jellyfin?"
AI: vault_list(service="jellyfin")
```

---

#### vault_get
**Description:** Retrieve secrets from Vault with values TOKENIZED for security. Returns secret keys with values replaced by temporary tokens (@token-xxx). Tokens are valid only for this session (2h default). Secret values never sent to Claude API.

**Safety:** ✅ Read-only with tokenization - AI never sees actual secret values

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "service": {
      "type": "string",
      "description": "Service name to retrieve secrets from"
    },
    "key": {
      "type": "string",
      "description": "Optional specific secret key to retrieve"
    }
  },
  "required": ["service"]
}
```

**Example Usage:**
```
User: "Show me the secrets for my jellyfin service"
AI: vault_get(service="jellyfin")
Response: API_KEY: @token-a8f3d9e1b2c4f7a9 (AI never sees actual value)
```

---

### 🔐 Authentication Tools (Local)

#### vault_login
**Description:** Authenticate to HashiCorp Vault via OIDC. Guides user through browser-based authentication flow. Updates environment variables but cannot directly modify running MCP server environment.

**Safety:** ⚠️ Requires user action - Opens browser for OIDC login

**Input Schema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Notes:** User must restart MCP server after login to pick up new token.

---

#### vault_logout
**Description:** Revoke the current Vault token and provide instructions to clear environment variables. Invalidates the session and requires re-authentication for future operations.

**Safety:** ⚠️ Revokes access - User must manually restart MCP server

**Input Schema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

---

### ✍️ Write Tools (WebAuthn Required)

#### vault_set
**Description:** Create or update secrets in Vault for a service.

**Safety:** 🔒 WebAuthn approval REQUIRED - Cannot execute without biometric authentication

**WebAuthn Workflow:**
1. **Phase 1:** Call without approval_token → validates inputs, creates pending operation
2. **Phase 2:** User opens approval URL in browser → authenticates with TouchID/Windows Hello
3. **Phase 3:** Call with approval_token → writes to Vault after verification

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "service": {
      "type": "string",
      "description": "Service name to register secrets for"
    },
    "secrets": {
      "type": "object",
      "description": "Key-value pairs of secrets to register",
      "additionalProperties": {"type": "string"}
    },
    "approval_token": {
      "type": "string",
      "description": "Approval token from WebAuthn (only after user approves)"
    },
    "dry_run": {
      "type": "boolean",
      "description": "Preview without writing",
      "default": false
    }
  },
  "required": ["service", "secrets"]
}
```

**Example Usage:**
```
User: "Register API key for my app"
AI: vault_set(service="myapp", secrets={"API_KEY": "value"})
AI: ⚠️ Approve at: http://localhost:8091/approve/xyz123
User: [Opens URL, authenticates with TouchID]
AI: vault_set(service="myapp", secrets={"API_KEY": "value"}, approval_token="xyz123")
Result: ✓ Secrets registered in Vault
```

---

### 🔍 Scanning Tools (WebAuthn Required)

#### vault_scan_env
**Description:** Scan .env files for secrets and tokenize them before sending to AI.

**Safety:** 🔒 WebAuthn approval REQUIRED - Reads sensitive files

**WebAuthn Workflow:** Same 3-phase process as vault_set

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "service": {
      "type": "string",
      "description": "Service name (e.g., 'jellyfin', 'sonarr')"
    },
    "file_path": {
      "type": "string",
      "description": "Optional: Path to .env file"
    },
    "approval_token": {
      "type": "string",
      "description": "Approval token from WebAuthn"
    }
  },
  "required": ["service"]
}
```

---

#### vault_scan_compose
**Description:** Scan docker-compose.yml files for secrets in environment variables and tokenize them.

**Safety:** 🔒 WebAuthn approval REQUIRED - Scans configuration files

**WebAuthn Workflow:** Same 3-phase process as vault_set

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "service": {
      "type": "string",
      "description": "Service name"
    },
    "file_path": {
      "type": "string",
      "description": "Optional: Path to docker-compose.yml"
    },
    "approval_token": {
      "type": "string",
      "description": "Approval token from WebAuthn"
    }
  },
  "required": ["service"]
}
```

---

### 📁 File Generation Tools (Safe)

#### vault_inject
**Description:** Inject secrets from Vault into local configuration files (.env or secrets.yaml). Detokenizes values locally (never sent to Claude API). Generated files should be in .gitignore.

**Safety:** ⚠️ Writes local files - Creates plaintext secret files on disk

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "service": {
      "type": "string",
      "description": "Service name to inject secrets for"
    },
    "format": {
      "type": "string",
      "enum": ["auto", "env", "yaml"],
      "description": "Output format",
      "default": "auto"
    }
  },
  "required": ["service"]
}
```

---

#### vault_generate_example
**Description:** Generate .env.example or docker-compose.example.yml files with secrets redacted (<REDACTED> placeholders). Preserves configuration values while hiding secrets. Safe for committing to git.

**Safety:** ✅ Read-only - Only generates example files

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "service": {
      "type": "string",
      "description": "Service name"
    },
    "file_path": {
      "type": "string",
      "description": "Optional: Path to source file"
    },
    "format": {
      "type": "string",
      "enum": ["auto", "env", "yaml"],
      "default": "auto"
    },
    "output_path": {
      "type": "string",
      "description": "Optional: Output path"
    }
  },
  "required": ["service"]
}
```

---

## Privacy Policy

### Data Handling
- **Secrets never sent to AI:** All secret values are tokenized (@token-xxx) before being sent to Claude API
- **Local processing:** MCP server runs on user's machine, not in cloud
- **WebAuthn approval:** All write operations require biometric authentication
- **No telemetry:** No analytics or usage data collected
- **Audit trail:** All operations logged locally for compliance (~/.claude-vault/)

### Storage
- **Vault tokens:** Stored only in shell environment, expire after 60 minutes
- **Approval operations:** Stored locally in ~/.claude-vault/pending_operations/
- **WebAuthn credentials:** Stored in browser's secure storage (WebAuthn standard)

### Full Privacy Policy
See https://github.com/weber8thomas/claude-vault#security-architecture

## Installation

```bash
# From PyPI (recommended)
pip install claude-vault-mcp

# Or using uvx
uvx claude-vault-mcp
```

## Configuration

Add to `.mcp.json`:
```json
{
  "mcpServers": {
    "claude-vault": {
      "command": "uvx",
      "args": ["claude-vault-mcp"],
      "env": {
        "VAULT_ADDR": "https://vault.example.com",
        "VAULT_TOKEN": "${VAULT_TOKEN}",
        "VAULT_SECURITY_MODE": "tokenized"
      }
    }
  }
}
```

## Prerequisites

1. HashiCorp Vault server with OIDC authentication
2. vault-approve-server running: `vault-approve-server`
3. WebAuthn-compatible browser
4. Python 3.12+

## Documentation

- **Full Documentation:** https://github.com/weber8thomas/claude-vault#readme
- **Security Architecture:** https://github.com/weber8thomas/claude-vault#security-architecture
- **WebAuthn Setup:** https://github.com/weber8thomas/claude-vault/blob/main/packages/mcp-server/WEBAUTHN_SETUP.md
- **Publishing Guide:** https://github.com/weber8thomas/claude-vault/blob/main/PUBLISHING.md

## Support

- **Issues:** https://github.com/weber8thomas/claude-vault/issues
- **Discussions:** https://github.com/weber8thomas/claude-vault/discussions

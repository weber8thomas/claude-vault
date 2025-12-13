# Vault Quick Start for Claude Code

> **For Claude Code AI Assistant:** This is the authoritative guide for Vault access. Always reference this first.

## Quick Command Reference

```bash
# Authentication (use 'source' to export variables)
source claude-vault login          # Authenticate via OIDC
claude-vault status                # Check session status
source claude-vault logout         # Revoke token and clear session

# Secret operations
claude-vault list                  # List all services
claude-vault list bitwarden        # List keys for bitwarden
claude-vault get bitwarden         # Get all bitwarden secrets
claude-vault get bitwarden DOMAIN  # Get specific secret
claude-vault set bitwarden KEY=val # Register/update secrets
claude-vault inject bitwarden      # Inject to .env file
```

---

## 🔐 Authentication (Human Required)

**You (human) must authenticate first:**

```bash
source ./scripts/vault-login-simple.sh
```

Then:
1. Open URL shown
2. Login with OIDC + security key/MFA
3. Paste token when prompted
4. Session valid for 60 minutes

**Share token with Claude Code:**
```bash
echo "Token: $VAULT_TOKEN"
```

---

## 🤖 For Claude Code

### Check Session
```bash
export VAULT_ADDR="https://vault.example.com"
export VAULT_TOKEN="<user-provided-token>"
export VAULT_TOKEN_EXPIRY="$(($(date +%s) + 3600))"

./scripts/vault-status.sh
```

### List Secrets
```bash
# All services
claude-vault list

# Specific service (keys only)
claude-vault list esphome

# Get values (shows plaintext!)
claude-vault get esphome wifi_ssid
```

### Register Secrets (Requires human confirmation)
```bash
# Preview first (safe, no changes)
claude-vault set --dry-run myapp \
  DB_PASSWORD="secret123" \
  API_KEY="abc789"

# Actual registration (asks human for "yes")
claude-vault set myapp \
  DB_PASSWORD="secret123" \
  API_KEY="abc789"
```

---

## 📋 Available Scripts

| Script | Purpose | Human Confirmation |
|--------|---------|-------------------|
| `vault-login-simple.sh` | Authenticate via OIDC | ✅ Human auth required |
| `vault-status.sh` | Check session | No |
| `vault-logout.sh` | Revoke token | No |
| `claude-vault-list.sh` | List services/keys | No |
| `claude-vault-get.sh` | Get secret values | No |
| `claude-vault-register.sh` | Create/update secrets | ✅ Must type "yes" |

---

## 🔒 Security Model

### What Claude Code Can Do:
- ✅ **List** services and secret keys
- ✅ **Read** all secret values
- ✅ **Create/Update** secrets (with human confirmation)

### What Claude Code Cannot Do:
- ❌ **Delete** secrets
- ❌ **Access** paths outside `proxmox-services/*`
- ❌ **Bypass** human confirmation prompts
- ❌ **Authenticate** without human present

### Protection Layers:
1. **Human authentication** (OIDC + MFA)
2. **Session-based** (60 min auto-expire)
3. **Input validation** (prevents injection)
4. **Manual confirmation** (for writes)
5. **Audit logging** (`.claude-vault-audit.log`)

---

## 🎯 Common Workflows

### Workflow 1: Help user list secrets
```bash
# User authenticates and shares token
export VAULT_TOKEN="<token>"

# Claude lists services
claude-vault list

# Claude shows specific service
claude-vault list esphome
```

### Workflow 2: Register new service secrets
```bash
# Claude previews (safe)
claude-vault set --dry-run newservice \
  SECRET1="value1" \
  SECRET2="value2"

# Show preview to human
# Ask: "Does this look correct?"

# If approved, run actual command
claude-vault set newservice \
  SECRET1="value1" \
  SECRET2="value2"

# Script will STOP and show confirmation prompt
# Claude MUST tell human: "Please type 'yes' to confirm"
# Human types 'yes' in their terminal
```

### Workflow 3: Inject secrets to service
```bash
# After secrets are in Vault, inject to .env file
export VAULT_TOKEN="<token>"
./scripts/inject-secrets.sh myservice
```

---

## ⚠️ Important Reminders for Claude Code

1. **NEVER bypass confirmation prompts** - If you see the security checkpoint, STOP and tell the human to review and type "yes"

2. **Session expires in 60 minutes** - If commands fail with "session expired", tell human to re-authenticate

3. **Validate inputs** - The scripts validate automatically, but be cautious with user-provided values

4. **Audit log** - All operations logged to `.claude-vault-audit.log`

5. **No persistent credentials** - Token is session-only, no files on disk

---

## 📚 Full Documentation

- **This file** - Quick start (read this first!)
- `CLAUDE_VAULT_SETUP.md` - Detailed setup guide
- `CLAUDE_VAULT_SECURITY.md` - Security details & prompt injection protection
- ~~`CLAUDE_VAULT_ACCESS.md`~~ - **DEPRECATED** (old AppRole approach)

---

## 🆘 Troubleshooting

**"No active Vault session"**
→ Human needs to authenticate: `source ./scripts/vault-login-simple.sh`

**"Session expired"**
→ 60 minutes passed, re-authenticate

**"Invalid token"**
→ Token was revoked, get fresh token

**Scripts not executable**
→ `chmod +x scripts/vault-*.sh scripts/claude-vault-*.sh`

---

**Last Updated:** 2025-12-12
**Auth Method:** Session-based OIDC (human-initiated)
**Session Duration:** 60 minutes
**Status:** ✅ Production ready

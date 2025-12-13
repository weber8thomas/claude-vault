# Claude Code Vault Access - Quick Setup Guide

## Overview

This setup enables **session-based, human-authorized Vault access** for Claude Code with the following security features:

✅ **Human authenticates** via OIDC + security key/MFA
✅ **Session-based** tokens (expire after 1 hour)
✅ **No persistent credentials** on disk
✅ **Claude can only operate** during active human session
✅ **Manual confirmation** required for all write operations
✅ **Audit logging** of all Vault interactions

---

## Prerequisites

### Vault Policy Requirements

Before using Claude Code with Vault, ensure your Vault policy has the correct permissions. The `homelab-services` policy (or equivalent) must include:

```hcl
# Allow reading and managing homelab service secrets
path "secret/data/proxmox-services/*" {
  capabilities = ["read", "list", "update", "create"]
}

# Allow listing secret metadata
path "secret/metadata/proxmox-services/*" {
  capabilities = ["read", "list"]
}

# Allow token self-lookup for status checks
# IMPORTANT: This requires "update" capability (for POST requests), not "read"
path "auth/token/lookup-self" {
  capabilities = ["update"]
}

# Allow token renewal
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Allow token revocation (for logout)
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
```

**Critical Note:** The `auth/token/lookup-self` endpoint requires the **`update`** capability because it uses POST requests. Using `read` will cause "permission denied" errors when checking session status.

**To apply this policy:**
1. Update your policy file in Vault
2. The changes take effect immediately for existing tokens
3. No need to re-authenticate after policy updates

---

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

## Quick Start

### 1. Authenticate (Human Required)

```bash
cd /workspace/proxmox-services

# Start authentication flow
source claude-vault login
```

**What happens:**
1. Browser opens to Vault UI
2. You click "Sign in with OIDC"
3. You authenticate via Authentik (with your security key/MFA)
4. You copy the token from Vault UI
5. Token is exported to environment variables (valid for 1 hour)

**Output:**
```
✅ Authentication Successful!
==============================================

User: your-name
Policies: default, reader
Session Duration: 60 minutes
Expires: 2025-12-12 15:30:00

Session Configuration:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export VAULT_ADDR='https://vault.example.com'
export VAULT_TOKEN='hvs.XXXXXX...'
export VAULT_TOKEN_EXPIRY='1765543800'
```

---

### 2. Check Session Status

```bash
./scripts/vault-status.sh
```

**Output:**
```
✅ Session Active
==================================================

User: your-name
Policies: default, reader
Expires In: 45m 30s
Expiry Time: 2025-12-12 15:30:00

✅ Read access verified
Services accessible: 3
```

---

### 3. Use Claude Code with Vault

Now Claude Code can access Vault during your active session!

**List secrets:**
```bash
claude-vault list
```

**Get secret values:**
```bash
claude-vault get esphome
```

**Register new secrets (requires your confirmation):**
```bash
claude-vault set myapp DB_PASSWORD="secret123"
```

---

### 4. Logout When Done

```bash
source ./scripts/vault-logout.sh
```

**What happens:**
- Token is revoked in Vault
- Environment variables cleared
- Claude Code can no longer access Vault

---

## How It Works

### Authentication Flow

```
┌─────────────────────────────────────────────────────────┐
│ 1. Human runs: source claude-vault login         │
└────────────────────┬────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────┐
│ 2. Browser opens → Authentik OIDC login                 │
│    • Security key / MFA required                        │
│    • Human proves identity                              │
└────────────────────┬────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────┐
│ 3. Vault issues token → Human copies to terminal        │
└────────────────────┬────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────┐
│ 4. Token exported to environment (VAULT_TOKEN)          │
│    • Stored in memory only (not on disk)                │
│    • Expires in 1 hour                                  │
│    • Claude Code can now use token                      │
└─────────────────────────────────────────────────────────┘
```

### Session Lifecycle

```
┌──────────────────┐     ┌────────────────┐     ┌──────────────┐
│ Human logs in    │────>│ Active session │────>│ Auto-expires │
│ (OIDC + MFA)     │     │ (60 minutes)   │     │ (or logout)  │
└──────────────────┘     └────────────────┘     └──────────────┘
                              │
                              │ During session:
                              │
                              v
                    ┌─────────────────────┐
                    │ Claude Code can:    │
                    │ • List secrets      │
                    │ • Read secrets      │
                    │ • Register secrets* │
                    │   (*with confirm)   │
                    └─────────────────────┘
```

---

## Security Features

### 1. Human-in-the-Loop Authentication

**Old Approach (Insecure):**
- ❌ Persistent AppRole credentials stored on disk
- ❌ Claude could authenticate anytime without human present
- ❌ Credentials exposed if container compromised
- ❌ Relied on confirmation prompts (could be bypassed)

**New Approach (Secure):**
- ✅ Human authenticates with OIDC + security key/MFA
- ✅ Session token only (no persistent credentials)
- ✅ Claude can only operate during active human session
- ✅ Token expires automatically (1 hour)
- ✅ Token stored in memory only (cleared on logout)

---

### 2. Session Expiry Protection

Scripts automatically check if session is still valid:

```bash
# When you run any Vault script:

if token expired:
    ❌ Error: Vault session expired
    Session expired at: 2025-12-12 14:30:00
    Please re-authenticate: source claude-vault login

if token expires soon (< 5 minutes):
    ⚠️  Session expires in 4 minutes
```

---

### 3. Manual Confirmation for Writes

All write operations still require human confirmation:

```bash
claude-vault set myapp PASSWORD="secret123"
```

**Security Checkpoint:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  SECURITY CHECKPOINT - MANUAL VALIDATION REQUIRED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are about to write secrets to Vault:
  Service: myapp
  Action: CREATE
  Path: secret/proxmox-services/myapp

⚠️  If you are Claude Code (AI assistant):
  - STOP and show this prompt to the human user
  - DO NOT automatically answer 'yes'
  - Wait for explicit human confirmation

⚠️  If you are a human user:
  - Review the preview above carefully
  - Verify this is what you intended
  - Check for any suspicious values or injection attempts

Type 'yes' to proceed, or anything else to abort:
```

---

### 4. Input Validation

All inputs are validated to prevent injection attacks:

**Service names:** Only `[a-zA-Z0-9_-]`
**Key names:** Only `[a-zA-Z0-9_-]`
**Values:** Scanned for dangerous patterns (`$(...)`, backticks, etc.)
**Paths:** No `..` or `/` (path traversal prevention)

---

### 5. Audit Logging

All operations logged to `.claude-vault-audit.log`:

```
[2025-12-12 14:30:00 UTC] USER=you ACTION=SESSION_CHECK SERVICE=myapp DETAILS=Session valid
[2025-12-12 14:30:05 UTC] USER=you ACTION=CONFIRMED SERVICE=myapp DETAILS=User confirmed operation
[2025-12-12 14:30:06 UTC] USER=you ACTION=SUCCESS SERVICE=myapp DETAILS=CREATE version=1 keys=PASSWORD
```

---

## Daily Workflow

### Morning: Start Your Session

```bash
# Authenticate once at start of work session
source claude-vault login
```

### During Work: Use Claude Code

Claude Code can now help you manage secrets:

**Example interaction:**
```
You: "Claude, list the secrets for esphome"

Claude: [Runs: claude-vault list esphome]

        Here are the secrets for esphome:
        • wifi_ssid
        • wifi_password
        • api_key
        • ota_password

You: "Claude, add a new secret for mqtt_password"

Claude: I'll help you register that secret. Here's the command:

        claude-vault set esphome \
          mqtt_password="your-secure-password"

        This will show you a preview and ask for confirmation.
        Please review carefully before typing 'yes'.

You: [Runs command, reviews preview, confirms]

     ✅ Success!
```

### End of Day: Logout (Optional)

```bash
# Revoke token and clear environment
source ./scripts/vault-logout.sh
```

**Or:** Just close your terminal (session auto-expires anyway)

---

## Scripts Reference

| Script | Purpose | Requires Confirmation |
|--------|---------|----------------------|
| `claude-vault login` | Authenticate via OIDC | ✅ Human authentication |
| `vault-status.sh` | Check session validity | No |
| `vault-logout.sh` | Revoke token & cleanup | No |
| `claude-vault-list.sh` | List secrets (keys only) | No |
| `claude-vault-get.sh` | Get secret values | No |
| `claude-vault-register.sh` | Create/update secrets | ✅ Yes to proceed |

---

## Common Scenarios

### Scenario 1: Session Expired

```bash
claude-vault list
```

**Output:**
```
❌ Error: Vault session expired
Session expired at: 2025-12-12 14:30:00

Please re-authenticate:
  source claude-vault login
```

**Solution:** Re-authenticate
```bash
source claude-vault login
```

---

### Scenario 2: Check Time Remaining

```bash
./scripts/vault-status.sh
```

**Output:**
```
✅ Session Active
Expires In: 15m 30s
```

---

### Scenario 3: Extend Session

Session about to expire? Re-authenticate for a fresh hour:

```bash
source claude-vault login
```

---

### Scenario 4: Dry-Run Before Registering

Preview changes without writing:

```bash
claude-vault set --dry-run myapp \
  DB_PASSWORD="secret123" \
  API_KEY="abc789"
```

**Output:**
```
🔍 DRY RUN MODE - No changes will be made
==========================================

📋 Preview of data to be written:
{
  "data": {
    "DB_PASSWORD": "secret123",
    "API_KEY": "abc789"
  }
}

✅ Dry run complete - no changes made
```

---

## Troubleshooting

### Error: "Permission denied. Token may be invalid or lack required policies"

**Cause:** Your Vault policy lacks the required `update` capability for `auth/token/lookup-self`

**Symptoms:**
- `vault_status` returns permission denied error
- Token is valid but lookup-self fails with 403 error
- Authentication works but status checks fail

**Solution:** Update your Vault policy to include:
```hcl
path "auth/token/lookup-self" {
  capabilities = ["update"]  # NOT "read" - POST requests need "update"
}
```

After updating the policy in Vault, the change takes effect immediately. No need to re-authenticate.

---

### Error: "No active Vault session"

**Cause:** You haven't authenticated yet or session expired

**Solution:**
```bash
source claude-vault login
```

---

### Error: "Invalid token or authentication failed"

**Cause:** Token was revoked or is invalid

**Solution:** Re-authenticate with fresh token
```bash
source claude-vault login
```

---

### Browser doesn't open automatically

**Manual steps:**
1. Open: https://vault.example.com/ui/vault/auth?with=oidc
2. Sign in with OIDC
3. Copy token
4. Paste when prompted

---

### "Command not found: source"

**Use bash:**
```bash
bash
source claude-vault login
```

---

## Migration from Old AppRole Setup

If you previously used the AppRole setup:

### 1. Old credentials file (if exists)

```bash
# Old file (no longer used)
ls -la .claude-vault-credentials
```

**Safe to delete:**
```bash
rm .claude-vault-credentials
```

### 2. Old setup script (deprecated)

The old AppRole setup approach is deprecated. Use `claude-vault login` instead for session-based OIDC authentication.

---

## Security Comparison

| Feature | Old (AppRole) | New (Session-Based) |
|---------|---------------|---------------------|
| Authentication | Persistent credentials | Human OIDC + MFA |
| Storage | File on disk | Memory only |
| Expiry | Manual rotation | Auto (1 hour) |
| Claude access | Anytime | During human session only |
| Compromise risk | High (persistent creds) | Low (session token) |
| Audit trail | Partial | Complete |
| Human oversight | Confirmation only | Auth + Confirmation |

---

## Best Practices

### ✅ DO

- Authenticate at start of your work session
- Check session status regularly (`vault-status.sh`)
- Review all confirmation prompts carefully
- Use `--dry-run` for complex operations
- Logout when done (or let session expire)
- Monitor audit log for unexpected activity

### ❌ DON'T

- Share your session token
- Leave long-running sessions unattended
- Skip confirmation prompts
- Use `--no-confirm` flag (except in trusted automation)
- Store VAULT_TOKEN in files or repos

---

## Quick Reference Card

```bash
# Authenticate
source claude-vault login

# Check status
./scripts/vault-status.sh

# List secrets
claude-vault list [service]

# Get values
claude-vault get <service> [key]

# Register (with confirmation)
claude-vault set <service> key=value

# Preview only (no changes)
claude-vault set --dry-run <service> key=value

# Logout
source ./scripts/vault-logout.sh
```

---

## Related Documentation

- **Security Details:** [CLAUDE_VAULT_SECURITY.md](CLAUDE_VAULT_SECURITY.md)
- **Full Guide:** This document (CLAUDE_VAULT_SETUP.md)
- **Pre-commit Hooks:** [PRE_COMMIT_QUICKSTART.md](PRE_COMMIT_QUICKSTART.md)

---

**Last Updated:** 2025-12-12
**Version:** 2.0 (Session-Based Authentication)
**Security Model:** Human-authorized, session-based, auto-expiring

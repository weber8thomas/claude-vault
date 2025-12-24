# MCP-Vault Test Service

A simple demonstration service for testing and showcasing mcp-vault features.

## Overview

This nginx service demonstrates the complete mcp-vault workflow with **3 simple secrets**:
- `API_KEY` - External service API key
- `DATABASE_URL` - Database connection string
- `SESSION_SECRET` - Session authentication secret

## Quick Start - Three Ways to Use

### Option 1: Natural Language (Ask Claude/AI)

**Scan for secrets:**
```
"Scan the test-service .env file for secrets"
```

**Store to Vault:**
```
"Store the test-service secrets to Vault"
```
→ Opens approval URL: `http://localhost:8091/approve/{op_id}`
→ Approve with TouchID/Windows Hello/YubiKey
→ Then: `"Complete the vault_set operation with approval token {op_id}"`

**Inject from Vault:**
```
"Inject test-service secrets from Vault to create the .env file"
```

**Get secrets (view):**
```
"Show me the test-service secrets from Vault"
```

---

### Option 2: MCP Tools (Direct Function Calls)

**Scan for secrets:**
```python
vault_scan_env(
    service="test-service",
    file_path="/workspace/mcp-vault/examples/test-service/.env"
)
```

**Store to Vault (Phase 1 - Create pending operation):**
```python
vault_set(
    service="test-service",
    secrets={
        "API_KEY": "test-api-key-abc123def456",
        "DATABASE_URL": "postgresql://testuser:testpass@localhost:5432/testdb",
        "SESSION_SECRET": "super-secret-session-key-xyz789"
    }
)
```
→ Returns approval URL, approve with WebAuthn

**Store to Vault (Phase 2 - Execute after approval):**
```python
vault_set(
    service="test-service",
    secrets={
        "API_KEY": "test-api-key-abc123def456",
        "DATABASE_URL": "postgresql://testuser:testpass@localhost:5432/testdb",
        "SESSION_SECRET": "super-secret-session-key-xyz789"
    },
    approval_token="abc123xyz"  # From approval URL
)
```

**Inject from Vault:**
```python
vault_inject(service="test-service")
```

**Get secrets (view):**
```python
vault_get(service="test-service")
```

---

### Option 3: CLI Package (vault-session)

**Authenticate to Vault:**
```bash
source vault-session login
vault-session status
```

**List services:**
```bash
vault-session list
```

**Get secrets:**
```bash
vault-session get test-service
```

**Set secrets (requires manual JSON file):**
```bash
# Create secrets.json
cat > /tmp/test-service-secrets.json <<'EOF'
{
  "API_KEY": "test-api-key-abc123def456",
  "DATABASE_URL": "postgresql://testuser:testpass@localhost:5432/testdb",
  "SESSION_SECRET": "super-secret-session-key-xyz789"
}
EOF

# Write to Vault
vault kv put secret/proxmox-services/test-service @/tmp/test-service-secrets.json

# Clean up
rm /tmp/test-service-secrets.json
```

**Note:** The CLI doesn't have built-in WebAuthn approval - it uses direct Vault access after authentication.

---

## Files

```
examples/test-service/
├── docker-compose.yml    # Service with ${VAR} references
├── .env                  # Test secrets (fake values for demo)
├── .env.example          # Template with <REDACTED>
├── html/index.html       # Web page
└── README.md             # This file
```

## Run the Service

```bash
cd /workspace/mcp-vault/examples/test-service

# Start
docker-compose up -d

# Verify
curl http://localhost:8080

# Stop
docker-compose down
```

## Vault Path

Secrets stored at:
```
secret/proxmox-services/test-service/
├── API_KEY
├── DATABASE_URL
└── SESSION_SECRET
```

## Security

✅ **Safe to commit:**
- `docker-compose.yml` (uses ${VAR} references)
- `.env.example` (has <REDACTED> placeholders)

❌ **DO NOT commit:**
- `.env` (actual secrets - even fake ones for demo)
- `.env.backup.*` (backup files)

## Comparison

| Feature | Natural Language | MCP Tools | CLI Package |
|---------|-----------------|-----------|-------------|
| **Ease of use** | Easiest - just ask | Medium - function calls | Advanced - shell commands |
| **WebAuthn approval** | ✅ Yes | ✅ Yes | ❌ No (direct Vault access) |
| **Secret tokenization** | ✅ Yes (AI never sees values) | ✅ Yes | ❌ No |
| **Scanning files** | ✅ Yes | ✅ Yes | ❌ Manual |
| **Best for** | Quick testing, demos | Automation, scripts | Manual Vault operations |

## Next Steps

1. Test all three interaction methods
2. Try with your own services
3. Set up production deployment with nginx
4. Integrate with CI/CD pipelines

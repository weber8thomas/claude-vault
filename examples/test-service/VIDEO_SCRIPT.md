# Video Recording Script - MCP-Vault Demo

**Duration:** 5-7 minutes

## Temporary Setup (Keep Your Data Clean)

### Option 1: Temporary Vault Instance (Recommended)

Run a local Vault dev server just for recording:

```bash
# Terminal 1: Start temporary Vault dev server
vault server -dev -dev-root-token-id="demo-token" -dev-listen-address="127.0.0.1:8201"

# Terminal 2: Configure for demo Vault
export VAULT_ADDR="http://127.0.0.1:8201"
export VAULT_TOKEN="demo-token"

# Verify connection
vault status

# Start approval server (uses ~/.claude-vault/ but that's okay for temp data)
vault-approve-server

# Register WebAuthn device
# Open: http://localhost:8091/register
```

**After recording:**
```bash
# Stop dev Vault (Ctrl+C in Terminal 1)
# All demo data in Vault is gone
# Optionally clean approval server data:
rm -rf ~/.claude-vault/*.json
```

### Option 2: Use Separate User Profile (Linux/Mac)

```bash
# Run approval server as different user with isolated home directory
sudo -u demo-user vault-approve-server
# Data goes to /home/demo-user/.claude-vault/
```

---

## Recording Steps

### Pre-Recording Checklist
- [ ] Demo Vault running on port 8201
- [ ] `VAULT_ADDR=http://127.0.0.1:8201` set
- [ ] `VAULT_TOKEN=demo-token` set
- [ ] Approval server running on port 8091
- [ ] WebAuthn device registered at http://localhost:8091/register
- [ ] Test service ready in examples/test-service/
- [ ] Browser ready

---

### 1. Introduction (30 sec)
```bash
cd /workspace/mcp-vault/examples/test-service
cat .env
```
Show 3 secrets: API_KEY, DATABASE_URL, SESSION_SECRET

---

### 2. Scan Secrets (1 min)
Ask Claude:
```
"Scan the test-service .env file for secrets"
```
**Show:** Tokenized output with @token-xxx

---

### 3. Store to Vault (2 min)

**Phase 1:** Ask Claude:
```
"Store the test-service secrets to Vault"
```
**Show:** Approval URL

**Phase 2:**
- Open URL in browser
- Approve with WebAuthn (TouchID/Windows Hello)

**Phase 3:** Ask Claude:
```
"Complete the vault_set operation with approval token {id}"
```
**Show:** Success message

---

### 4. Inject & Run (1.5 min)
```bash
# Remove .env
rm .env

# Ask Claude:
"Inject test-service secrets from Vault to create .env"

# Verify secrets injected
cat .env

# Start service
docker-compose up -d

# Verify running
curl http://localhost:8080
```

---

### 5. Summary (30 sec)
```bash
docker-compose down
```

**Show what happened:**
- ✅ Scanned secrets (AI never saw values)
- ✅ Stored to Vault (WebAuthn approval required)
- ✅ Injected from Vault
- ✅ Service ran successfully

---

## Vault Dev Server Setup (Detailed)

### Install Vault (if not installed)
```bash
# macOS
brew install vault

# Linux
wget https://releases.hashicorp.com/vault/1.15.0/vault_1.15.0_linux_amd64.zip
unzip vault_1.15.0_linux_amd64.zip
sudo mv vault /usr/local/bin/
```

### Start Dev Server
```bash
# Start in dev mode (in-memory, no persistence)
vault server -dev \
  -dev-root-token-id="demo-token" \
  -dev-listen-address="127.0.0.1:8201"

# Leave this running in Terminal 1
```

**Output will show:**
```
WARNING! dev mode is enabled!
Root Token: demo-token
Unseal Key: (not needed in dev mode)

The server is running at: http://127.0.0.1:8201
```

### Configure Client (Terminal 2)
```bash
# Point to dev Vault
export VAULT_ADDR="http://127.0.0.1:8201"
export VAULT_TOKEN="demo-token"

# Test connection
vault status
# Should show: Sealed: false

# Enable KV v2 secrets engine (if needed)
vault secrets enable -path=secret kv-v2 2>/dev/null || true
```

### Verify Setup
```bash
# Write test secret
vault kv put secret/test key=value

# Read it back
vault kv get secret/test

# Delete it
vault kv delete secret/test
```

---

## MCP Server Configuration for Demo

Update your `.mcp.json` to use demo Vault:

```json
{
  "mcpServers": {
    "mcp-vault": {
      "command": "uvx",
      "args": ["mcp-vault"],
      "env": {
        "VAULT_ADDR": "http://127.0.0.1:8201",
        "VAULT_TOKEN": "demo-token",
        "VAULT_SECURITY_MODE": "tokenized"
      }
    }
  }
}
```

**Restart your MCP client** after changing config.

---

## Quick Test Before Recording

```bash
# 1. Vault is running
vault status

# 2. Approval server is running
curl http://localhost:8091

# 3. WebAuthn is registered
# Open http://localhost:8091 - should show "1 registered device"

# 4. Test the workflow
cd examples/test-service
# Ask Claude: "Get test-service secrets from Vault"
# Should fail with "not found" (good - clean state)
```

---

## Cleanup After Recording

```bash
# Terminal 1: Stop Vault dev server
# Press Ctrl+C
# All demo Vault data is automatically deleted

# Terminal 2: Stop approval server
pkill -f vault-approve-server

# Optional: Clean approval server demo data
rm ~/.claude-vault/pending-operations.json
rm ~/.claude-vault/completed-operations.json
# Keep webauthn-credentials.json if you want to reuse the device

# Reset MCP config to production Vault
# Edit .mcp.json back to your real VAULT_ADDR
```

---

## Troubleshooting

**"Connection refused" to Vault:**
- Check Vault dev server is running: `ps aux | grep vault`
- Verify VAULT_ADDR: `echo $VAULT_ADDR`
- Should be: http://127.0.0.1:8201

**WebAuthn not working:**
- Check approval server: `lsof -i :8091`
- Re-register device: http://localhost:8091/register

**MCP server not connecting to Vault:**
- Restart MCP client after config change
- Verify env vars in .mcp.json
- Check vault-session status

---

## Why This Setup?

✅ **Isolated:** Demo Vault on port 8201, production on 8200
✅ **Temporary:** Dev Vault stores data in-memory, gone when stopped
✅ **Clean:** Your production Vault data untouched
✅ **Repeatable:** Easy to restart and re-record
✅ **Safe:** Demo token is disposable

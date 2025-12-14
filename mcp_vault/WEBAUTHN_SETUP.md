# WebAuthn Setup Guide

## Overview

The mcp-vault approval system uses **WebAuthn** (same technology as Authentik) to require biometric/hardware authentication before writing secrets to Vault.

Supported authenticators:
- 🍎 **TouchID** (macOS)
- 🪟 **Windows Hello** (Windows)
- 🔑 **YubiKey** (cross-platform)
- 📱 **Phone authenticators** (via Bluetooth/NFC)

## One-Time Device Registration

Before you can approve Vault operations, you must register your authenticator **once**.

### Step 1: Start the Approval Server

The approval server starts automatically when you use `vault_set`, but you can also start it manually:

```bash
# Option 1: Standalone server (for testing)
vault-approve-server

# Option 2: Let MCP start it automatically (recommended)
# Just use vault_set normally, server auto-starts on first use
```

The server runs on `http://localhost:8091`

### Step 2: Register Your Authenticator

Open your browser and navigate to:

```
http://localhost:8091/register
```

**What you'll see:**
1. A page titled "🔐 Register Authenticator"
2. A button: "Register Authenticator"
3. Click the button

**What happens next:**

**On macOS (TouchID):**
- Dialog appears: "Touch Touch ID to register"
- Touch your fingerprint sensor
- Success message: "✅ Authenticator registered successfully!"

**On Windows (Windows Hello):**
- Windows Hello prompt appears
- Use fingerprint/face/PIN
- Success message appears

**On Linux/Any OS (YubiKey):**
- Insert YubiKey
- Touch the metal contact
- Success message appears

### Step 3: Verify Registration

After successful registration, you'll see:

```
✅ Authenticator registered successfully!

You can now approve Vault operations!
```

Your credentials are stored in: `~/.claude-vault/webauthn-credentials.json`

**This file is safe to commit to git** - it only contains public keys, not private keys. The private keys stay in your:
- Secure Enclave (macOS)
- TPM (Windows)
- Hardware token (YubiKey)

## Daily Workflow

### Writing Secrets with WebAuthn Approval

```
# 1. You (or Claude) calls vault_set
vault_set(service="myapp", secrets={"DB_PASS": "secret123"})

# 2. MCP returns approval URL
⚠️  SECURITY CHECKPOINT - WEBAUTHN APPROVAL REQUIRED

To approve:
  1. Open in browser: http://localhost:8091/approve/abc123xyz
  2. Review the operation details
  3. Click "Approve with WebAuthn"
  4. Authenticate with your device

After approval, call vault_set again with:
  vault_set(service="myapp", secrets={...}, approval_token="abc123xyz")

# 3. You open the URL in browser
[Browser shows rich preview of what will be written]

# 4. You click "Approve with WebAuthn"
[TouchID/Windows Hello/YubiKey prompt appears]

# 5. You authenticate
[Success message: ✅ Operation approved!]

# 6. Call vault_set again with token
vault_set(service="myapp", secrets={"DB_PASS": "secret123"}, approval_token="abc123xyz")

# 7. Write succeeds
✅ Success! Secrets written to Vault.
```

## Troubleshooting

### "No registered authenticator. Please register first."

**Solution:**
1. Open: `http://localhost:8091/register`
2. Click "Register Authenticator"
3. Complete authentication

### "Touch ID is not available on this device"

**Options:**
1. Use a YubiKey instead
2. On macOS: Enable TouchID in System Preferences
3. Fall back to password authentication (less secure)

### "Operation expired (max 5 minutes)"

Pending operations expire after 5 minutes for security.

**Solution:**
1. Call `vault_set` again to create a new operation
2. Approve within 5 minutes

### Server not starting

**Check if port 8091 is in use:**
```bash
lsof -i :8091
```

**Change the port:**
```python
# In your code
approval_server = ApprovalServer(port=9000)
```

### Lost credentials file

If you delete `~/.claude-vault/webauthn-credentials.json`:

1. Re-register your authenticator
2. Previous pending operations will fail
3. New operations work fine after re-registration

## Security Notes

### What's Stored Where

**In `~/.claude-vault/webauthn-credentials.json`:**
- ✅ Credential ID (public)
- ✅ Public key (public)
- ✅ Sign counter (public)
- ❌ NO private keys
- ❌ NO biometric data

**In your device's Secure Enclave/TPM:**
- 🔐 Private key (never leaves device)
- 🔐 Biometric templates (TouchID/Windows Hello)

**In memory (during approval):**
- Pending operations (max 5 minutes)
- WebAuthn challenges (single-use)

### Why This is Secure

**Prompt Injection Protection:**
- AI cannot fake TouchID/Windows Hello/YubiKey touch
- AI cannot access the browser approval page
- Even if AI calls phase 3 directly, approval check fails

**Man-in-the-Middle Protection:**
- WebAuthn uses challenge-response cryptography
- Each approval requires a unique challenge
- Replay attacks are prevented

**Phishing Protection:**
- Credentials are bound to `localhost` origin
- Cannot be used on other domains
- Browser enforces origin checks

## Advanced: Multiple Devices

To approve from multiple devices (e.g., Mac and Linux):

1. Register each device separately
2. Each gets its own credentials
3. All stored in same file (dict of user_id → credential)

Currently limited to single user (`vault-admin`). For multi-user:

```python
# Modify approval_server.py
user_id = f"vault-{username}"  # Instead of hardcoded "vault-admin"
```

## Comparison with Alternatives

| Method | Security | UX | Cross-Platform |
|--------|----------|-----|----------------|
| **WebAuthn** | ✅✅✅ | ✅✅✅ | ✅ |
| Terminal `input()` | ⚠️ (prompt injection) | ✅✅ | ✅ |
| Time delay | ⚠️ (AI can wait) | ⚠️ (slow) | ✅ |
| YubiKey only | ✅✅✅ | ⚠️ (hardware) | ✅ |
| TouchID only | ✅✅✅ | ✅✅✅ | ❌ (macOS) |

WebAuthn gives you **best of all worlds**: maximum security + great UX + works everywhere.

## Next Steps

1. ✅ Register your authenticator: `http://localhost:8091/register`
2. ✅ Test with a vault_set operation
3. ✅ Add to your workflow
4. 🔄 Re-register if you switch devices

Questions? Check the main [README.md](README.md) or [CLAUDE_VAULT_SETUP.md](../../docs/CLAUDE_VAULT_SETUP.md)

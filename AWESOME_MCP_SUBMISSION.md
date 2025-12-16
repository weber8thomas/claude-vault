# Awesome MCP Servers Submission

## Proposed Entry

**Category:** 🔒 Security

**Format:**
```markdown
- [weber8thomas/claude-vault](https://github.com/weber8thomas/claude-vault) 🐍 ☁️ 🏠 🍎 🪟 🐧 - AI-assisted HashiCorp Vault management with zero secrets sent to AI providers. Features tokenization, WebAuthn biometric approval for write operations, and Docker/docker-compose config migration.
```

## Emoji Legend

- 🐍 - Python codebase
- ☁️ - Cloud Service (talks to remote Vault API)
- 🏠 - Local Service (MCP server and approval server run locally)
- 🍎 🪟 🐧 - Cross-platform (macOS, Windows, Linux)

## Submission Process

### Step 1: Fork Repository
```bash
# Fork https://github.com/punkpeye/awesome-mcp-servers on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/awesome-mcp-servers.git
cd awesome-mcp-servers
```

### Step 2: Add Entry
1. Open `README.md`
2. Find the `### 🔒 <a name="security"></a>Security` section
3. Add the entry in alphabetical order (claude-vault goes near the beginning)
4. Entry should be:
```markdown
- [weber8thomas/claude-vault](https://github.com/weber8thomas/claude-vault) 🐍 ☁️ 🏠 🍎 🪟 🐧 - AI-assisted HashiCorp Vault management with zero secrets sent to AI providers. Features tokenization, WebAuthn biometric approval for write operations, and Docker/docker-compose config migration.
```

### Step 3: Create Pull Request
```bash
git checkout -b add-claude-vault
git add README.md
git commit -m "Add claude-vault MCP server"
git push origin add-claude-vault
```

Then create PR on GitHub with:
- **Title:** `Add claude-vault MCP server`
- **Description:**
```markdown
## New MCP Server: claude-vault

**Category:** Security

**Description:** AI-assisted HashiCorp Vault management with zero secrets sent to AI providers

**Key Features:**
- Zero-knowledge AI assistance - secrets tokenized before reaching Claude API
- WebAuthn biometric approval (TouchID/Windows Hello/YubiKey) for all write operations
- Natural language commands for secret migration and management
- Docker/docker-compose config scanning and migration
- Comprehensive audit trail and operation history

**Tech Stack:**
- Python 3.12+
- FastAPI for approval server
- WebAuthn for biometric security
- Model Context Protocol (MCP)

**PyPI:** https://pypi.org/project/claude-vault-mcp/
**Documentation:** https://github.com/weber8thomas/claude-vault#readme

**Checklist:**
- [x] Added to appropriate category (Security)
- [x] Alphabetically sorted
- [x] Correct emoji indicators
- [x] Concise, clear description
- [x] Project is open source (MIT license)
- [x] Has comprehensive README
- [x] Published to PyPI
```

## Validation Checklist

Before submitting, ensure:

- [x] **Open source license** - MIT ✓
- [x] **Comprehensive README** - Detailed installation, usage, and security docs ✓
- [x] **Published package** - Available on PyPI as `claude-vault-mcp` ✓
- [x] **Clear description** - Concise 1-2 sentence description ✓
- [x] **Correct emojis** - 🐍 ☁️ 🏠 🍎 🪟 🐧 ✓
- [x] **Alphabetical order** - Goes before "dkvdm/onepassword-mcp-server" ✓
- [x] **Working repository** - GitHub repo is public and accessible ✓
- [x] **Security category** - Fits perfectly in 🔒 Security section ✓

## Alternative Description Options

If the main description is too long, here are shorter variants:

**Variant 1 (Concise):**
```markdown
- [weber8thomas/claude-vault](https://github.com/weber8thomas/claude-vault) 🐍 ☁️ 🏠 🍎 🪟 🐧 - AI-assisted HashiCorp Vault management. Zero secrets sent to AI via tokenization. WebAuthn approval for write operations.
```

**Variant 2 (Focus on security):**
```markdown
- [weber8thomas/claude-vault](https://github.com/weber8thomas/claude-vault) 🐍 ☁️ 🏠 🍎 🪟 🐧 - Secure AI-assisted Vault management with secret tokenization (never sent to AI) and WebAuthn biometric approval for write operations.
```

**Variant 3 (Focus on use case):**
```markdown
- [weber8thomas/claude-vault](https://github.com/weber8thomas/claude-vault) 🐍 ☁️ 🏠 🍎 🪟 🐧 - Migrate Docker secrets to HashiCorp Vault with AI assistance. Secrets tokenized before reaching AI. WebAuthn approval required for writes.
```

Choose the variant that best fits the length and style of surrounding entries.

## Timeline

1. **After PyPI publish** - Submit to awesome-mcp-servers
2. **Estimated review time** - 1-7 days (community-maintained, varies)
3. **After merge** - Listed in official awesome list (high SEO value)

# Quick GitHub Token Setup for claude-vault

## Your Repository Type
- Repository: `weber8thomas/claude-vault`
- Type: **Personal repository** (not organization)
- Token needed: **Personal Access Token** from your profile

## Fast Setup (5 minutes)

### Step 1: Create Token (2 minutes)

1. **Open this URL directly:**
   👉 https://github.com/settings/tokens/new

2. **Fill in the form:**
   - **Note:** `Claude Code MCP - claude-vault`
   - **Expiration:** 90 days (or your preference)

3. **Select ONLY these 2 scopes:**
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (Update GitHub Action workflows)

4. **Click "Generate token"** at the bottom

5. **Copy the token** (starts with `ghp_...`)
   ⚠️ You can only see it once!

### Step 2: Add Token to Environment (2 minutes)

**Option A: Quick Test (temporary)**
```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_your_token_here"
```

**Option B: Permanent Setup (recommended)**
```bash
# Add to your shell config
echo 'export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_your_token_here"' >> ~/.bashrc
source ~/.bashrc
```

### Step 3: Update Config (1 minute)

Your `.mcp.json` is already configured! Just replace `<YOUR_TOKEN_HERE>` with your token:

**If using environment variable (Option B above - recommended):**
```json
{
  "mcpServers": {
    "github": {
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    }
  }
}
```

**If putting token directly in file (Option A - quick test):**
```json
{
  "mcpServers": {
    "github": {
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_actual_token"
      }
    }
  }
}
```

⚠️ **If using Option A:** Add `.mcp.json` to `.gitignore`:
```bash
echo ".mcp.json" >> .gitignore
```

### Step 4: Restart Claude Code

Completely exit and reopen Claude Code to load the new MCP server.

### Step 5: Test It

Ask Claude Code:
```
"List recent GitHub workflow runs for this repository"
```

## Troubleshooting

**Token doesn't work?**
- Check you selected `repo` and `workflow` scopes
- Verify token starts with `ghp_`
- Make sure there are no extra spaces when pasting

**MCP server not loading?**
```bash
# Test if npx works
npx -y @modelcontextprotocol/server-github --version
```

**Still having issues?**
See full guide: `docs/GITHUB_MCP_SETUP.md`

---

## Why Personal Token (Not Organization)?

Your repository `weber8thomas/claude-vault` is owned by your personal account, not a GitHub organization.

**Personal repository** = Use personal access token from your profile
**Organization repository** (like `mycompany/repo`) = Could use organization token or personal token with org access

Since yours is personal, you just need a token from:
https://github.com/settings/tokens

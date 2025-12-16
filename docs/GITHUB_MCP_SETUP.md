# GitHub MCP Server Setup Guide

This guide will help you set up the GitHub MCP server to enable Claude Code to interact with GitHub workflows, issues, pull requests, and more.

## Step 1: Create a GitHub Personal Access Token

1. **Go to GitHub Settings**
   - Navigate to: https://github.com/settings/tokens
   - Or: Click your profile → Settings → Developer settings → Personal access tokens → Tokens (classic)

2. **Generate New Token**
   - Click "Generate new token" → "Generate new token (classic)"
   - Give it a descriptive name: `Claude Code MCP - claude-vault`
   - Set expiration: Choose based on your preference (recommended: 90 days or No expiration for development)

3. **Select Required Scopes**

   For the GitHub MCP server to work with workflows and repository management, select these scopes:

   **Repository Access:**
   - ✅ `repo` (Full control of private repositories)
     - Includes: `repo:status`, `repo_deployment`, `public_repo`, `repo:invite`, `security_events`

   **Workflow Access:**
   - ✅ `workflow` (Update GitHub Action workflows)

   **Additional Recommended Scopes:**
   - ✅ `read:org` (Read organization membership)
   - ✅ `read:user` (Read user profile data)
   - ✅ `user:email` (Access user email addresses)

   **Optional (for advanced features):**
   - `admin:repo_hook` (for webhook management)
   - `read:discussion` (for discussions)
   - `read:packages` (for GitHub Packages)

4. **Generate and Copy Token**
   - Click "Generate token" at the bottom
   - **IMPORTANT:** Copy the token immediately - you won't be able to see it again!
   - Token format: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

## Step 2: Configure the MCP Server

You have two options for storing the token:

### Option A: Environment Variable (Recommended for Security)

1. **Add to your shell profile** (~/.bashrc, ~/.zshrc, or ~/.profile):
   ```bash
   export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_your_token_here"
   ```

2. **Apply changes:**
   ```bash
   source ~/.bashrc  # or ~/.zshrc
   ```

3. **Update .mcp.json** to reference the environment variable:
   ```json
   {
     "mcpServers": {
       "github": {
         "type": "stdio",
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-github"],
         "env": {
           "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
         }
       }
     }
   }
   ```

4. **Restart Claude Code** to pick up the new environment variable.

### Option B: Direct in Config (Quick Setup)

1. **Edit .mcp.json** and replace `<YOUR_TOKEN_HERE>`:
   ```json
   {
     "mcpServers": {
       "github": {
         "type": "stdio",
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-github"],
         "env": {
           "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_actual_token_here"
         }
       }
     }
   }
   ```

2. **IMPORTANT:** Add `.mcp.json` to `.gitignore` if using this method:
   ```bash
   echo ".mcp.json" >> .gitignore
   ```

## Step 3: Verify Installation

1. **Restart Claude Code** completely (exit and reopen)

2. **Test the connection** by asking Claude Code to:
   - "List recent workflow runs for this repository"
   - "Show me the status of the latest GitHub Actions"
   - "Check if there are any open pull requests"

3. **Check MCP server logs** if you encounter issues:
   ```bash
   # Claude Code typically logs MCP server output to:
   # ~/.claude/logs/ or check the Claude Code console
   ```

## Step 4: Security Best Practices

### Protect Your Token
- ✅ Never commit tokens to git repositories
- ✅ Use environment variables when possible
- ✅ Add `.mcp.json` to `.gitignore` if it contains secrets
- ✅ Rotate tokens periodically (every 90 days recommended)
- ✅ Use fine-grained tokens with minimal required permissions

### Fine-Grained Tokens (Alternative)

Instead of classic tokens, you can use fine-grained personal access tokens with more precise permissions:

1. Go to: https://github.com/settings/tokens?type=beta
2. Generate new token (fine-grained)
3. Select specific repositories: `weber8thomas/claude-vault`
4. Choose permissions:
   - **Actions:** Read and write
   - **Contents:** Read and write
   - **Metadata:** Read-only (required)
   - **Workflows:** Read and write
   - **Pull requests:** Read and write (if needed)

## Troubleshooting

### MCP Server Not Loading
```bash
# Test if npx can run the server
npx -y @modelcontextprotocol/server-github --help
```

### Token Permission Errors
- Verify you selected the `repo` and `workflow` scopes
- Check token hasn't expired: https://github.com/settings/tokens
- Regenerate token with correct permissions if needed

### Claude Code Can't Connect
- Check `.mcp.json` syntax is valid JSON
- Verify token is correctly set (no extra spaces/quotes)
- Restart Claude Code completely
- Check Claude Code logs for error messages

## Available GitHub MCP Tools

Once configured, you'll have access to:

- **Repository Operations:**
  - Create/update files, branches, commits
  - Search code, issues, pull requests
  - List/create issues and PRs

- **Workflow Operations:**
  - List workflow runs
  - Get workflow run details
  - Download workflow logs
  - Re-run workflows

- **Repository Information:**
  - Get repository details
  - List branches, tags, releases
  - View commit history

## Example Commands

After setup, try these commands with Claude Code:

```
"List all failed workflow runs in the last week"
"Show me the logs for the most recent release workflow"
"Check the status of workflows for commit 3fc1559"
"Create a new issue about the broken workflow"
"List all tags in this repository"
```

## Additional Resources

- GitHub MCP Server: https://github.com/modelcontextprotocol/servers/tree/main/src/github
- GitHub Token Docs: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- MCP Documentation: https://modelcontextprotocol.io/

---

**Need Help?** If you encounter issues, check:
1. Token has correct permissions
2. Token hasn't expired
3. Claude Code was fully restarted
4. `.mcp.json` is valid JSON

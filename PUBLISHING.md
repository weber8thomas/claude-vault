# Publishing Guide

This guide covers how to publish the `claude-vault-mcp` package to PyPI and the Smithery catalog.

## Prerequisites

### 1. PyPI Account Setup
1. Create account at https://pypi.org
2. Enable 2FA (required for publishing)
3. Generate API token:
   - Go to https://pypi.org/manage/account/token/
   - Create token with scope "Entire account" (or project-specific after first release)
   - Save the token (starts with `pypi-`)

### 2. GitHub Secret Configuration
Add the PyPI token to GitHub repository secrets:
1. Go to repository Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: Your PyPI API token (the full `pypi-...` string)

## Publishing to PyPI

### Automatic Publishing (Recommended)
The package is automatically published to PyPI when you create a GitHub release:

```bash
# Create and push a new version tag
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

The `.github/workflows/publish-pypi.yml` workflow will:
1. Build the package
2. Publish to PyPI
3. Make it available via `pip install claude-vault-mcp`

### Manual Publishing
For testing or manual releases:

```bash
cd packages/mcp-server

# Install build tools
pip install build twine

# Build the package
python -m build

# Check the package
twine check dist/*

# Upload to TestPyPI (for testing)
twine upload --repository testpypi dist/*

# Upload to PyPI (production)
twine upload dist/*
```

## Publishing to MCP Directories & Marketplaces

### Priority Directories (Recommended)

#### 1. Smithery.ai (Official - Start Here)
**Submission:**
1. Visit https://smithery.ai
2. Sign in with GitHub
3. Click "Submit MCP Server"
4. Provide repository URL: `https://github.com/weber8thomas/claude-vault`
5. Smithery reads `smithery.yaml` automatically

**Why prioritize:**
- Official Anthropic-maintained catalog
- Highest credibility
- Integration with Claude Desktop and Claude Code
- Version tracking and automatic updates

#### 2. Awesome MCP Servers (High Impact)
**Submission:**
See detailed guide in `AWESOME_MCP_SUBMISSION.md`

1. Fork https://github.com/punkpeye/awesome-mcp-servers
2. Add entry in Security section (🔒):
   ```markdown
   - [weber8thomas/claude-vault](https://github.com/weber8thomas/claude-vault) 🐍 ☁️ 🏠 🍎 🪟 🐧 - AI-assisted HashiCorp Vault management with zero secrets sent to AI providers. Features tokenization, WebAuthn biometric approval for write operations, and Docker/docker-compose config migration.
   ```
3. Submit pull request with detailed description

**Why prioritize:**
- Highly curated (quality signal)
- Massive GitHub visibility and SEO
- Trusted by developers
- High conversion to users

#### 3. mcp.so (Community Reach)
**Submission:**
See detailed guide in `MCP_SO_SUBMISSION.md`

1. Visit https://mcp.so
2. Click "Submit" and create GitHub issue
3. Provide server details with complete tool listings (see MCP_SO_SUBMISSION.md)
4. Server appears in 17K+ directory after review

**Why prioritize:**
- Largest community platform (17,000+ servers)
- Fast discovery and user ratings
- Comprehensive tool documentation increases visibility
- May automatically index after PyPI publish

### Optional Directories (Lower Priority)

- **mcpmarket.com** - Professional presentation, enterprise audience
- **PulseMCP** - Daily updates, 6,970+ servers
- **mcpservers.org** - Quality-focused curation

These typically auto-index from PyPI or GitHub, so active submission may not be necessary.

## Version Management

Before releasing, update version numbers:

1. **pyproject.toml**: Update `version = "X.Y.Z"`
2. **smithery.yaml**: Update `version: X.Y.Z`
3. Create git tag matching the version

### Version Numbering
Follow semantic versioning (semver):
- **Major (X)**: Breaking changes
- **Minor (Y)**: New features, backwards compatible
- **Patch (Z)**: Bug fixes, backwards compatible

Examples:
- `1.0.0` → `1.0.1`: Bug fix
- `1.0.1` → `1.1.0`: New feature (backward compatible)
- `1.1.0` → `2.0.0`: Breaking change

## Release Checklist

### Pre-Release
- [ ] Update version in `packages/mcp-server/pyproject.toml`
- [ ] Update version in `smithery.yaml`
- [ ] Update CHANGELOG.md (if exists)
- [ ] Test package locally: `pip install -e packages/mcp-server`
- [ ] Test approval server: `vault-approve-server`
- [ ] Commit version changes
- [ ] Create and push git tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`

### Release Validation
- [ ] Verify GitHub Actions workflow completes
- [ ] Check package on PyPI: https://pypi.org/project/claude-vault-mcp/
- [ ] Test installation: `uvx --from claude-vault-mcp vault-approve-server --help`
- [ ] Test in clean environment with `.mcp.json` configuration

### Distribution (Priority Directories - First Release Only)
- [ ] Submit to Smithery.ai (official catalog) - **Required**
- [ ] Submit PR to awesome-mcp-servers (GitHub list) - **High priority**
- [ ] Submit to mcp.so (community platform) - **Recommended**

**Note:** Other directories (mcpmarket, PulseMCP, mcpservers.org) typically auto-index from PyPI/GitHub

## Post-Release

After publishing:
1. **Test installation** in a clean environment
2. **Update documentation** if installation method changed
3. **Submit to MCP directories** (first release only, see checklist above)
4. **Announce release**:
   - GitHub Discussions
   - Twitter/X (with #MCP #Claude hashtags)
   - Reddit (r/ClaudeAI)
   - Dev.to or Medium (optional)
5. **Monitor** for installation issues and questions
6. **Update directory listings** if major changes (features, categories)

## Troubleshooting

### Build Fails
```bash
# Clean previous builds
rm -rf packages/mcp-server/dist packages/mcp-server/build packages/mcp-server/*.egg-info

# Rebuild
cd packages/mcp-server
python -m build
```

### Upload Fails
- Check PYPI_API_TOKEN is set correctly in GitHub secrets
- Verify token has correct permissions
- Ensure version number hasn't been used before (PyPI doesn't allow re-uploading same version)

### Package Not Found After Upload
- Wait a few minutes for PyPI to index
- Check https://pypi.org/project/claude-vault-mcp/ exists
- Try: `pip install --upgrade claude-vault-mcp`

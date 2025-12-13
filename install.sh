#!/bin/bash
# Claude-Vault Installation Script
# Simple installation to make claude-vault available system-wide

set -e

PREFIX="${PREFIX:-/usr/local/bin}"
GITHUB_REPO="weber8thomas/claude-vault"
GITHUB_BRANCH="main"

echo "Installing claude-vault to $PREFIX..."

# Check if we have write permission
if [ ! -w "$PREFIX" ]; then
    echo "Error: No write permission to $PREFIX"
    echo "Please run with sudo or set PREFIX to a writable location:"
    echo "  sudo ./install.sh"
    echo "  PREFIX=\$HOME/.local/bin ./install.sh"
    exit 1
fi

# Determine installation method
if [ -d "bin" ]; then
    # Local installation (from cloned repo)
    echo "Installing from local directory..."
    cp -v bin/* "$PREFIX/"
else
    # Remote installation (piped from curl)
    echo "Downloading scripts from GitHub..."
    TEMP_DIR=$(mktemp -d)
    trap "rm -rf $TEMP_DIR" EXIT

    # Download all scripts
    SCRIPTS=(
        "claude-vault"
        "claude-vault-get.sh"
        "claude-vault-list.sh"
        "claude-vault-register.sh"
        "vault-login-simple.sh"
        "vault-status.sh"
        "vault-logout.sh"
        "inject-secrets.sh"
    )

    for script in "${SCRIPTS[@]}"; do
        echo "Downloading $script..."
        curl -fsSL "https://raw.githubusercontent.com/$GITHUB_REPO/$GITHUB_BRANCH/bin/$script" -o "$TEMP_DIR/$script"
    done

    echo "Installing scripts..."
    cp -v "$TEMP_DIR"/* "$PREFIX/"
fi

# Make executable
echo "Setting permissions..."
chmod +x "$PREFIX"/claude-vault*
chmod +x "$PREFIX"/vault-*
chmod +x "$PREFIX"/inject-secrets.sh

echo ""
echo "✅ Installation complete!"
echo ""
echo "claude-vault is now available in your PATH."
echo "Try: claude-vault --help"

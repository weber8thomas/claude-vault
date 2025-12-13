#!/bin/bash
# Claude-Vault Installation Script
# Simple installation to make claude-vault available system-wide

set -e

PREFIX="${PREFIX:-/usr/local/bin}"

echo "Installing claude-vault to $PREFIX..."

# Check if we have write permission
if [ ! -w "$PREFIX" ]; then
    echo "Error: No write permission to $PREFIX"
    echo "Please run with sudo or set PREFIX to a writable location:"
    echo "  sudo ./install.sh"
    echo "  PREFIX=\$HOME/.local/bin ./install.sh"
    exit 1
fi

# Copy all scripts
echo "Copying scripts..."
cp -v bin/* "$PREFIX/"

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

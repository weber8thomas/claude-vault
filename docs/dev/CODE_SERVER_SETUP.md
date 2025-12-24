# Code-Server Setup with Vault

Instructions for setting up HashiCorp Vault and mcp-vault in a code-server container environment.

## Custom Init Script

To automatically install Vault binary and mcp-vault package when code-server starts, create a custom initialization script.

### File: `custom-cont-init.d/20-install-vault`

```bash
#!/usr/bin/with-contenv bash

echo "*** Installing HashiCorp Vault ***"

# Vault version to install
VAULT_VERSION="1.18.3"
ARCH=$(dpkg --print-architecture)

# Download and install Vault
echo "Downloading Vault ${VAULT_VERSION} for ${ARCH}..."
cd /tmp
wget -q "https://releases.hashicorp.com/vault/${VAULT_VERSION}/vault_${VAULT_VERSION}_linux_${ARCH}.zip"

if [ ! -f "vault_${VAULT_VERSION}_linux_${ARCH}.zip" ]; then
    echo "ERROR: Failed to download Vault"
    exit 1
fi

# Extract and install
apt-get update && apt-get install -y unzip
unzip -q "vault_${VAULT_VERSION}_linux_${ARCH}.zip"
mv vault /usr/local/bin/vault
chmod +x /usr/local/bin/vault

# Cleanup
rm -f "vault_${VAULT_VERSION}_linux_${ARCH}.zip"

# Verify installation
if vault version > /dev/null 2>&1; then
    echo "*** Vault $(vault version | head -1) installed successfully ***"
else
    echo "ERROR: Vault installation verification failed"
    exit 1
fi

# Enable command completion for abc user
if [ -d /home/abc ]; then
    su - abc -c 'vault -autocomplete-install 2>/dev/null || true'
fi

# Install mcp-vault package (provides vault-approve-server command)
echo "Installing mcp-vault package..."
if [ -d /workspace/mcp-vault/packages/mcp-server ]; then
    # Install from local dev version if available
    pip3 install --break-system-packages -e /workspace/mcp-vault/packages/mcp-server
    echo "Installed mcp-vault from local development version"
else
    # Install from PyPI
    pip3 install --break-system-packages mcp-vault
    echo "Installed mcp-vault from PyPI"
fi

# Verify vault-approve-server is available
if which vault-approve-server > /dev/null 2>&1; then
    echo "*** vault-approve-server command is available ***"
else
    echo "WARNING: vault-approve-server command not found in PATH"
fi

echo "*** Vault installation complete ***"
```

## Installation Instructions

### 1. Create the Script

```bash
# Navigate to your code-server directory
cd /path/to/code-server

# Create the custom init directory if it doesn't exist
mkdir -p custom-cont-init.d

# Create the install script
nano custom-cont-init.d/20-install-vault
# Paste the script content above

# Make it executable
chmod +x custom-cont-init.d/20-install-vault
```

### 2. Mount in Docker Compose

Make sure your `docker-compose.yml` has the custom-cont-init.d directory mounted:

```yaml
services:
  code-server:
    image: lscr.io/linuxserver/code-server
    volumes:
      - ./custom-cont-init.d:/custom-cont-init.d
      # ... other volumes
```

### 3. Restart Code-Server

```bash
docker-compose restart
```

The init script will run automatically when the container starts.

### 4. Verify Installation

Once the container is running, exec into it and verify:

```bash
# Exec into container
docker exec -it code-server bash

# Check Vault
vault version
# Should show: Vault v1.18.3 (...)

# Check vault-approve-server
which vault-approve-server
# Should show: /usr/local/bin/vault-approve-server

# Or check with:
vault-approve-server --help
```

## What Gets Installed

1. **HashiCorp Vault CLI**
   - Binary: `/usr/local/bin/vault`
   - Version: 1.18.3 (configurable in script)
   - Includes autocomplete for zsh/bash

2. **mcp-vault Package**
   - Installed via pip
   - Provides `vault-approve-server` command
   - Installed from local dev if `/workspace/mcp-vault` exists
   - Otherwise installed from PyPI

## Customization

### Change Vault Version

Edit the `VAULT_VERSION` variable in the script:

```bash
VAULT_VERSION="1.19.0"  # Update to desired version
```

### Install Additional Tools

Add more commands to the script after the Vault installation:

```bash
# Install vault-session CLI (if separate package)
pip3 install --break-system-packages vault-session

# Install other HashiCorp tools
apt-get install -y terraform
```

## Troubleshooting

### Script Not Running

- Check file is executable: `ls -la custom-cont-init.d/20-install-vault`
- Check container logs: `docker logs code-server`
- Scripts run in numerical order (10-*, 20-*, etc.)

### Vault Not Found After Install

- Check PATH: `echo $PATH`
- Vault should be in `/usr/local/bin`
- Try absolute path: `/usr/local/bin/vault version`

### vault-approve-server Not Found

- Check pip installation: `pip3 list | grep mcp-vault`
- Check if binary exists: `find /usr/local -name vault-approve-server`
- May need to restart shell or source profile

### Permission Issues

- Init scripts run as root during container startup
- User `abc` is the default code-server user
- Use `su - abc -c 'command'` to run as user in script

## Alternative: Manual Installation

If you don't want to use init scripts, manually install in the container:

```bash
# Install Vault
wget https://releases.hashicorp.com/vault/1.18.3/vault_1.18.3_linux_amd64.zip
unzip vault_1.18.3_linux_amd64.zip
sudo mv vault /usr/local/bin/
vault version

# Install mcp-vault
pip install mcp-vault
vault-approve-server --help
```

## Related Documentation

- [VIDEO_SCRIPT.md](../../examples/test-service/VIDEO_SCRIPT.md) - Demo recording setup
- [WEBAUTHN_SETUP.md](../../packages/mcp-server/WEBAUTHN_SETUP.md) - WebAuthn configuration
- [README.md](../../README.md) - Main mcp-vault documentation

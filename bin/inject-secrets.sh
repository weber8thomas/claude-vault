#!/bin/bash
# Generic script to inject secrets from HashiCorp Vault to service configs
# Supports both .env and secrets.yaml formats
#
# Usage:
#   ./scripts/inject-secrets.sh <service-name> [output-format]
#
# Examples:
#   ./scripts/inject-secrets.sh esphome yaml
#   ./scripts/inject-secrets.sh authentik env
#   ./scripts/inject-secrets.sh authentik  # auto-detects format

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
SERVICE_NAME="${1:-}"
OUTPUT_FORMAT="${2:-auto}"

if [ -z "$SERVICE_NAME" ]; then
    echo -e "${RED}❌ Error: Service name required${NC}"
    echo ""
    echo "Usage: $0 <service-name> [output-format]"
    echo ""
    echo "Examples:"
    echo "  $0 esphome yaml"
    echo "  $0 authentik env"
    echo "  $0 authentik  # auto-detects format"
    echo ""
    exit 1
fi

# Determine service directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$REPO_ROOT/$SERVICE_NAME"

if [ ! -d "$SERVICE_DIR" ]; then
    echo -e "${RED}❌ Error: Service directory not found: $SERVICE_DIR${NC}"
    exit 1
fi

# Auto-detect output format if not specified
if [ "$OUTPUT_FORMAT" == "auto" ]; then
    if [ -f "$SERVICE_DIR/.env.example" ]; then
        OUTPUT_FORMAT="env"
        OUTPUT_FILE="$SERVICE_DIR/.env"
    elif [ -f "$SERVICE_DIR/config/secrets.yaml.example" ] || [ "$SERVICE_NAME" == "esphome" ]; then
        OUTPUT_FORMAT="yaml"
        OUTPUT_FILE="$SERVICE_DIR/config/secrets.yaml"
    else
        echo -e "${RED}❌ Error: Cannot auto-detect format. Please specify 'env' or 'yaml'${NC}"
        exit 1
    fi
elif [ "$OUTPUT_FORMAT" == "yaml" ]; then
    OUTPUT_FILE="$SERVICE_DIR/config/secrets.yaml"
elif [ "$OUTPUT_FORMAT" == "env" ]; then
    OUTPUT_FILE="$SERVICE_DIR/.env"
else
    echo -e "${RED}❌ Error: Invalid format '$OUTPUT_FORMAT'. Use 'env' or 'yaml'${NC}"
    exit 1
fi

# Vault configuration
VAULT_ADDR="${VAULT_ADDR:-}"
VAULT_TOKEN="${VAULT_TOKEN:-}"

echo -e "${BLUE}🔐 Secrets Injection from Vault${NC}"
echo "========================================"
echo "Service: $SERVICE_NAME"
echo "Format: $OUTPUT_FORMAT"
echo "Output: $OUTPUT_FILE"
echo ""

# Check if Vault token is set
if [ -z "$VAULT_TOKEN" ]; then
    echo -e "${RED}❌ Error: VAULT_TOKEN environment variable is not set${NC}"
    echo ""
    echo "Please set your Vault token:"
    echo "  export VAULT_TOKEN='your_vault_token'"
    echo ""
    echo "Get token from Vault UI → F12 → Local Storage → vault:token"
    exit 1
fi

# Set default Vault address if not set
if [ -z "$VAULT_ADDR" ]; then
    VAULT_ADDR="http://localhost:8200"
    echo -e "${YELLOW}⚠️  Using default VAULT_ADDR: $VAULT_ADDR${NC}"
fi

# Fetch secrets from Vault
echo "📥 Fetching secrets from Vault..."
VAULT_PATH="secret/data/proxmox-services/$SERVICE_NAME"  # pragma: allowlist secret
SECRETS_JSON=$(curl -sk \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    "$VAULT_ADDR/v1/$VAULT_PATH" | jq -r '.data.data')

if [ "$SECRETS_JSON" == "null" ] || [ -z "$SECRETS_JSON" ]; then
    echo -e "${RED}❌ Failed to fetch secrets from Vault${NC}"
    echo "Please check:"
    echo "  1. VAULT_TOKEN is valid"
    echo "  2. You have access to $VAULT_PATH"
    echo "  3. Vault is accessible at $VAULT_ADDR"
    exit 1
fi

# Backup existing file if it exists
if [ -f "$OUTPUT_FILE" ]; then
    BACKUP_FILE="$OUTPUT_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}⚠️  Backing up existing file to: $(basename $BACKUP_FILE)${NC}"
    cp "$OUTPUT_FILE" "$BACKUP_FILE"
fi

# Create output directory if needed
OUTPUT_DIR="$(dirname "$OUTPUT_FILE")"
mkdir -p "$OUTPUT_DIR"

# Generate output file based on format
echo "📝 Generating $OUTPUT_FORMAT file..."

if [ "$OUTPUT_FORMAT" == "yaml" ]; then
    # Generate secrets.yaml
    cat > "$OUTPUT_FILE" << HEADER
# $SERVICE_NAME Secrets File
# Generated automatically from HashiCorp Vault
# DO NOT COMMIT THIS FILE TO GIT!
#
# To regenerate: $REPO_ROOT/scripts/inject-secrets.sh $SERVICE_NAME yaml
#
HEADER
    echo "$SECRETS_JSON" | jq -r 'to_entries | .[] | "\(.key): \"\(.value)\""' >> "$OUTPUT_FILE"

elif [ "$OUTPUT_FORMAT" == "env" ]; then
    # Generate .env
    cat > "$OUTPUT_FILE" << HEADER
# $SERVICE_NAME Environment Variables
# Generated automatically from HashiCorp Vault
# DO NOT COMMIT THIS FILE TO GIT!
#
# To regenerate: $REPO_ROOT/scripts/inject-secrets.sh $SERVICE_NAME env
#
HEADER
    echo "$SECRETS_JSON" | jq -r 'to_entries | .[] | "\(.key)=\(.value)"' >> "$OUTPUT_FILE"
fi

# Verify the file was created
if [ ! -f "$OUTPUT_FILE" ]; then
    echo -e "${RED}❌ Failed to create output file${NC}"
    exit 1
fi

# Show summary
SECRET_COUNT=$(echo "$SECRETS_JSON" | jq -r 'keys | length')
echo ""
echo -e "${GREEN}✅ Success!${NC}"
echo "Generated $OUTPUT_FILE with $SECRET_COUNT secrets"
echo ""
echo "Secrets included:"
echo "$SECRETS_JSON" | jq -r 'keys[]' | sed 's/^/  - /'
echo ""
echo -e "${YELLOW}⚠️  Remember: This file should NOT be committed to Git${NC}"
echo "Make sure it's in .gitignore"

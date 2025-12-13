#!/bin/bash
# Get secret values from Vault for Claude Code
# This script displays actual secret values (use with caution)
#
# Usage:
#   claude-vault get <service-name> [key-name]
#
# Examples:
#   claude-vault get esphome              # Show all secrets for esphome
#   claude-vault get esphome wifi_ssid    # Show only wifi_ssid value

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VAULT_ADDR="${VAULT_ADDR:-https://vault.example.com}"

# Parse arguments
SERVICE_NAME="${1:-}"
KEY_NAME="${2:-}"

if [ -z "$SERVICE_NAME" ]; then
    echo -e "${RED}❌ Error: Service name required${NC}"
    echo ""
    echo "Usage: $0 <service-name> [key-name]"
    echo ""
    echo "Examples:"
    echo "  $0 esphome              # Show all secrets"
    echo "  $0 esphome wifi_ssid    # Show only wifi_ssid"
    echo ""
    exit 1
fi

# Function to check session validity
check_session() {
    if [ -z "$VAULT_TOKEN" ]; then
        echo -e "${RED}❌ Error: No active Vault session${NC}"
        echo ""
        echo "Please authenticate first:"
        echo -e "  ${GREEN}source claude-vault login${NC}"
        echo ""
        exit 1
    fi

    # Check token expiry if tracked
    if [ -n "$VAULT_TOKEN_EXPIRY" ]; then
        CURRENT_TIME=$(date +%s)
        if [ "$CURRENT_TIME" -ge "$VAULT_TOKEN_EXPIRY" ]; then
            echo -e "${RED}❌ Error: Vault session expired${NC}"
            echo ""
            EXPIRED_AT=$(date -d "@$VAULT_TOKEN_EXPIRY" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || date -r "$VAULT_TOKEN_EXPIRY" "+%Y-%m-%d %H:%M:%S")
            echo "Session expired at: $EXPIRED_AT"
            echo ""
            echo "Please re-authenticate:"
            echo -e "  ${GREEN}source claude-vault login${NC}"
            echo ""
            exit 1
        fi

        # Warn if expiring soon
        REMAINING=$((VAULT_TOKEN_EXPIRY - CURRENT_TIME))
        if [ "$REMAINING" -lt 300 ]; then # Less than 5 minutes
            REMAINING_MIN=$((REMAINING / 60))
            echo -e "${YELLOW}⚠️  Session expires in ${REMAINING_MIN} minutes${NC}"
            echo ""
        fi
    fi
}

# Check session validity
check_session

echo -e "${BLUE}🔐 Retrieving secrets for: ${CYAN}$SERVICE_NAME${NC}"
echo "=========================================="
echo ""

# Get secret data
RESPONSE=$(curl -sk \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    "$VAULT_ADDR/v1/secret/data/proxmox-services/$SERVICE_NAME")

# Check if service exists
if echo "$RESPONSE" | jq -e '.errors' >/dev/null 2>&1; then
    echo -e "${RED}❌ Service '$SERVICE_NAME' not found in Vault${NC}"
    echo ""
    echo "To list available services, use:"
    echo "  claude-vault list"
    exit 1
fi

SECRET_DATA=$(echo "$RESPONSE" | jq -r '.data.data')

if [ -n "$KEY_NAME" ]; then
    # Show specific key
    VALUE=$(echo "$SECRET_DATA" | jq -r --arg key "$KEY_NAME" '.[$key] // empty')

    if [ -z "$VALUE" ]; then
        echo -e "${RED}❌ Key '$KEY_NAME' not found in $SERVICE_NAME${NC}"
        echo ""
        echo "Available keys:"
        echo "$SECRET_DATA" | jq -r 'keys[]' | while read -r key; do
            echo "  • $key"
        done
        exit 1
    fi

    echo -e "${GREEN}$KEY_NAME:${NC}"
    echo "$VALUE"
else
    # Show all secrets
    echo -e "${YELLOW}⚠️  WARNING: Displaying secret values!${NC}"
    echo ""
    echo -e "${GREEN}Secrets for $SERVICE_NAME:${NC}"
    echo ""
    echo "$SECRET_DATA" | jq -r 'to_entries[] | "  \(.key): \(.value)"'
fi

echo ""

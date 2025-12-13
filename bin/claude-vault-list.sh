#!/bin/bash
# List secrets from Vault for Claude Code
# This script uses AppRole authentication to list available secrets
#
# Usage:
#   claude-vault list [service-name]
#
# Examples:
#   claude-vault list              # List all services
#   claude-vault list esphome      # List esphome secrets

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

# Function to list all services
list_all_services() {
    echo -e "${BLUE}📋 Listing all services in Vault${NC}"
    echo "=========================================="
    echo ""

    RESPONSE=$(curl -sk \
        --header "X-Vault-Token: $VAULT_TOKEN" \
        "$VAULT_ADDR/v1/secret/metadata/proxmox-services?list=true")

    SERVICES=$(echo "$RESPONSE" | jq -r '.data.keys[]?' 2>/dev/null)

    if [ -z "$SERVICES" ]; then
        echo -e "${YELLOW}⚠️  No services found in Vault${NC}"
        echo ""
        echo "To register a new service, use:"
        echo "  claude-vault set <service-name> key=value ..."
        return
    fi

    echo -e "${GREEN}Found services:${NC}"
    echo "$SERVICES" | while read -r service; do
        echo -e "  ${CYAN}•${NC} $service"
    done
    echo ""
}

# Function to list secrets for a specific service
list_service_secrets() {
    local service="$1"

    echo -e "${BLUE}📋 Listing secrets for service: ${CYAN}$service${NC}"
    echo "=========================================="
    echo ""

    # Get secret data
    RESPONSE=$(curl -sk \
        --header "X-Vault-Token: $VAULT_TOKEN" \
        "$VAULT_ADDR/v1/secret/data/proxmox-services/$service")

    # Check if service exists
    if echo "$RESPONSE" | jq -e '.errors' >/dev/null 2>&1; then
        echo -e "${RED}❌ Service '$service' not found in Vault${NC}"
        echo ""
        echo "To register this service, use:"
        echo "  claude-vault set $service key=value ..."
        exit 1
    fi

    # Get metadata
    METADATA_RESPONSE=$(curl -sk \
        --header "X-Vault-Token: $VAULT_TOKEN" \
        "$VAULT_ADDR/v1/secret/metadata/proxmox-services/$service")

    # Extract information
    SECRET_DATA=$(echo "$RESPONSE" | jq -r '.data.data')
    CURRENT_VERSION=$(echo "$METADATA_RESPONSE" | jq -r '.data.current_version')
    CREATED_TIME=$(echo "$METADATA_RESPONSE" | jq -r '.data.created_time')
    UPDATED_TIME=$(echo "$METADATA_RESPONSE" | jq -r '.data.updated_time')

    echo -e "${GREEN}Metadata:${NC}"
    echo "  Version: $CURRENT_VERSION"
    echo "  Created: $CREATED_TIME"
    echo "  Updated: $UPDATED_TIME"
    echo ""

    echo -e "${GREEN}Secrets (keys only):${NC}"
    echo "$SECRET_DATA" | jq -r 'keys[]' | while read -r key; do
        echo -e "  ${CYAN}•${NC} $key"
    done
    echo ""

    echo -e "${YELLOW}💡 To view secret values:${NC}"
    echo "  claude-vault get $service"
    echo ""
}

# Main script
SERVICE_NAME="${1:-}"

# Check session validity
check_session

if [ -z "$SERVICE_NAME" ]; then
    # List all services
    list_all_services
else
    # List specific service secrets
    list_service_secrets "$SERVICE_NAME"
fi

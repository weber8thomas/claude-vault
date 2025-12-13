#!/bin/bash
# Check Vault session status and token validity
#
# Usage:
#   ./scripts/vault-status.sh

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

VAULT_ADDR="${VAULT_ADDR:-https://vault.example.com}"

echo -e "${BLUE}🔍 Vault Session Status${NC}"
echo "========================="
echo ""

# Check if token is set
if [ -z "$VAULT_TOKEN" ]; then
    echo -e "${RED}❌ Not authenticated${NC}"
    echo ""
    echo "No active Vault session found."
    echo ""
    echo "To authenticate, run:"
    echo -e "  ${GREEN}source claude-vault login${NC}"
    echo ""
    exit 1
fi

# Check token expiry
if [ -n "$VAULT_TOKEN_EXPIRY" ]; then
    CURRENT_TIME=$(date +%s)

    if [ "$CURRENT_TIME" -ge "$VAULT_TOKEN_EXPIRY" ]; then
        echo -e "${RED}❌ Session expired${NC}"
        echo ""
        EXPIRED_AT=$(date -d "@$VAULT_TOKEN_EXPIRY" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || date -r "$VAULT_TOKEN_EXPIRY" "+%Y-%m-%d %H:%M:%S")
        echo "Token expired at: $EXPIRED_AT"
        echo ""
        echo "To re-authenticate:"
        echo -e "  ${GREEN}source claude-vault login${NC}"
        echo ""
        exit 1
    fi

    REMAINING=$((VAULT_TOKEN_EXPIRY - CURRENT_TIME))
    REMAINING_MIN=$((REMAINING / 60))
    REMAINING_SEC=$((REMAINING % 60))
    EXPIRY_DISPLAY=$(date -d "@$VAULT_TOKEN_EXPIRY" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || date -r "$VAULT_TOKEN_EXPIRY" "+%Y-%m-%d %H:%M:%S")
fi

# Validate token with Vault
echo -e "${CYAN}Checking token validity...${NC}"
echo ""

TOKEN_INFO=$(curl -sk \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    "$VAULT_ADDR/v1/auth/token/lookup-self" 2>/dev/null)

if ! echo "$TOKEN_INFO" | jq -e '.data' >/dev/null 2>&1; then
    echo -e "${RED}❌ Token invalid or revoked${NC}"
    echo ""
    echo "Your session may have been revoked or the token is invalid."
    echo ""
    echo "To re-authenticate:"
    echo -e "  ${GREEN}source claude-vault login${NC}"
    echo ""
    exit 1
fi

# Extract token details
DISPLAY_NAME=$(echo "$TOKEN_INFO" | jq -r '.data.display_name // "unknown"')
POLICIES=$(echo "$TOKEN_INFO" | jq -r '.data.policies | join(", ")')
CREATION_TIME=$(echo "$TOKEN_INFO" | jq -r '.data.creation_time')
ENTITY_ID=$(echo "$TOKEN_INFO" | jq -r '.data.entity_id // "none"')
RENEWABLE=$(echo "$TOKEN_INFO" | jq -r '.data.renewable')

echo -e "${GREEN}✅ Session Active${NC}"
echo "=================================================="
echo ""
echo "User: $DISPLAY_NAME"
echo "Policies: $POLICIES"
echo "Created: $(date -d "$CREATION_TIME" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "$CREATION_TIME")"
echo "Renewable: $RENEWABLE"
echo ""

if [ -n "$VAULT_TOKEN_EXPIRY" ]; then
    if [ "$REMAINING_MIN" -lt 5 ]; then
        echo -e "${YELLOW}⚠️  Expiring Soon: ${REMAINING_MIN}m ${REMAINING_SEC}s${NC}"
    else
        echo -e "${GREEN}Expires In: ${REMAINING_MIN}m ${REMAINING_SEC}s${NC}"
    fi
    echo "Expiry Time: $EXPIRY_DISPLAY"
    echo ""
fi

# Test read access
echo -e "${CYAN}Testing Vault access...${NC}"
echo ""

LIST_RESPONSE=$(curl -sk \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    "$VAULT_ADDR/v1/secret/metadata/proxmox-services?list=true" 2>/dev/null)

if echo "$LIST_RESPONSE" | jq -e '.data.keys' >/dev/null 2>&1; then
    SERVICE_COUNT=$(echo "$LIST_RESPONSE" | jq -r '.data.keys | length')
    echo -e "${GREEN}✅ Read access verified${NC}"
    echo "Services accessible: $SERVICE_COUNT"
    echo ""

    if [ "$SERVICE_COUNT" -gt 0 ]; then
        echo "Available services:"
        echo "$LIST_RESPONSE" | jq -r '.data.keys[]' | head -5 | while read -r service; do
            echo "  • $service"
        done

        if [ "$SERVICE_COUNT" -gt 5 ]; then
            echo "  ... and $((SERVICE_COUNT - 5)) more"
        fi
        echo ""
    fi
else
    echo -e "${YELLOW}⚠️  Limited access or no services found${NC}"
    echo ""
fi

# Summary
echo "=================================================="
echo -e "${GREEN}Session Summary:${NC}"
echo "=================================================="
echo ""

if [ -n "$REMAINING_MIN" ]; then
    if [ "$REMAINING_MIN" -lt 10 ]; then
        echo -e "${YELLOW}⚠️  Session expires soon - consider re-authenticating${NC}"
        echo ""
        echo "To extend session:"
        echo -e "  ${GREEN}source claude-vault login${NC}"
    else
        echo -e "${GREEN}✅ Session active and valid${NC}"
        echo ""
        echo "You can now use Claude Code to:"
        echo "  • List secrets: ./scripts/claude-vault list"
        echo "  • Get secrets: ./scripts/claude-vault get <service>"
        echo "  • Register secrets: ./scripts/claude-vault set <service> key=val"
    fi
else
    echo -e "${YELLOW}⚠️  Session expiry not tracked${NC}"
    echo ""
    echo "Token is valid but expiry time unknown."
fi

echo ""

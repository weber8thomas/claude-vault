#!/bin/bash
# Simplified Vault Login - Direct token input
# Usage: source ./scripts/vault-login-simple.sh

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

VAULT_ADDR="${VAULT_ADDR:-https://vault.example.com}"

echo -e "${BLUE}🔐 Vault Login${NC}"
echo "=============="
echo ""

# Check if already authenticated
if [ -n "$VAULT_TOKEN" ] && [ -n "$VAULT_TOKEN_EXPIRY" ]; then
    CURRENT_TIME=$(date +%s)
    if [ "$CURRENT_TIME" -lt "$VAULT_TOKEN_EXPIRY" ]; then
        REMAINING=$((VAULT_TOKEN_EXPIRY - CURRENT_TIME))
        REMAINING_MIN=$((REMAINING / 60))
        echo -e "${GREEN}✅ Already authenticated (${REMAINING_MIN} minutes remaining)${NC}"
        echo ""
        return 0 2>/dev/null || exit 0
    fi
fi

echo -e "${CYAN}Step 1: Open this URL in your browser:${NC}"
echo ""
echo "  ${VAULT_ADDR}/ui/vault/auth?with=oidc"
echo ""
echo -e "${CYAN}Step 2: In Vault UI:${NC}"
echo "  • Click 'Sign in with OIDC'"
echo "  • Authenticate via Authentik (use your security key/MFA)"
echo "  • Click your username (top left)"
echo "  • Click 'Copy token'"
echo ""
echo -e "${CYAN}Step 3: Paste your token below:${NC}"
echo ""
# Compatible with both bash and zsh
if [ -n "$ZSH_VERSION" ]; then
    read "VAULT_TOKEN?Token: "
else
    read -p "Token: " VAULT_TOKEN
fi

if [ -z "$VAULT_TOKEN" ]; then
    echo -e "${RED}❌ No token provided${NC}"
    return 1 2>/dev/null || exit 1
fi

# Validate token
echo ""
echo -e "${BLUE}Validating token...${NC}"

TOKEN_INFO=$(curl -sk \
    --max-time 10 \
    --connect-timeout 5 \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    "$VAULT_ADDR/v1/auth/token/lookup-self" 2>/dev/null)

# If curl failed completely, TOKEN_INFO will be empty
if [ -z "$TOKEN_INFO" ]; then
    echo -e "${RED}❌ Connection error${NC}"
    echo ""
    echo "Could not reach Vault at: $VAULT_ADDR"
    return 1 2>/dev/null || exit 1
fi

# Check for errors in response
if echo "$TOKEN_INFO" | jq -e '.errors' >/dev/null 2>&1; then
    echo -e "${RED}❌ Invalid token${NC}"
    echo ""
    echo "Vault error:"
    echo "$TOKEN_INFO" | jq -r '.errors[]' 2>/dev/null
    echo ""
    return 1 2>/dev/null || exit 1
fi

# Extract token info
DISPLAY_NAME=$(echo "$TOKEN_INFO" | jq -r '.data.display_name // "unknown"')
POLICIES=$(echo "$TOKEN_INFO" | jq -r '.data.policies | join(", ")')
TOKEN_TTL=$(echo "$TOKEN_INFO" | jq -r '.data.ttl // 3600')

# Verify we got valid data
if [ "$DISPLAY_NAME" = "unknown" ] || [ -z "$DISPLAY_NAME" ]; then
    echo -e "${RED}❌ Could not parse token info${NC}"
    echo ""
    echo "Response:"
    echo "$TOKEN_INFO" | jq . 2>/dev/null || echo "$TOKEN_INFO"
    echo ""
    return 1 2>/dev/null || exit 1
fi

# Calculate expiry (cap at 1 hour)
EXPIRY_SECONDS=$((TOKEN_TTL))
if [ "$EXPIRY_SECONDS" -gt 3600 ]; then
    EXPIRY_SECONDS=3600
fi

EXPIRY_TIME=$(($(date +%s) + EXPIRY_SECONDS))

# Export variables
export VAULT_ADDR="$VAULT_ADDR"
export VAULT_TOKEN="$VAULT_TOKEN"
export VAULT_TOKEN_EXPIRY="$EXPIRY_TIME"

echo ""
echo -e "${GREEN}✅ Authentication Successful!${NC}"
echo "=============================================="
echo ""
echo "User: $DISPLAY_NAME"
echo "Policies: $POLICIES"
echo "Session: $((EXPIRY_SECONDS / 60)) minutes"
echo ""
echo -e "${GREEN}Environment variables set:${NC}"
echo "  • VAULT_ADDR"
echo "  • VAULT_TOKEN"
echo "  • VAULT_TOKEN_EXPIRY"
echo ""
echo -e "${CYAN}You can now use:${NC}"
echo "  • claude-vault status"
echo "  • claude-vault list"
echo "  • claude-vault get <service>"
echo "  • claude-vault set <service> key=value"
echo ""

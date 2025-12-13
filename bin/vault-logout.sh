#!/bin/bash
# Logout from Vault session and clear credentials
#
# Usage:
#   source ./scripts/vault-logout.sh

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

VAULT_ADDR="${VAULT_ADDR:-https://vault.example.com}"

echo -e "${BLUE}👋 Vault Logout${NC}"
echo "================"
echo ""

if [ -z "$VAULT_TOKEN" ]; then
    echo -e "${YELLOW}⚠️  No active session found${NC}"
    echo ""
    exit 0
fi

# Revoke token (best practice)
echo -e "${CYAN}Revoking token...${NC}"

REVOKE_RESPONSE=$(curl -sk -w "\n%{http_code}" \
    --request POST \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    "$VAULT_ADDR/v1/auth/token/revoke-self" 2>/dev/null)

HTTP_CODE=$(echo "$REVOKE_RESPONSE" | tail -n1)

if [ "$HTTP_CODE" -eq 204 ] || [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✅ Token revoked${NC}"
else
    echo -e "${YELLOW}⚠️  Token revocation failed (may already be invalid)${NC}"
fi

# Clear environment variables
unset VAULT_TOKEN
unset VAULT_TOKEN_EXPIRY
unset VAULT_ADDR

# Clean up session files
rm -f /tmp/vault-session-* 2>/dev/null

echo ""
echo -e "${GREEN}✅ Logged out successfully${NC}"
echo ""
echo "Environment variables cleared:"
echo "  • VAULT_TOKEN"
echo "  • VAULT_TOKEN_EXPIRY"
echo "  • VAULT_ADDR"
echo ""

# If script was sourced, clear in parent shell
if [ "$0" != "$BASH_SOURCE" ]; then
    echo -e "${GREEN}✅ Session cleared from your shell${NC}"
    echo ""
else
    echo -e "${YELLOW}💡 Tip: Run with 'source' to clear from current shell:${NC}"
    echo -e "  ${CYAN}source ./scripts/vault-logout.sh${NC}"
    echo ""
fi

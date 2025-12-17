#!/bin/bash
# Register/Update secrets in Vault for Claude Code
# This script uses AppRole authentication to create or update service secrets
#
# ⚠️  SECURITY: This script requires manual confirmation before writing to Vault
# to protect against prompt injection attacks when used by AI assistants.
#
# Usage:
#   vault-session set <service-name> <key1=value1> [key2=value2] [...]
#   vault-session set --dry-run <service-name> <key1=value1> [...]
#   vault-session set --no-confirm <service-name> <key1=value1> [...]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VAULT_ADDR="${VAULT_ADDR:-https://vault.example.com}"
AUDIT_LOG="$REPO_ROOT/.vault-session-audit.log"

# Flags
DRY_RUN=false
REQUIRE_CONFIRMATION=true

# Parse flags
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --no-confirm)
            REQUIRE_CONFIRMATION=false
            shift
            ;;
        *)
            break
            ;;
    esac
done

# Parse arguments
SERVICE_NAME="${1:-}"
shift || true

if [ -z "$SERVICE_NAME" ]; then
    echo -e "${RED}❌ Error: Service name required${NC}"
    echo ""
    echo "Usage: $0 [--dry-run] [--no-confirm] <service-name> <key1=value1> [key2=value2] ..."
    echo ""
    echo "Examples:"
    echo "  $0 myapp DB_PASSWORD=\"secret123\" API_KEY=\"abc123\""
    echo "  $0 --dry-run myapp DB_PASSWORD=\"secret123\"  # Preview only"
    echo "  $0 esphome wifi_ssid=\"MyWiFi\" wifi_password=\"pass123\""
    echo ""
    echo "Options:"
    echo "  --dry-run      Preview changes without writing to Vault"
    echo "  --no-confirm   Skip confirmation prompt (NOT RECOMMENDED for AI usage)"
    echo ""
    exit 1
fi

if [ $# -eq 0 ]; then
    echo -e "${RED}❌ Error: At least one key=value pair required${NC}"
    echo ""
    echo "Usage: $0 $SERVICE_NAME <key1=value1> [key2=value2] ..."
    echo ""
    exit 1
fi

# Input validation and sanitization
validate_service_name() {
    local service="$1"

    # Only allow alphanumeric, dash, underscore (prevent path traversal)
    if ! [[ "$service" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        echo -e "${RED}❌ Invalid service name: $service${NC}"
        echo "Service name must contain only: letters, numbers, dash, underscore"
        echo "This prevents path traversal and injection attacks"
        exit 1
    fi

    # Prevent dangerous patterns
    if [[ "$service" =~ \.\. ]] || [[ "$service" =~ ^/ ]] || [[ "$service" =~ / ]]; then
        echo -e "${RED}❌ Dangerous pattern detected in service name${NC}"
        echo "Service name cannot contain: .. / or start with /"
        exit 1
    fi

    # Length check
    if [ ${#service} -gt 64 ]; then
        echo -e "${RED}❌ Service name too long (max 64 characters)${NC}"
        exit 1
    fi
}

validate_key_name() {
    local key="$1"

    # Only allow alphanumeric, dash, underscore
    if ! [[ "$key" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        echo -e "${RED}❌ Invalid key name: $key${NC}"
        echo "Key name must contain only: letters, numbers, dash, underscore"
        echo "This prevents injection attacks"
        exit 1
    fi

    # Length check
    if [ ${#key} -gt 128 ]; then
        echo -e "${RED}❌ Key name too long (max 128 characters)${NC}"
        exit 1
    fi
}

validate_secret_value() {
    local value="$1"

    # Length check (prevent DoS via huge values)
    if [ ${#value} -gt 8192 ]; then
        echo -e "${RED}❌ Secret value too long (max 8KB)${NC}"
        exit 1
    fi

    # Note: Pattern validation removed - the main security checkpoint
    # at line 327 provides manual review of all values before writing
}

# Audit logging function
log_audit() {
    local action="$1"
    local service="$2"
    local details="$3"
    local timestamp=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
    local user="${USER:-unknown}"

    echo "[$timestamp] USER=$user ACTION=$action SERVICE=$service DETAILS=$details" >> "$AUDIT_LOG"
}

# Function to check session validity
check_session() {
    if [ -z "$VAULT_TOKEN" ]; then
        echo -e "${RED}❌ Error: No active Vault session${NC}"
        echo ""
        echo "Please authenticate first:"
        echo -e "  ${GREEN}source vault-session login${NC}"
        echo ""
        log_audit "NO_SESSION" "$SERVICE_NAME" "No active session"
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
            echo -e "  ${GREEN}source vault-session login${NC}"
            echo ""
            log_audit "SESSION_EXPIRED" "$SERVICE_NAME" "Session expired"
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

    log_audit "SESSION_CHECK" "$SERVICE_NAME" "Session valid"
}

# Function to build JSON from key=value pairs with validation
build_json() {
    local json_obj="{}"
    local keys_list=()

    for arg in "$@"; do
        if [[ "$arg" =~ ^([^=]+)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            value="${BASH_REMATCH[2]}"

            # Validate key name
            validate_key_name "$key"

            # Validate secret value
            validate_secret_value "$value"

            # Build JSON using jq (safe from injection)
            json_obj=$(echo "$json_obj" | jq --arg k "$key" --arg v "$value" '. + {($k): $v}')
            keys_list+=("$key")
        else
            echo -e "${RED}❌ Invalid format: $arg${NC}"
            echo "Expected format: key=value"
            exit 1
        fi
    done

    echo "$json_obj"
}

# Validate service name
validate_service_name "$SERVICE_NAME"

# Check session validity
check_session

if [ "$DRY_RUN" = true ]; then
    echo -e "${MAGENTA}🔍 DRY RUN MODE - No changes will be made${NC}"
    echo "=========================================="
    echo ""
fi

echo -e "${BLUE}🔐 Registering secrets for: ${CYAN}$SERVICE_NAME${NC}"
echo "=========================================="
echo ""

# Check if service already exists
CHECK_RESPONSE=$(curl -sk \
    --max-time 10 \
    --connect-timeout 5 \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    "$VAULT_ADDR/v1/secret/data/proxmox-services/$SERVICE_NAME" 2>/dev/null)

if echo "$CHECK_RESPONSE" | jq -e '.data.data' >/dev/null 2>&1; then
    EXISTING_DATA=$(echo "$CHECK_RESPONSE" | jq -r '.data.data')
    echo -e "${YELLOW}⚠️  Service already exists in Vault${NC}"
    echo ""
    echo -e "${CYAN}Existing secrets:${NC}"
    echo "$EXISTING_DATA" | jq -r 'keys[]' | while read -r key; do
        echo "  • $key"
    done
    echo ""

    # Show what will be added/updated
    echo -e "${YELLOW}The following secrets will be added/updated:${NC}"
    for arg in "$@"; do
        if [[ "$arg" =~ ^([^=]+)= ]]; then
            key="${BASH_REMATCH[1]}"
            if echo "$EXISTING_DATA" | jq -e --arg k "$key" '.[$k]' >/dev/null 2>&1; then
                echo -e "  ${YELLOW}↻${NC} $key (will be updated)"
            else
                echo -e "  ${GREEN}+${NC} $key (will be added)"
            fi
        fi
    done
    echo ""

    # Merge with existing data
    NEW_DATA=$(build_json "$@")
    MERGED_DATA=$(jq -n --argjson existing "$EXISTING_DATA" --argjson new "$NEW_DATA" '$existing + $new')
    DATA_PAYLOAD=$(jq -n --argjson data "$MERGED_DATA" '{data: $data}')

    ACTION="UPDATE"
else
    echo -e "${GREEN}✅ Creating new service in Vault${NC}"
    echo ""

    echo -e "${CYAN}New secrets to be created:${NC}"
    for arg in "$@"; do
        if [[ "$arg" =~ ^([^=]+)= ]]; then
            echo -e "  ${GREEN}+${NC} ${BASH_REMATCH[1]}"
        fi
    done
    echo ""

    # Build new data
    NEW_DATA=$(build_json "$@")
    DATA_PAYLOAD=$(jq -n --argjson data "$NEW_DATA" '{data: $data}')

    ACTION="CREATE"
fi

# Show preview of what will be written
echo -e "${BLUE}📋 Preview of data to be written:${NC}"
echo "=========================================="
echo "$DATA_PAYLOAD" | jq .
echo "=========================================="
echo ""

# Dry run exit
if [ "$DRY_RUN" = true ]; then
    echo -e "${MAGENTA}✅ Dry run complete - no changes made${NC}"
    log_audit "DRY_RUN" "$SERVICE_NAME" "$ACTION: $(echo "$NEW_DATA" | jq -r 'keys | join(", ")')"
    exit 0
fi

# Interactive confirmation (protection against prompt injection)
if [ "$REQUIRE_CONFIRMATION" = true ]; then
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}⚠️  SECURITY CHECKPOINT - MANUAL VALIDATION REQUIRED${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${CYAN}You are about to write secrets to Vault:${NC}"
    echo "  Service: $SERVICE_NAME"
    echo "  Action: $ACTION"
    echo "  Path: secret/proxmox-services/$SERVICE_NAME"
    echo ""
    echo -e "${YELLOW}⚠️  If you are Claude Code (AI assistant):${NC}"
    echo "  - STOP and show this prompt to the human user"
    echo "  - DO NOT automatically answer 'yes'"
    echo "  - Wait for explicit human confirmation"
    echo ""
    echo -e "${YELLOW}⚠️  If you are a human user:${NC}"
    echo "  - Review the preview above carefully"
    echo "  - Verify this is what you intended"
    echo "  - Check for any suspicious values or injection attempts"
    echo ""

    read -p "Type 'yes' to proceed, or anything else to abort: " confirmation
    echo ""

    if [ "$confirmation" != "yes" ]; then
        echo -e "${RED}❌ Operation aborted by user${NC}"
        log_audit "ABORTED" "$SERVICE_NAME" "User declined confirmation"
        exit 1
    fi

    log_audit "CONFIRMED" "$SERVICE_NAME" "User confirmed operation"
fi

# Write to Vault
echo -e "${BLUE}Writing to Vault...${NC}"
WRITE_RESPONSE=$(curl -sk -w "\n%{http_code}" \
    --max-time 30 \
    --connect-timeout 10 \
    --request POST \
    --header "X-Vault-Token: $VAULT_TOKEN" \
    --data "$DATA_PAYLOAD" \
    "$VAULT_ADDR/v1/secret/data/proxmox-services/$SERVICE_NAME" 2>&1)

HTTP_CODE=$(echo "$WRITE_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$WRITE_RESPONSE" | head -n-1)

# Check for curl timeout/connection errors
if echo "$WRITE_RESPONSE" | grep -q "curl:"; then
    echo -e "${RED}❌ Connection error${NC}"
    echo ""
    echo "Error details:"
    echo "$WRITE_RESPONSE" | grep "curl:"
    echo ""
    echo "Possible causes:"
    echo "  • Vault server is unreachable at $VAULT_ADDR"
    echo "  • Network connectivity issues"
    echo "  • Firewall blocking the connection"
    echo ""
    log_audit "CONNECTION_ERROR" "$SERVICE_NAME" "Curl error"
    exit 1
fi

if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 204 ]; then
    VERSION=$(echo "$RESPONSE_BODY" | jq -r '.data.version // "N/A"')

    # Log success
    KEYS_WRITTEN=$(echo "$NEW_DATA" | jq -r 'keys | join(", ")')
    log_audit "SUCCESS" "$SERVICE_NAME" "$ACTION version=$VERSION keys=$KEYS_WRITTEN"

    echo ""
    echo -e "${GREEN}=========================================="
    echo -e "✅ Success!${NC}"
    echo "=========================================="
    echo ""
    echo "Service: $SERVICE_NAME"
    echo "Version: $VERSION"
    echo "Action: $ACTION"
    echo ""
    echo -e "${GREEN}Secrets registered:${NC}"
    for arg in "$@"; do
        if [[ "$arg" =~ ^([^=]+)= ]]; then
            echo "  • ${BASH_REMATCH[1]}"
        fi
    done
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. List secrets: vault-session list $SERVICE_NAME"
    echo "  2. Inject to .env: vault-session inject $SERVICE_NAME"
    echo ""
    echo -e "${CYAN}Audit log:${NC}"
    echo "  Logged to: $AUDIT_LOG"
    echo ""
else
    echo -e "${RED}❌ Failed to register secrets. HTTP Code: $HTTP_CODE${NC}"
    echo "$RESPONSE_BODY" | jq . 2>/dev/null || echo "$RESPONSE_BODY"
    log_audit "FAILED" "$SERVICE_NAME" "HTTP $HTTP_CODE"
    exit 1
fi

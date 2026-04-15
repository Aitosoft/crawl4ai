#!/usr/bin/env bash
# Aitosoft: set up an Azure Monitor alert for replica memory > 85% for > 5 min.
#
# Why: the 2026-04-14 outage saw memory climb from 68% → 82% over 75 min with
# nobody watching. By the time we noticed, requests had been 504'ing for 90
# min. This alert fires within ~5-10 min of sustained high memory so we catch
# any regression of Fix 1 / Fix 2 early.
#
# Usage:
#   ./setup-memory-alert.sh you@aitosoft.com
#   ./setup-memory-alert.sh you@aitosoft.com,oncall@aitosoft.com
#
# Idempotent — re-running updates the existing alert and action group.

set -euo pipefail

EMAIL_LIST="${1:-}"
if [ -z "$EMAIL_LIST" ]; then
    echo "Usage: $0 <email[,email,...]>" >&2
    exit 1
fi

RESOURCE_GROUP="aitosoft-prod"
APP_NAME="crawl4ai-service"
ACTION_GROUP="crawl4ai-oncall"
ALERT_NAME="crawl4ai-memory-high"
SUBSCRIPTION=$(az account show --query id -o tsv)
APP_RESOURCE_ID="/subscriptions/$SUBSCRIPTION/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.App/containerApps/$APP_NAME"

echo "1️⃣  Creating / updating action group '$ACTION_GROUP'..."
# Convert comma-separated emails to az CLI receiver args
EMAIL_ARGS=()
idx=0
IFS=',' read -ra ADDR <<< "$EMAIL_LIST"
for email in "${ADDR[@]}"; do
    idx=$((idx + 1))
    EMAIL_ARGS+=("--email" "oncall${idx}" "$email")
done

az monitor action-group create \
    --name "$ACTION_GROUP" \
    --resource-group "$RESOURCE_GROUP" \
    --short-name "c4aialert" \
    "${EMAIL_ARGS[@]}" \
    --output none

ACTION_GROUP_ID=$(az monitor action-group show \
    --name "$ACTION_GROUP" \
    --resource-group "$RESOURCE_GROUP" \
    --query id -o tsv)

echo "2️⃣  Creating / updating metric alert '$ALERT_NAME'..."
# Threshold: 85% MemoryPercentage sustained for 5 min (window=5m, frequency=1m)
az monitor metrics alert create \
    --name "$ALERT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --scopes "$APP_RESOURCE_ID" \
    --description "Replica memory > 85% for > 5 min — possible leak regression (see 2026-04-14 incident / Fix 1 + Fix 2 in api.py, crawler_pool.py)" \
    --severity 2 \
    --window-size 5m \
    --evaluation-frequency 1m \
    --condition "max MemoryPercentage > 85" \
    --action "$ACTION_GROUP_ID" \
    --output none || {
    # Alert already exists — update via delete + recreate pattern
    echo "   (alert exists, recreating with new threshold…)"
    az monitor metrics alert delete \
        --name "$ALERT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --output none
    az monitor metrics alert create \
        --name "$ALERT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --scopes "$APP_RESOURCE_ID" \
        --description "Replica memory > 85% for > 5 min — possible leak regression" \
        --severity 2 \
        --window-size 5m \
        --evaluation-frequency 1m \
        --condition "max MemoryPercentage > 85" \
        --action "$ACTION_GROUP_ID" \
        --output none
}

echo
echo "✅ Alert configured."
echo "   Alert:        $ALERT_NAME"
echo "   Threshold:    max MemoryPercentage > 85 (sustained 5 min)"
echo "   Notifies:     $EMAIL_LIST"
echo
echo "   Verify:"
echo "     az monitor metrics alert show --name $ALERT_NAME --resource-group $RESOURCE_GROUP"
echo
echo "   Test-fire (optional):"
echo "     az monitor metrics alert update --name $ALERT_NAME \\"
echo "       --resource-group $RESOURCE_GROUP --condition 'max MemoryPercentage > 0.1'"
echo "     (then revert the threshold after it fires)"

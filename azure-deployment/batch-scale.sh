#!/usr/bin/env bash
# Aitosoft: toggle crawl4ai-service min-replicas. EMERGENCY VALVE ONLY.
#
# RETIRED as a routine pre-batch step (2026-07-17). Capacity is now managed
# by the render-admission gate (aitosoft_admission.py, 429 + Retry-After) and
# the `http-renders` ACA scale rule (a trigger, NOT render capacity) — replicas
# scale with load automatically. See DEPLOYMENT_INFO.md "Scaling".
#
# Keep for emergencies: if KEDA misbehaves mid-batch (e.g. the 2026-04-14
# outage where replica xs697 was SIGTERM'd during an active run), pinning
# min-replicas > 0 holds warm capacity until the batch completes.
#
# Usage:
#   ./batch-scale.sh up [N]  # Pin min=N warm replicas (default 1). Emergency only.
#   ./batch-scale.sh down    # Set min=0 (scale-to-zero). ALWAYS call after.
#   ./batch-scale.sh status  # Show current replica config.

set -euo pipefail

APP_NAME="crawl4ai-service"
RESOURCE_GROUP="aitosoft-prod"

# NOTE (2026-08-08): this script used to carry `MAX_REPLICAS=30` and pass
# `--max-replicas "$MAX_REPLICAS"` on BOTH `up` and `down`. That silently
# reverted maxReplicas to a stale hardcoded value on every invocation — and by
# then production was at 45 (raised for MAS's ~18,000-company plan). The
# emergency valve would therefore have cut the fleet ceiling by a third at
# exactly the moment someone reached for it because the fleet was under stress.
#
# The fix is to not mention max-replicas at all: `az containerapp update
# --min-replicas N` changes only min and leaves the rest of the scale block
# untouched. A constant that must "keep in sync" with live infrastructure by
# hand is a defect waiting to happen; the live value is the source of truth.

show_scale() {
    az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.scale" -o json
}

action="${1:-status}"

case "$action" in
    up)
        min="${2:-1}"
        echo "Scaling $APP_NAME min-replicas to $min (maxReplicas left untouched)..."
        az containerapp update \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --min-replicas "$min" \
            --output none
        echo "✅ Done. Warm replicas held at $min until you call 'batch-scale.sh down'."
        echo "Resulting scale block:"; show_scale
        ;;
    down)
        echo "Scaling $APP_NAME back to min=0 (scale-to-zero on idle)..."
        az containerapp update \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --min-replicas 0 \
            --output none
        echo "✅ Done. Replicas will scale to zero when idle."
        echo "Resulting scale block:"; show_scale
        ;;
    status)
        az containerapp show \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --query "{image:properties.template.containers[0].image, minReplicas:properties.template.scale.minReplicas, maxReplicas:properties.template.scale.maxReplicas}" \
            --output table
        echo ""
        echo "Live replicas:"
        az containerapp replica list \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --query "[].{name:name, created:properties.createdTime, state:properties.runningState}" \
            --output table
        ;;
    *)
        echo "Usage: $0 {up [min]|down|status}" >&2
        exit 1
        ;;
esac

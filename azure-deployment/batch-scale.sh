#!/usr/bin/env bash
# Aitosoft: toggle crawl4ai-service min-replicas. EMERGENCY VALVE ONLY.
#
# RETIRED as a routine pre-batch step (2026-07-17). Capacity is now managed
# by the render-admission gate (aitosoft_admission.py, 429 + Retry-After) and
# the `http-renders` ACA scale rule (2 concurrent renders/replica) — replicas
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
MAX_REPLICAS=30  # keep in sync with prod scale config (DEPLOYMENT_INFO.md)

action="${1:-status}"

case "$action" in
    up)
        min="${2:-1}"
        echo "Scaling $APP_NAME min-replicas to $min (max=$MAX_REPLICAS)..."
        az containerapp update \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --min-replicas "$min" \
            --max-replicas "$MAX_REPLICAS" \
            --output none
        echo "✅ Done. Warm replicas held at $min until you call 'batch-scale.sh down'."
        ;;
    down)
        echo "Scaling $APP_NAME back to min=0 (scale-to-zero on idle)..."
        az containerapp update \
            --name "$APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --min-replicas 0 \
            --max-replicas "$MAX_REPLICAS" \
            --output none
        echo "✅ Done. Replicas will scale to zero when idle."
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

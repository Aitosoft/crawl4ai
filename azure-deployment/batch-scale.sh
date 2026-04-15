#!/usr/bin/env bash
# Aitosoft: toggle crawl4ai-service min-replicas around a WAA batch run.
#
# Why: default minReplicas=0 lets Azure KEDA scale to zero when idle
# (saves cost). But during an active WAA batch, KEDA's http-scaler can
# decide traffic is light and scale down mid-run — removing redundancy
# right when we might need failover. Seen in the 2026-04-14 outage at
# 12:51 UTC: replica xs697 was SIGTERM'd during Ahlman's run.
#
# Usage:
#   ./batch-scale.sh up      # Set min=1, max=20. Call BEFORE starting WAA batch.
#   ./batch-scale.sh up 3    # Set min=3 for parallel-agent runs (3 agents).
#   ./batch-scale.sh down    # Set min=0 (scale-to-zero). Call AFTER batch done.
#   ./batch-scale.sh status  # Show current replica config.
#
# Scaling guidance:
#   1 WAA agent (sequential)     → min=1
#   3-6 parallel WAA agents       → min=3
#   10+ parallel agents (prod)    → min=5, revisit max if hitting 20.

set -euo pipefail

APP_NAME="crawl4ai-service"
RESOURCE_GROUP="aitosoft-prod"
MAX_REPLICAS=20

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

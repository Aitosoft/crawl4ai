#!/usr/bin/env bash
# Aitosoft: is anything in flight on the app? Read-only (Log Analytics + management API); never
# calls the app. The check behind DEPLOY_ALLOW_LIVE=1 (deploy-image.sh) and ALLOW_LIVE=1
# (batch-scale.sh fix): a revision change kills in-flight renders (AZURE_OPERATIONS.md §2.4).
#
# Usage: LAW_ID=<PRIVATE.md> ./azure-deployment/last-admit.sh [app]
#
# Console rows reach Log Analytics a few minutes late (AZURE_OPERATIONS.md §5.3), so "no recent
# ADMIT" can be the lag. Rule: go ahead only if the last ADMIT is >= 5 minutes old on two reads a
# minute apart. MAS's unannounced traffic (from ~2026-11-08) runs 1-5 companies in flight, so a
# quiet gap of 5 minutes is a real gap, not a pause between pages.
set -euo pipefail
APP="${1:-${APP_NAME:-crawl4ai-service-se}}"
: "${LAW_ID:?set LAW_ID (PRIVATE.md)}"
replicas="$(az containerapp replica list -n "$APP" -g aitosoft-prod --query 'length(@)' -o tsv)"
last="$(az monitor log-analytics query -w "$LAW_ID" -o tsv --analytics-query \
  "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(2h) | where ContainerAppName_s == '$APP'
   | where indexof(Log_s, 'RenderGate ADMIT') >= 0 | summarize t_last=max(TimeGenerated)" \
  | awk '{print $2}')"
now="$(date -u +%s)"
if [[ -z "$last" || "$last" == "None" ]]; then
  echo "replicas=$replicas  last ADMIT: none in 2 h"
else
  age=$(( now - $(date -u -d "$last" +%s) ))
  echo "replicas=$replicas  last ADMIT: $last  ($(( age / 60 )) min $(( age % 60 )) s ago)"
fi

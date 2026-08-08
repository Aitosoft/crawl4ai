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
# The first fix — drop `--max-replicas` entirely — broke `down` instead, and
# silently, which is worse than what it replaced. Verified 2026-08-08 in the
# installed CLI source (`azext_containerapp/containerapp_decorator.py`):
#
#   :791  update_map['scale'] = min_replicas or max_replicas or scale_rule_name
#   :983  if update_map["scale"]:        # <- the only writer of minReplicas
#   :986      if min_replicas is not None: ...scale["minReplicas"] = min_replicas
#
# The INNER logic handles 0 correctly (`is not None`); the OUTER gate is plain
# truthiness. So `--min-replicas 0` alone gives `0 or None or None` -> None ->
# falsy -> the scale block is never added to the PATCH body at all. `up N`
# worked only because N>=1 is truthy. `down` printed its success line and did
# nothing — the valve could be opened and not closed.
#
# So we must pass a second, truthy scale argument, and it must not be a
# hardcoded constant (that was the original defect). Read maxReplicas live and
# hand it straight back: the gate goes truthy, max is written to the value it
# already had, and there is no constant to drift.
#
# Both branches verify afterwards rather than trusting the exit code, because
# the failure mode this comment documents is a SILENT no-op that exits 0.

show_scale() {
    az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.scale" -o json
}

live_max() {
    az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.scale.maxReplicas" -o tsv
}

# set_min <target> — write minReplicas and prove it landed.
set_min() {
    local target="$1" max
    max="$(live_max)"
    if [[ -z "$max" || ! "$max" =~ ^[0-9]+$ ]]; then
        echo "ERROR: could not read live maxReplicas (got '${max}'). Refusing to guess." >&2
        exit 1
    fi
    az containerapp update \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --min-replicas "$target" \
        --max-replicas "$max" \
        --output none

    local now
    now="$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.scale.minReplicas" -o tsv)"
    if [[ "$now" != "$target" ]]; then
        echo "ERROR: minReplicas is '${now}', expected '${target}'. The update did NOT apply." >&2
        exit 1
    fi
    echo "Verified: minReplicas=${now}, maxReplicas=${max} (unchanged)."
}

action="${1:-status}"

case "$action" in
    up)
        min="${2:-1}"
        echo "Scaling $APP_NAME min-replicas to $min (maxReplicas left untouched)..."
        set_min "$min"
        echo "✅ Done. Warm replicas held at $min until you call 'batch-scale.sh down'."
        echo "Resulting scale block:"; show_scale
        ;;
    down)
        echo "Scaling $APP_NAME back to min=0 (scale-to-zero on idle)..."
        set_min 0
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

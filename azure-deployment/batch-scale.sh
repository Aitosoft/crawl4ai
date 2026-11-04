#!/usr/bin/env bash
# Aitosoft: set crawl4ai-service's replica floor and ceiling.
#
# Two uses (AZURE_OPERATIONS.md §3.5):
#  - `fix N` / `release`: the fixed fleet for MAS's announced windows (since 2026-11-04). At their
#    shape the autoscaler lands on 2 or 3 replicas by chance, so a fixed 2 makes our cost
#    predictable and removes the cold-start 429 burst (tasks/optimization-experiments.md, lever 2).
#  - `up N` / `down`: an emergency floor, e.g. if KEDA misbehaves mid-batch (the 2026-04-14
#    outage, where replica xs697 was SIGTERM'd during an active run).
# Outside those, the app autoscales from zero: the render-admission gate (429 + Retry-After) and the
# `http-renders` scale rule (a trigger, not render capacity) track the traffic.
#
# Every change mints a revision, which kills in-flight renders (AZURE_OPERATIONS.md §2.4), so make
# it with nothing in flight.
#
# Usage:
#   ./batch-scale.sh up [N]  # Pin min=N warm replicas (default 1). Emergency only.
#   ./batch-scale.sh down    # Set min=0 (scale-to-zero). ALWAYS call after.
#   ./batch-scale.sh fix N   # min = max = N: a FIXED fleet for one announced window
#                            # (tasks/optimization-experiments.md, lever 2). Mints a revision.
#   ./batch-scale.sh release # Undo `fix`: min=0 and max back to deploy-image.sh's
#                            # ACA_MAX_REPLICAS. ALWAYS call after `fix`; `down` would
#                            # keep max at N.
#   ./batch-scale.sh status  # Show current replica config.

set -euo pipefail

# 2026-11-04: MAS calls crawl4ai-service-se (Sweden Central); see deploy-image.sh.
APP_NAME="${APP_NAME:-crawl4ai-service-se}"
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

# set_min_max <min> <max> — write both and prove both landed. Both values go into the PATCH
# because --max-replicas is truthy whenever max >= 1 (see the CLI gate described above).
set_min_max() {
    local min="$1" max="$2" now
    az containerapp update --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --min-replicas "$min" --max-replicas "$max" --output none
    now="$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --query "join(' ', [to_string(properties.template.scale.minReplicas), to_string(properties.template.scale.maxReplicas)])" -o tsv)"
    if [[ "$now" != "$min $max" ]]; then
        echo "ERROR: min/max is '${now}', expected '${min} ${max}'. The update did NOT apply." >&2
        exit 1
    fi
    echo "Verified: minReplicas=${min}, maxReplicas=${max}."
}

# The ceiling `release` restores: the one deploy-image.sh's drift check enforces, read from that
# script so there is no second constant to drift (the defect this file's header documents).
repo_max() {
    grep -E '^ACA_MAX_REPLICAS=[0-9]+$' "$(dirname "${BASH_SOURCE[0]}")/deploy-image.sh" | cut -d= -f2
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
    fix)
        n="${2:?usage: $0 fix N}"
        [[ "$n" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: N must be a positive integer." >&2; exit 1; }
        # From ~2026-11-08 MAS's traffic is unannounced, and a revision change kills in-flight
        # renders (AZURE_OPERATIONS.md §2.4). Fix the fleet only on an idle app, or after checking
        # the last RenderGate ADMIT (azure-deployment/last-admit.sh, AZURE_OPERATIONS.md §2.1).
        live="$(az containerapp replica list --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
            --query 'length(@)' -o tsv 2>/dev/null || echo "")"
        if [[ -n "$live" && "$live" != "0" && "${ALLOW_LIVE:-}" != "1" ]]; then
            echo "REFUSING: $live replica(s) live, so MAS may be mid-crawl. Wait for scale-to-zero," >&2
            echo "or run azure-deployment/last-admit.sh twice a minute apart; if the last ADMIT is" >&2
            echo ">= 5 min old both times, re-run with ALLOW_LIVE=1." >&2
            exit 1
        fi
        echo "Fixing $APP_NAME at min = max = $n (mints a revision; nothing may be in flight)..."
        set_min_max "$n" "$n"
        echo "✅ Fixed at $n. Run 'batch-scale.sh release' after the window."
        ;;
    release)
        # The fixed fleet is live by design here; MAS's end message plus a last RenderGate ADMIT
        # older than a minute is the check (tasks/optimization-experiments.md, protocol step 5).
        max="$(repo_max)"
        [[ "$max" =~ ^[0-9]+$ ]] || { echo "ERROR: could not read ACA_MAX_REPLICAS from deploy-image.sh." >&2; exit 1; }
        echo "Releasing $APP_NAME to min=0, max=$max (deploy-image.sh's ACA_MAX_REPLICAS)..."
        set_min_max 0 "$max"
        echo "✅ Released. Scale-to-zero on idle."
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
        echo "Usage: $0 {up [min]|down|fix N|release|status}" >&2
        exit 1
        ;;
esac

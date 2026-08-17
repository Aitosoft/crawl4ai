#!/usr/bin/env bash
# Aitosoft: build and deploy a new crawl4ai-service image.
#
# This is the ONLY supported deploy path for image updates. It never touches
# env vars (so MAS's CRAWL4AI_API_TOKEN survives), replica limits, probes, or
# scale rules — it swaps the image, then drift-checks the live `http-renders`
# trigger and maxReplicas against the constants declared below. Those are NOT
# tied to `render_capacity`; that coupling was a category error, retired
# 2026-08-08.
#
# Usage:
#   ./azure-deployment/deploy-image.sh <tag>     # e.g. 0.9.3-fix-foo
#
# Prereqs: az login (subscription "Aitosoft - Microsoft Partner Network NEW"),
# run from repo root or pass nothing else — the build context is the repo root.
#
# Full provisioning reference (scale rule, probes, env vars) lives in
# AZURE_OPERATIONS.md — this script assumes the app already exists.

set -euo pipefail

TAG="${1:?usage: deploy-image.sh <image-tag>}"
APP_NAME="crawl4ai-service"
RESOURCE_GROUP="aitosoft-prod"
REGISTRY="aitosoftacr"
IMAGE="crawl4ai-service:${TAG}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------------------
# PRE-DEPLOY GATE: is the fleet small enough for a revision transition?
#
# Measured the hard way 2026-08-08. ANY template change -- including the
# --image swap below -- mints a NEW revision, and the new revision needs its
# OWN replicas while the old one is still draining. Both count against the
# environment's 100-core quota at 2 vCPU each. With the fleet at 38 replicas
# (76 cores) the new revision could not create pods at all:
#
#   FailedCreate: pods "..." is forbidden: exceeded quota: consumption,
#   requested: cpu=2k, used: 98250, limited: 100k
#
# It then sat in ActivationFailed with 0 replicas while holding 100% of the
# traffic weight. The app stayed up only because ACA kept routing to the old
# revision's surviving replicas -- that is the platform being forgiving, not a
# margin to rely on. This is a live risk mid-sweep, i.e. exactly when someone
# wants to ship a fix. See tasks/done/autoscaler-ratchets-to-the-cap.md.
DEPLOY_REPLICA_CEILING=20
live_replicas=$(az containerapp replica list --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" --query 'length(@)' -o tsv 2>/dev/null || echo "")
if [[ -z "$live_replicas" ]]; then
    echo "    WARNING: could not read the live replica count; continuing." >&2
elif (( live_replicas > DEPLOY_REPLICA_CEILING )); then
    echo "!! REFUSING TO DEPLOY: $live_replicas replicas are live (> $DEPLOY_REPLICA_CEILING)." >&2
    echo "!! A new revision needs its own replicas while these drain, and the" >&2
    echo "!! environment quota is 100 cores at 2 vCPU each. Wait for the fleet to" >&2
    echo "!! drain (scale-to-zero is ~9 min after the last request), then retry." >&2
    echo "!!   az containerapp replica list -n $APP_NAME -g $RESOURCE_GROUP --query 'length(@)'" >&2
    echo "!! Override with DEPLOY_ALLOW_BUSY=1 only if you have checked the quota:" >&2
    echo "!!   az containerapp env list-usages --ids <env-id> -o table" >&2
    [[ "${DEPLOY_ALLOW_BUSY:-}" == "1" ]] || exit 1
    echo "!! DEPLOY_ALLOW_BUSY=1 set -- proceeding anyway." >&2
else
    echo "==> Fleet check OK: ${live_replicas} live replica(s)."
fi

# ---------------------------------------------------------------------------
# DRIFT CHECKS RUN HERE, BEFORE THE BUILD -- moved 2026-08-14.
#
# They used to run AFTER `az containerapp update --image`, which meant a drift
# `exit 1` reported failure with the new image ALREADY LIVE. The operator sees a
# red deploy and a changed production. That is the worst of both, and it fired
# for real: MAS lowered maxReplicas 45 -> 20 on 2026-08-14 while this script
# still declared 45, so the next deploy would have shipped an image and then
# hard-failed. A guard that runs after the thing it guards is not a guard.
#
# Nothing below this block reads the checks' results, so moving them is
# behaviour-preserving for the success path and strictly better for the failure
# path: on drift, nothing has been built and nothing has been deployed.
# ---------------------------------------------------------------------------
echo "==> Verifying scale-trigger invariant (repo intent vs live ACA scale rule)..."
# This check used to require `render_capacity == concurrentRequests`, and that
# was WRONG -- corrected 2026-08-08, see tasks/done/autoscaler-ratchets-to-the-cap.md.
#
# The two are different quantities in different units. `render_capacity` is a
# hard in-process cap on concurrent renders (the safety mechanism).
# `concurrentRequests` is only the autoscaler's trigger, and Microsoft's own
# documentation defines it as "requests in the past 15 seconds divided by 15"
# -- a rate. Requiring them equal pinned the trigger to 2 and badly
# over-provisioned the fleet; the measured factor lives in the task file.
#
# What is still worth verifying is DRIFT: that the live rule is what this repo
# thinks it is, so a console edit or a `batch-scale.sh` accident is caught at
# deploy time. Hence one declared constant, checked against live.
#
# 2026-08-14: 6 -> 12. At trigger 6 the fleet sat at ~12 replicas for a 5-day
# sweep at 7.0% render-slot utilisation, costing EUR 398.89 (94.6% of all Azure
# spend). See tasks/crawl-cost-is-idle-replicas-not-slow-renders.md -- and note
# the leading mechanism there implies the metric is ~6x the replica count
# (render_capacity 2 + admission_queue 4 upstream connections per replica, held
# open by gunicorn's `--keep-alive 300`), which makes trigger 6 a NEUTRAL
# equilibrium the fleet never drains from, and anything above 6 draining.
ACA_SCALE_TRIGGER=12

rule_trigger=$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --query "properties.template.scale.rules[?name=='http-renders'].http.metadata.concurrentRequests | [0]" -o tsv)
if [[ -z "$rule_trigger" ]]; then
    echo "!! The 'http-renders' scale rule is MISSING from the live app." >&2
    echo "!! Without it ACA falls back to its default of 10. Re-apply it:" >&2
    echo "!!   az containerapp update -n $APP_NAME -g $RESOURCE_GROUP \\" >&2
    echo "!!     --scale-rule-name http-renders --scale-rule-type http \\" >&2
    echo "!!     --scale-rule-http-concurrency $ACA_SCALE_TRIGGER" >&2
    exit 1
fi
if [[ "$rule_trigger" != "$ACA_SCALE_TRIGGER" ]]; then
    echo "!! DRIFT: ACA http-renders rule=$rule_trigger but this repo expects $ACA_SCALE_TRIGGER." >&2
    echo "!! Someone changed the scale rule outside the repo, or ACA_SCALE_TRIGGER in this" >&2
    echo "!! script is stale. Reconcile before running traffic -- see AZURE_OPERATIONS.md" >&2
    echo "!! 'Scaling' and tasks/done/autoscaler-ratchets-to-the-cap.md." >&2
    echo "!! NOTHING HAS BEEN BUILT OR DEPLOYED -- this check now runs first." >&2
    exit 1
fi
echo "    OK: http-renders trigger=$rule_trigger (render_capacity is separate, and deliberately so)."

# maxReplicas is checked too, because it is the value that HAS silently drifted:
# batch-scale.sh used to pass a hardcoded --max-replicas on every invocation.
# minReplicas is deliberately NOT checked -- batch-scale.sh legitimately pins it
# above 0 for an emergency window, and a deploy during that window must not fail.
#
# 2026-08-14: 45 -> 20. MAS lowered it on their side as tail protection; the
# observed peak across the whole 18,374-company sweep was 19, so 20 does not
# bind and this is a bookkeeping reconcile, not a capacity decision. The cost
# lever is the trigger above, NOT this number -- 45 -> 20 saved exactly EUR 0.
ACA_MAX_REPLICAS=20
live_max=$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --query "properties.template.scale.maxReplicas" -o tsv)
if [[ "$live_max" != "$ACA_MAX_REPLICAS" ]]; then
    echo "!! DRIFT: maxReplicas=$live_max but this repo expects $ACA_MAX_REPLICAS." >&2
    echo "!! Environment quota is 100 consumption cores at 2 vCPU/replica (50 hard ceiling)," >&2
    echo "!! shared with MAS's aitosoft-edge. Reconcile before running traffic." >&2
    echo "!! NOTHING HAS BEEN BUILT OR DEPLOYED -- this check now runs first." >&2
    exit 1
fi
echo "    OK: maxReplicas=$live_max."

echo "==> Building ${IMAGE} in ACR (context: ${REPO_ROOT})..."
az acr build --registry "$REGISTRY" --image "$IMAGE" \
    --file "$REPO_ROOT/Dockerfile" "$REPO_ROOT"

echo "==> Updating ${APP_NAME} to ${REGISTRY}.azurecr.io/${IMAGE}..."
az containerapp update \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "${REGISTRY}.azurecr.io/${IMAGE}" \
    --output none

# The drift checks used to live HERE, after the image update. They now run
# before the build (see the block above) so a drift cannot leave a changed
# production behind a failed deploy.

echo "==> Active revision:"
az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --query "{image: properties.template.containers[0].image, revision: properties.latestRevisionName, fqdn: properties.configuration.ingress.fqdn}" \
    --output table

echo "==> Done. Smoke-test with:"
echo '    curl -s https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io/health'

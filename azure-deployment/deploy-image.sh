#!/usr/bin/env bash
# Aitosoft: build and deploy a new crawl4ai-service image (to the app MAS calls;
# since 2026-11-04 that is crawl4ai-service-se, see APP_NAME below).
#
# This is the ONLY supported deploy path for image updates. It never touches
# env vars (so MAS's CRAWL4AI_API_TOKEN survives), replica limits, probes, or
# scale rules. Order: the fleet gates, then drift checks of the live `http-renders`
# trigger and maxReplicas against the constants declared below (skipped under
# BUILD_ONLY, which changes nothing live), then the build (unless DEPLOY_DIGEST),
# then the image swap by digest. The constants are NOT tied to `render_capacity`;
# that coupling was a category error, retired 2026-08-08.
#
# Usage:
#   ./azure-deployment/deploy-image.sh <tag>     # build, then deploy what was built
#   BUILD_ONLY=1 ./azure-deployment/deploy-image.sh <tag>
#                                               # build and print the digest; deploy nothing
#   DEPLOY_DIGEST=sha256:<hex> ./azure-deployment/deploy-image.sh <tag>
#                                               # deploy an already-built digest; no build
#
# The safe sequence (2026-11-04): BUILD_ONLY=1, run the test suite inside that digest (TESTING.md
# "Inside a built image"), then DEPLOY_DIGEST=<it>. A plain run rebuilds, and every build installs
# whatever Google Chrome is current, so the image you tested is not the one you would ship
# (FINDINGS "Google Chrome is a second upstream"). Both modes run the same gates and drift checks.
#
# Prereqs: az login (subscription "Aitosoft - Microsoft Partner Network NEW"),
# run from repo root or pass nothing else — the build context is the repo root.
#
# Full provisioning reference (scale rule, probes, env vars) lives in
# AZURE_OPERATIONS.md — this script assumes the app already exists.

set -euo pipefail

TAG="${1:?usage: deploy-image.sh <image-tag>}"
# 2026-11-04: MAS moved every agent to Sweden Central, and the app they call is
# `crawl4ai-service-se` (environment `aitosoft-aca-se`), a clone of the West
# Europe `crawl4ai-service`. The West Europe app still exists, idle at zero;
# target it explicitly with APP_NAME=crawl4ai-service if you ever need to.
APP_NAME="${APP_NAME:-crawl4ai-service-se}"
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
elif (( live_replicas > 0 )) && [[ -z "${BUILD_ONLY:-}" ]] && [[ "${DEPLOY_ALLOW_LIVE:-}" != "1" ]] \
        && (( live_replicas <= DEPLOY_REPLICA_CEILING )); then
    # Since ~2026-11-08 MAS's production traffic arrives unannounced (thread 131). A revision
    # change kills in-flight renders and can strand a request mid-switch (AZURE_OPERATIONS §2.4),
    # so deploy only onto an idle fleet unless you have checked nothing is in flight.
    echo "!! REFUSING TO DEPLOY: $live_replicas replica(s) live; MAS may be mid-crawl." >&2
    echo "!! Wait for scale-to-zero, or run azure-deployment/last-admit.sh twice a minute apart;" >&2
    echo "!! if the last RenderGate ADMIT is >= 5 min old both times, nothing is in flight, and" >&2
    echo "!! re-run with DEPLOY_ALLOW_LIVE=1. A fixed-fleet window keeps replicas up on purpose:" >&2
    echo "!! deploy in its release step instead (batch-scale.sh release, then deploy)." >&2
    exit 1
elif (( live_replicas > DEPLOY_REPLICA_CEILING )); then
    echo "!! REFUSING TO DEPLOY: $live_replicas replicas are live (> $DEPLOY_REPLICA_CEILING)." >&2
    echo "!! A new revision needs its own replicas while these drain, and the" >&2
    echo "!! environment quota is 100 cores at 2 vCPU each. Wait for the fleet to" >&2
    echo "!! drain (scale-to-zero: 6–16 min after the last request, AZURE_OPERATIONS §6.5), then retry." >&2
    echo "!!   az containerapp replica list -n $APP_NAME -g $RESOURCE_GROUP --query 'length(@)'" >&2
    echo "!! Override with DEPLOY_ALLOW_BUSY=1 only if you have checked the quota:" >&2
    echo "!!   az containerapp env list-usages --ids <env-id> -o table" >&2
    [[ "${DEPLOY_ALLOW_BUSY:-}" == "1" ]] || exit 1
    echo "!! DEPLOY_ALLOW_BUSY=1 set -- proceeding anyway." >&2
else
    echo "==> Fleet check OK: ${live_replicas} live replica(s)."
fi

if [[ -n "${BUILD_ONLY:-}" ]]; then
    echo "==> BUILD_ONLY: skipping the drift checks (nothing live changes)."
else
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
# above 0 for an emergency window. maxReplicas IS, so during a fixed-fleet window
# (`batch-scale.sh fix N`, max = N) this check stops a deploy: release first.
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
    echo "!! If a fixed-fleet window is running (batch-scale.sh fix $live_max), this is expected:" >&2
    echo "!! wait for MAS's end message, run batch-scale.sh release, then deploy. Do NOT reset" >&2
    echo "!! max by hand mid-window. Otherwise:" >&2
    echo "!! Environment quota is 100 consumption cores at 2 vCPU/replica (50 hard ceiling)," >&2
    echo "!! shared with MAS's edge app in the same environment. Reconcile before running traffic." >&2
    echo "!! NOTHING HAS BEEN BUILT OR DEPLOYED -- this check now runs first." >&2
    exit 1
fi
echo "    OK: maxReplicas=$live_max."
fi

if [[ -n "${DEPLOY_DIGEST:-}" ]]; then
    if [[ "$DEPLOY_DIGEST" != sha256:* ]]; then
        echo "!! DEPLOY_DIGEST must look like sha256:<hex> (got '${DEPLOY_DIGEST}')." >&2
        exit 1
    fi
    # The digest must exist in this repository, or the update would point the app at nothing.
    if ! az acr repository show --name "$REGISTRY" --image "${IMAGE%%:*}@${DEPLOY_DIGEST}" \
            --query digest -o tsv >/dev/null 2>&1; then
        echo "!! ${IMAGE%%:*}@${DEPLOY_DIGEST} is not in ${REGISTRY}. Nothing deployed." >&2
        exit 1
    fi
    echo "==> DEPLOY_DIGEST set: skipping the build, deploying ${DEPLOY_DIGEST} (tag ${TAG})."
else
    echo "==> Building ${IMAGE} in ACR (context: ${REPO_ROOT})..."
    az acr build --registry "$REGISTRY" --image "$IMAGE" \
        --file "$REPO_ROOT/Dockerfile" "$REPO_ROOT"
fi

# Deploy BY DIGEST, not by tag (2026-11-04). MAS's cutover pinned the live app
# to a digest, and that is the better invariant: a tag is mutable (the
# rollback trap in AZURE_OPERATIONS.md §2.5 is a tag overwritten by a rebuild),
# a digest is not. The tag stays as the human-readable name in ACR.
DIGEST="${DEPLOY_DIGEST:-$(az acr repository show --name "$REGISTRY" --image "$IMAGE" --query digest -o tsv)}"
if [[ "$DIGEST" != sha256:* ]]; then
    echo "!! Could not resolve ${IMAGE} to a digest (got '${DIGEST}'). The image is built" >&2
    echo "!! but NOT deployed. Resolve it by hand and update by digest:" >&2
    echo "!!   az acr repository show --name $REGISTRY --image $IMAGE --query digest -o tsv" >&2
    exit 1
fi
PINNED="${REGISTRY}.azurecr.io/${IMAGE%%:*}@${DIGEST}"
if [[ -n "${BUILD_ONLY:-}" ]]; then
    echo "==> BUILD_ONLY: built ${IMAGE} = ${DIGEST}. Nothing deployed."
    echo "    Test it inside the image (TESTING.md), then:"
    echo "    DEPLOY_DIGEST=${DIGEST} $0 ${TAG}"
    exit 0
fi
echo "==> Updating ${APP_NAME} to ${PINNED} (tag ${TAG})..."
az containerapp update \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "$PINNED" \
    --output none

# The drift checks used to live HERE, after the image update. They now run
# before the build (see the block above) so a drift cannot leave a changed
# production behind a failed deploy.

echo "==> Active revision:"
az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --query "{image: properties.template.containers[0].image, revision: properties.latestRevisionName, fqdn: properties.configuration.ingress.fqdn}" \
    --output table

fqdn=$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" -o tsv)
echo "==> Done. Smoke-test with (TESTING.md §Quality gates has the full post-deploy smoke):"
echo "    curl -s https://${fqdn}/health"

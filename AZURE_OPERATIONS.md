# Azure Operations — `crawl4ai-service-se` (production since 2026-11-04)

The single Azure reference for this repo: deploying, scaling, cost, logs, alerts,
and the failure modes that only show up in Azure. Written by Claude for Claude.

**The rule: if `az` can answer it in one call, this file gives the call, not the
number.** Configuration is queried. Behaviour and measurements are recorded,
because no command returns them. So every number here is dated evidence with its
instrument, never config. The 2026-08-17 audit found every transcribed config
value in this repo stale in at least one copy, with the copies disagreeing; do
not add a replica count, trigger value, image tag or revision name to this file.

Why we own this (owner, 2026-08-17): upstream develops the scraper and we take
their work. Nobody upstream will run our Azure deployment, so that part we have
to know better than anyone.

---

## 0. Live state — query it

**Since 2026-11-04 there are two copies of this service, and MAS calls the Sweden Central one.** MAS
moved every agent to Sweden Central that morning and cloned us there as `crawl4ai-service-se` in
environment `aitosoft-aca-se` (same image by digest, token, scale rule, probes and env var names;
checked with `az` 2026-11-04). The West Europe `crawl4ai-service` in `aitosoft-aca` still exists, idle
at zero, running the older `0.9.2-capacity-gate-2`. **It's kept on purpose as a second egress**
(§7: some hosts drop Sweden Central's addresses and accept West Europe's). MAS holds its planned
11-11 deletion until that is decided. Every command below takes the app
and environment from these two variables, and the scripts in `azure-deployment/` default to the
same app. To target another, `deploy-image.sh`, `batch-scale.sh` and `last-admit.sh` read
`APP_NAME=`; `window-watch.sh`, `window-readout.sh` and `replica-minutes.sh` take the app as their
last positional argument; and `post-deploy-smoke.sh` reads `APP=`:

```bash
APP=crawl4ai-service-se; ACA_ENV=aitosoft-aca-se      # West Europe legacy: crawl4ai-service / aitosoft-aca
```

**KQL filters on the app name, and a wrong name returns zero rows without an error.** Both apps log
to the same workspace; the queries in §5 name `crawl4ai-service-se`. Anything you count from before
2026-11-04 is under `crawl4ai-service`. Spanning the cutover means `startswith "crawl4ai-service"`.

The ACR **repository** is still `crawl4ai-service` for both apps; only the app name changed.

```bash
az containerapp show -n "$APP" -g aitosoft-prod --query "{image:properties.template.containers[0].image, rev:properties.latestRevisionName, min:properties.template.scale.minReplicas, max:properties.template.scale.maxReplicas, trigger:properties.template.scale.rules[0].http.metadata.concurrentRequests, cpu:properties.template.containers[0].resources.cpu, mem:properties.template.containers[0].resources.memory}" -o json
az containerapp env list-usages -n "$ACA_ENV" -g aitosoft-prod -o table
az containerapp revision list -n "$APP" -g aitosoft-prod -o table
az acr repository show-tags --name aitosoftacr --repository crawl4ai-service --orderby time_desc -o tsv
```

What is running, how much environment quota is left, which revisions exist, and
what you could roll back to. These beat every document in the repo, this one
included. Two more:

```bash
# Every app in the environment — the core quota is shared, so this is a capacity fact
az containerapp list -g aitosoft-prod --query "[].{name:name, cpu:properties.template.containers[0].resources.cpu, mem:properties.template.containers[0].resources.memory, min:properties.template.scale.minReplicas, max:properties.template.scale.maxReplicas}" -o table

# Probes, env var NAMES (never values), grace period, revision mode, session affinity
az containerapp show -n "$APP" -g aitosoft-prod --query "{probes:properties.template.containers[0].probes, envNames:properties.template.containers[0].env[].name, grace:properties.template.terminationGracePeriodSeconds, mode:properties.configuration.activeRevisionsMode, sticky:properties.configuration.ingress.stickySessions}" -o json
```

---

## 1. Resources and identifiers

All in resource group `aitosoft-prod`. The resource group, the registry and the Log Analytics
workspace are in West Europe; since 2026-11-04 the apps MAS calls are in Sweden Central (§0).

| Resource | Type | Purpose |
|---|---|---|
| `aitosoftacr` | Container Registry | Image tags — the rollback surface (§2.5) |
| `aitosoft-aca-se` | Container Apps environment, Sweden Central | Since 2026-11-04. **Workload-profiles (v2)**, Consumption profile, its own 100-core quota (§3.6) |
| `crawl4ai-service-se` | Container App | **This service, as MAS calls it since 2026-11-04** |
| `aitosoft-edge-se` | Container App | The platform repo's (MAS), in `aitosoft-aca-se`: same core quota and cost lines as us there |
| `aitosoft-aca` | Container Apps environment, West Europe | Legacy Consumption-only (§3.6). Holds the pre-cutover apps |
| `crawl4ai-service` | Container App | This service before 2026-11-04; idle at zero |
| `aitosoft-edge` | Container App | MAS's, pre-cutover. min = max = 1, so it bills idle while it exists (§4.3) |
| `workspace-aitosoftprodnCsc` | Log Analytics | Console, system and HTTP logs (§5) |
| `crawl4ai-se-memory-high` | Metric alert | Created by MAS's cutover for `-se`, same rule as the old one; fires routinely and pages nobody (§5.5). `crawl4ai-memory-high` scopes the West Europe app |
| `crawl4ai-oncall` | Action group | Zero receivers |

**Trap: the environments are `aitosoft-aca-se` and `aitosoft-aca`; `blackpond-4f5c37ea` and
`wonderfulsea-6a581e75` are their DNS labels.** The label appears in the endpoint because an app FQDN is
`<app>.<environment defaultDomain>`; `az containerapp env …` commands written
against the label fail confusingly. The same fact is why an environment
migration changes the endpoint (§3.6).

```bash
az containerapp env show -n "$ACA_ENV" -g aitosoft-prod \
  --query "{defaultDomain:properties.defaultDomain, workloadProfiles:properties.workloadProfiles}" -o json
```

**Endpoint** (tracked on purpose: fail-closed behind the token, and live tooling
config). Since 2026-11-04 MAS calls the first; the second is the idle West Europe copy:

```
https://crawl4ai-service-se.blackpond-4f5c37ea.swedencentral.azurecontainerapps.io
https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io
```

**Auth:** `Authorization: Bearer $CRAWL4AI_API_TOKEN` — upstream's
`AuthGateMiddleware` since v0.9.2, fail-closed, constant-time. Which paths answer
without it: the 401 row of `TESTING.md` §"What tests should expect from the
server"; the authority is `public_paths` / `public_prefixes` where
`deploy/docker/server.py` installs the middleware. MAS holds the token as
`CRAWL4AI_API_TOKEN` alongside `CRAWL4AI_API_URL`; we hold it in `.env`. Never in
a document or a commit.

**The production token is a plain env var on the Container App, not a Key Vault
or secret reference** (checked 2026-11-03: the app's only secret is the ACR
registry credential). Check without printing values:

```bash
az containerapp show -n "$APP" -g aitosoft-prod \
  --query "properties.template.containers[0].env[].{name:name, secretRef:secretRef}" -o table
```

`-o table` drops an all-null column, so no `SecretRef` column at all means every
env var is a plain value.

**Infrastructure identifiers** (workspace GUID, egress address, subscription ID,
the dev container's home connection) are in gitignored `PRIVATE.md`.
Identifiers that let someone act go there; facts and reasoning stay here. Every
command in this file derives what it needs instead:

```bash
export LAW_ID=$(az monitor log-analytics workspace list \
  --query "[?name=='workspace-aitosoftprodnCsc'].customerId | [0]" -o tsv)
export APP_ID=$(az containerapp show -n "$APP" -g aitosoft-prod --query id -o tsv)
export SUB=$(az account show --query id -o tsv)
```

---

## 2. Deploying

### 2.1 The only supported path

```bash
BUILD_ONLY=1 ./azure-deployment/deploy-image.sh <tag>            # build; prints the digest
# run the suite inside that digest: TESTING.md "Inside a built image"
DEPLOY_DIGEST=sha256:<hex> ./azure-deployment/deploy-image.sh <tag>   # ship exactly that
```

**Build, test inside the image, then deploy the tested digest.** A plain `deploy-image.sh <tag>`
still works, but it rebuilds, and every build installs whatever Google Chrome is current. So the
image you tested is not the image you'd ship (FINDINGS "Google Chrome is a second upstream"; Chrome
151 → 157 arrived with the v0.9.5 deploy and refused http-only sites). Both modes run the same gates
and drift checks.

**The live-fleet gate (2026-11-04):** from ≈2026-11-08 MAS's traffic is unannounced, so the script
refuses while any replica is live. Wait for scale-to-zero. Or check that the last `RenderGate
ADMIT` is minutes old and set `DEPLOY_ALLOW_LIVE=1`. After a fixed-fleet window: `batch-scale.sh
release` first, then deploy with `DEPLOY_ALLOW_LIVE=1`.

It builds in ACR (no local Docker) and swaps the image only. It **never sets env
vars — setting env vars during a deploy is how MAS's token gets broken** — and
never touches replica limits, probes or scale rules. The script is commented at
the level this section would otherwise duplicate; read it.

Order inside the script: the live-fleet gate and the fleet-size gate (§2.3) → drift checks (§2.2;
skipped under `BUILD_ONLY`) → `az acr build` (skipped under `DEPLOY_DIGEST`) → `az containerapp update
--image …@sha256:…`. **Is anything in flight?** `azure-deployment/last-admit.sh` prints the live
replica count and the age of the last `RenderGate ADMIT`. Console rows land minutes late (§5.3), so
proceed only if the age is ≥ 5 min on two reads a minute apart. Confirm the order rather than trust
it:

```bash
grep -nE '^(DEPLOY_REPLICA_CEILING|ACA_SCALE_TRIGGER|ACA_MAX_REPLICAS)=|DRIFT CHECKS|az acr build|--image' azure-deployment/deploy-image.sh
```

### 2.2 Drift checks: a failure means nothing shipped

The script compares live ACA against two constants it declares itself,
`ACA_SCALE_TRIGGER` and `ACA_MAX_REPLICAS` (not against `render_capacity` —
§3.1), and hard-fails on a mismatch. The checks run **before** the build, so a
drift failure means nothing was built and nothing shipped: reconcile the constant
or production and re-run. Trap: before 2026-08-14 they ran after the image swap,
and older notes still say so; do not go looking for a half-deployed service.

`minReplicas` is deliberately unchecked, because `batch-scale.sh up` legitimately
pins it. `maxReplicas` is checked, so **during a fixed-fleet window (`batch-scale.sh fix N`) the
script stops with a drift error.** That's expected: release after MAS's end message, then deploy,
and never reset max by hand mid-window. **If you change a scale setting in Azure for good, change
the constant in the same session**, or the next deploy fails — which is the check working.

### 2.3 The fleet-size gate, and the quota behind it

The script refuses to deploy while more than `DEPLOY_REPLICA_CEILING` replicas are
live (override `DEPLOY_ALLOW_BUSY=1` only after checking quota). Any
`az containerapp update` that touches `properties.template` — image, scale block,
env vars, probes — mints a new revision, whose replicas must start while the old
ones drain, and both count against the environment's 100-core quota. Measured
2026-08-08 with 38 replicas live:

```
FailedCreate ×25: pods "crawl4ai-service--0000039-…" is forbidden:
  exceeded quota: consumption, requested: cpu=2k, used: 98250, limited: 100k
```

The new revision sat in `ActivationFailed` with 0 replicas holding 100 % of the
traffic weight for ~8 minutes. It stayed up only because ACA kept routing to the
old revision's survivors. The risk is highest mid-sweep — exactly when someone
wants to ship a fix.

```bash
az containerapp replica list -n "$APP" -g aitosoft-prod --query 'length(@)'
az containerapp env list-usages -n "$ACA_ENV" -g aitosoft-prod -o table
```

### 2.4 A revision change kills in-flight renders

`terminationGracePeriodSeconds` is unset, so ACA applies its 30 s default against
our 180 s wall-clock fence. **In practice a draining replica loses its in-flight renders at once**,
because the browsers die at SIGTERM (below), so a longer grace would not save them until that is fixed.

```bash
az containerapp show -n "$APP" -g aitosoft-prod \
  --query properties.template.terminationGracePeriodSeconds -o tsv    # empty == 30 s default
```

Observed: the first 39.4 h of the final sweep (2026-08-09 → 08-11) logged 739 ×
`killing 'gunicorn' (9) with SIGKILL` on scale-down. Measured loss was ~6 requests
of 36,783 (4 × `DC`, 2 × `SI` at the ingress) at a true concurrency of 1.45; it
scales with concurrency. The knob exists (`az containerapp update
--termination-grace-period`) and is deliberately unchanged: 180 s would make every
revision transition, every deploy included, drain for three minutes per replica,
to save ~6 requests in 36,783.

**The browsers die at SIGTERM, not after the grace (seen 2026-11-04, joint run (ii)).** At 09:54:34
the scaler went 3 → 2 ("All metrics below target") and terminated replica `ltjgf` with two renders
in flight. Within ~0.3 s supervisord logged dozens of `reaped unknown pid … (terminated by SIGTERM)` lines
(the browser processes), gunicorn began its 30 s graceful shutdown with nothing left to finish, and both requests returned
`render_error` 500 (`BrowserContext.new_page: Target page, context or browser has been closed`).
Evidence: `ContainerAppConsoleLogs_CL`, `ContainerGroupName_s endswith 'ltjgf'`, 09:54:28–09:55:30Z,
and `ContainerAppSystemLogs_CL` `SuccessfulRescale` at 09:54:34 (30-day retention; the readout's
copy is `tmp/research/readout-run-ii-raw.txt`).
`supervisord.conf` has no `stopasgroup`, so the likeliest sender is Playwright's own
`handle_sigterm` (default on), which closes browsers when the Python process gets SIGTERM.
**Unverified.** Size: 2 of 814 requests in that run, both retried by MAS; in August, 4 of the 163
URLs that ever got a 500 got exactly one, against 152 that got four (MAS's
`49-data/http500-urls.csv`; their ladder makes four attempts, so four means every attempt failed and
one means a retry fixed it). So it is real, small, and not where our lost captures come
from. Next step: `tasks/optimization-experiments.md`, lever 3.

**A request that arrives during the switch, to an app at zero, can be orphaned (seen 2026-11-04).**
The deploy of `0.9.5-merge` to `-se` updated the app at 09:12:14, but the platform kept 100 % of
traffic on the old revision until 09:12:58 while the new one pulled and started. A `/health` sent
at 09:12:42 was buffered by the activator for the *old* revision, which scaled a replica for it and
was deactivated 16 s later. The request hung until the client gave up: `ContainerAppHTTPLogs`
shows it on the old revision, no replica, 218.1 s, `DC downstream_remote_disconnect` (query
`ContainerAppHTTPLogs`, `ContainerAppName == 'crawl4ai-service-se'`, from 09:10Z). **`az
containerapp revision list` already showed the new revision at 100 % at that moment**, so it is
not the instrument for "has routing switched". Use the system log line `Setting traffic weight of
'100%' for revision '<new>'` (`ContainerAppSystemLogs_CL`), or a request that lands on the new
revision in `ContainerAppHTTPLogs`. **The log line is not always written:** for revisions
`--0000006` and `--0000007` (2026-11-04 17:20 and 17:50) only the *old* revision's line appeared. With
the old revision at zero replicas and the new ones running, a `/health` answering in under a
second is the check that worked. This is one more reason a deploy waits for MAS to stop calling.

### 2.5 Rollback

**Most incidents do not want an image rollback.** If the symptom is capacity,
cost or replica count, the lever is the scale rule (§3.5), not the image.

**The rollback target of the image that's live is the digest named in the previous
`AITOSOFT_CHANGES.md` entry** (each deploy entry names its digest; this file names no images, §0's
rule). Roll back through the script, so the gates run, with no build:
`DEPLOY_DIGEST=sha256:<older> ./azure-deployment/deploy-image.sh <older-tag>`. The manual
equivalent below points the app at an older **tag** already in ACR: an image-only update, no
build. The app runs `activeRevisionsMode: Single`, so old
revisions are deactivated and garbage-collected; a revision name is not a
rollback target, and a new revision is not necessarily a new image (a scale-rule
change mints one too).

```bash
az acr repository show-tags --name aitosoftacr --repository crawl4ai-service --orderby time_desc -o tsv
D=$(az acr repository show --name aitosoftacr --image crawl4ai-service:<older-tag> --query digest -o tsv)
az containerapp update -n "$APP" -g aitosoft-prod \
  --image aitosoftacr.azurecr.io/crawl4ai-service@$D
az containerapp show -n "$APP" -g aitosoft-prod --query 'properties.template.containers[0].image' -o tsv
```

**The live app names a digest, not a tag** (since MAS's cutover, 2026-11-04; `deploy-image.sh`
keeps it that way). So a tag push or retag changes nothing that runs, and the image field reads
`…@sha256:…`. To name it, map the digest back:
`az acr manifest list-metadata -r aitosoftacr -n crawl4ai-service --query "[?digest=='<sha256:…>'].tags" -o tsv`.

**Trap: never roll back with a plain `deploy-image.sh <older-tag>`** (without `DEPLOY_DIGEST`). It
runs `az acr build` on the current working tree before it deploys (§2.1's grep
shows the order), so it would push today's code under the old tag —
overwriting the good image, so the rollback target no longer exists — and then
ship it. The manual `update` skips the script's fleet-size gate, so check the
replica count first (§2.3); it still mints a revision and kills in-flight renders
(§2.4).

What the tag list cannot tell you:

- **`0.9.2-egress-dns` is burned** — it shipped a `NameError` and lasted 8
  minutes. Never roll back to it.
- `0.9.2-capacity-gate-2` is `0.9.2-capacity-gate` with two comment fixes and one
  defensive guard, rebuilt so the committed tree matches the image. Rolling back
  between them changes nothing useful. Rolling back past both also drops
  `capacity_gate` from 429 envelopes (§3.8).
- **Rolling back past `0.9.2-consent-guard` (2026-08-06) reverts the consent
  guard.** Segment 4 logged 23 × `CONSENT DECLINED node=html structural=True` in
  ~300 renders (7.7 %); on the older image each of those is a 15-byte capture at
  HTTP 500, which MAS retries 3×. It also reverts collapse recovery,
  `unrenderable_content`, the browser-pool cap and the egress DNS fix.
- **Rolling back past `0.9.2-failure-class` reverts a cross-repo contract**
  (`status_code` = final redirect hop; `failure_class` on every result; origin
  faults at HTTP 200 + `success:false`; 5xx reserved for us). MAS's retry branch
  reads the wire status. Coordinate first.

- **Rolling back past `0.9.5-merge` (2026-11-04)** reverts the code to v0.9.2 and Chrome to 151.
  For MAS only the additive changes revert (keyed `links`/`media`, a little markdown whitespace;
  `tasks/upgrade-upstream-v0.9.5.md` §8). **`0.9.5-candidate` is neither a deploy artifact nor a
  rollback target:** it's a test build from before the merge review's fixes.
- **Rolling back past `0.9.5-https-first` / `0.9.5-http-as-asked` (2026-11-04)** brings back
  Chrome 157's refusal of http-only sites and the http → https-placeholder upgrade
  (AITOSOFT_CHANGES).
- **Every tag up to and including `0.9.2-capacity-gate-2` carries `/tmp/project/.env` (the API
  token), `PRIVATE.md` and `tmp/`**, because there was no `.dockerignore`. Decided 2026-11-04: no
  rotation (nothing reached the open internet) and the tags stay. Rolling back to one is safe.

**Image only. Never set env vars during a rollback.**

### 2.6 Manual equivalents

```bash
az acr build --registry aitosoftacr --image crawl4ai-service:<tag> --file Dockerfile .
D=$(az acr repository show --name aitosoftacr --image crawl4ai-service:<tag> --query digest -o tsv)
az containerapp update -n "$APP" -g aitosoft-prod \
  --image aitosoftacr.azurecr.io/crawl4ai-service@$D     # by digest, never by tag (§2.5)
curl -s -o /dev/null -w '%{http_code}\n' "$CRAWL4AI_API_URL/health"
```

**Read an image without running it** (versions, files; a few cents of ACR task time, no Container
App change). The image runs as `appuser`, and `az acr run` sets an unwritable `HOME`, so set it:

```bash
az acr run --registry aitosoftacr --cmd 'aitosoftacr.azurecr.io/crawl4ai-service:<tag> sh -c "export HOME=/home/appuser; pip freeze; google-chrome --version"' /dev/null
```

Record Chrome's version for every image that ships: the build installs current stable, and
`azure-deployment/pip-constraints.txt` pins only the Python packages. Running our test suites inside
an image (real Chrome, amd64) is in `TESTING.md` §"Inside a built image".

### 2.7 Rotating the token — a standalone change, never during a deploy

```bash
NEW_TOKEN="crawl4ai-$(openssl rand -hex 24)"
az containerapp update -n "$APP" -g aitosoft-prod \
  --set-env-vars CRAWL4AI_API_TOKEN="$NEW_TOKEN"
# then update this repo's .env AND tell MAS, in that order
```

This mints a revision (§2.3, §2.4). Do it with a small fleet and no sweep running.

### 2.8 Provisioning reference

The app exists; this is the reproduce-from-scratch record.

- **Env vars** — read names live (§0), never values. Two matter:
  `CRAWL4AI_API_TOKEN`, and `GUNICORN_BIND=0.0.0.0:11235` (upstream's
  `entrypoint.sh` otherwise binds `[::]`). `ENVIRONMENT`, `LOG_LEVEL` and
  `MAX_CONCURRENT_REQUESTS` are inert leftovers.
- **Probes** — HTTP startup and readiness on `/health`, TCP liveness with generous
  thresholds (verified 2026-11-03). The lifespan pre-warms the browser before
  serving, so passing readiness means the browser pool is ready; the liveness
  probe must never kill a busy replica. Probes are set via YAML
  (`az containerapp update --yaml`), not flags — and see the `--yaml` scale-rule
  trap in §3.5.
- **Scale rule** — HTTP rule named `http-renders`, set with the explicit flag in
  §3.5.
- Redis inside the container gets an ephemeral password from `entrypoint.sh`.
- The legacy North Europe deployment (`crawl4ai-v2-rg`) and its token-regenerating
  deploy script were deleted 2026-07-17.

---

## 3. Scaling

### 3.1 The scale trigger and `render_capacity` are different quantities

|  | what it is | units | protects anything? |
|---|---|---|---|
| `render_capacity` (`config.yml`, enforced in-process by RenderGate) | hard cap on simultaneous renders per replica, plus a bounded queue (`admission_queue`, `admission_max_wait_s`) | concurrent renders | **yes — this is the safety mechanism** |
| `concurrentRequests` (ACA HTTP scale rule) | when Azure adds a replica | Microsoft calls it concurrency and defines it as "requests in the past 15 seconds divided by 15", a rate — and what the scaler actually reads is neither (§3.2) | no |

Two numbers in different units cannot meaningfully be equal. Pinning the trigger
to `render_capacity` held it at 2, the runaway setting (§3.2), until 2026-08-08.
**Raising the trigger cannot oversubscribe a replica**: the gate bounds renders,
not the scaler.

**Per-replica render capacity is 2** because a replica is 2 vCPU: benchmarked
2026-07-17, more than 2 concurrent renders degraded every request. Production
telemetry later gave `fleet_cores = −0.13 + 2.45 × concurrency` (r² 0.738), i.e.
~2.4 cores demanded per in-flight render, so a replica at 2/2 is already
oversubscribed. There is no headroom to raise it into.

```bash
grep -nE 'render_capacity|admission_queue|admission_max_wait_s|wall_clock_s|max_browsers|memory_threshold_percent' deploy/docker/config.yml
```

### 3.2 What the scaler actually reads

No public source documents this; our recovery of the metric names appears to be
net-new.

The documented formula is `desiredReplicas = ceil(metric / target)`. Every
request-based reading of `metric` — requests in 15 s ÷ 15 (the documented one),
requests per second, requests in 15 s undivided, instantaneous in-flight —
simulated second by second over three days of a trigger-6 sweep, with the 300 s
scale-down window, predicted a mean fleet of 1.0–2.25 against an observed 11–12.

**The scaled object is backed by eight Envoy metrics**, named in a
`FailedComputeMetricsReplicas` error on 2026-08-11:

```
s0-upstream_rq_total    s0-upstream_rq_active    s0-upstream_cx_total    s0-upstream_cx_active
s1-upstream_rq_total    s1-upstream_rq_active    s1-upstream_cx_total    s1-upstream_cx_active
```

Two scalers (`activator`, `http-scaler`) × four metrics, two of which are
connection counts (`cx`). The only public acknowledgement that connections count
is an ACA maintainer's comment in `microsoft/azure-container-apps#536` (January
2023): "scaling http apps takes into account active connections as well as
requests".

**`upstream_*` is Envoy → replica, so the metric grows with the replica count and
the scaler is self-referential**: more replicas ⇒ more upstream connections ⇒ a
higher metric ⇒ more replicas. Two independent routes give the slope:

- *Fit:* `metric = a·R + b·L` over 1,370 scaling decisions within one regime gives
  **a ≈ 5.2**.
- *Structure:* a replica accepts at most `render_capacity 2 + admission_queue 4` =
  6 concurrent requests, and our `gunicorn --keep-alive 300` (`supervisord.conf`;
  gunicorn's default is 2) holds those upstream connections open, so the metric
  should be ≈ 6 × R.

They agree within ~15 %. Loop gain is `a / trigger`:

| trigger | gain (fit) | gain (structural) | observed |
|---|---|---|---|
| 2 | ~2.6 | 3 | runaway to a fixed point: a bursty synthetic arm plateaued at 38 replicas, flat for four samples (2026-08-08) |
| 6 | ~0.87 | 1.0, neutral | the fleet keeps whatever size a burst gave it and never drains: mean 11.05, slot utilisation ~7–9 % every day of a five-day sweep |
| 12 | ~0.45 | 0.5 | drains to demand: mean 1.97 |

That is why a 2× trigger change moved the fleet 4.7×, which no request-rate model
can produce. **6 was the worst available setting, sitting on the neutral point.
12 is not tuned; it is just above 6.** "Anything ≥ 7 behaves like 12" is an
inference: only 2, 6 and 12 have been run.

**The scaler is fine on smooth load; bursts drive it.** Controlled runs
2026-08-08, all `raw://` (§3.10) at trigger 2, all at MAS segment 3's arrival
rate of 10.7 req/min:

| | requests arrive | peak in-flight | replicas |
|---|---|---|---|
| synthetic, uniform (12 min) | one every 5.6 s | ~2 | **1**, zero scale-up events — `ceil(0.9/2) = 1`, correct |
| synthetic, `--fanout 4` (9 min) | four every 22.4 s | 4 | **38** plateau |
| MAS segment 3 (30 min) | bursty agent traffic | 8 | **30** (the cap then) |

Same rate, 38× the fleet: arrival rate is not the driver. The same bursty arm at
trigger 6 plateaued at 5 replicas with no rejections (p90 +73 %), which is what
justified the first trigger change. Detail: `tasks/done/autoscaler-ratchets-to-the-cap.md`.

**A refuted sibling, so it is not re-fitted:** a model built on *downstream*
(client → Envoy) connections — "≈65 open, held ~300 s, independent of fleet size"
— predicted 6 replicas at trigger 12; the fleet was 2. No fleet-independent
connection count gives 12 replicas at trigger 6 and 2 at trigger 12.

**How sure:** no ACA metric exposes the scaler's value, so `a ≈ 5.2` is a fit over
decisions, not a reading. The metric-name list is observed and is the solid part.
If you touch the scale rule, reason with this model and distrust the fit first.

### 3.3 Documented ACA behaviour that amplifies the loop

- Scale-up stabilization: 0 s.
- Scale-up step: geometric — 1, 4, 8, 16, 32 …, clamped at `max(4, 2 × current)`.
- Scale-down stabilization: 300 s.

Instant up, damped down, on a self-referential metric. Visible in our logs: the
2026-07-17 scale-out went 0 → 4 → 8 → 16 → 19 → 30 in 72 seconds, clamped at the
then-`maxReplicas`.

### 3.4 Knobs that do not exist — stop re-investigating

Verified 2026-08-08 against the ARM spec and Microsoft's docs:

- `pollingInterval` — a real, writable ARM field (API ≥ `2024-08-02-preview`) and
  a no-op: documented as "doesn't apply to HTTP and TCP scale rules".
- `cooldownPeriod` — real, writable, governs only the final replica → 0.
- **The 300 s scale-down stabilization window has no configuration surface
  anywhere in ACA.** `microsoft/azure-container-apps#1418` asks for one (open
  since 2025-02, no Microsoft engagement as of 2026-08). KEDA has
  `behavior.scaleDown.stabilizationWindowSeconds`; Azure does not surface it.

**The only levers are `concurrentRequests`, `minReplicas` and `maxReplicas`.**

### 3.5 Changing a scale setting

```bash
# The trigger — the cost lever. Mints a revision.
az containerapp update -n "$APP" -g aitosoft-prod \
  --scale-rule-name http-renders --scale-rule-type http \
  --scale-rule-http-concurrency <N>

# Verify against the app, never against the update's response
az containerapp show -n "$APP" -g aitosoft-prod \
  --query "properties.template.scale.rules[?name=='http-renders'].http.metadata.concurrentRequests | [0]" -o tsv
```

Then edit `ACA_SCALE_TRIGGER` in `azure-deployment/deploy-image.sh` to match
(§2.2). The new revision restarts every replica and kills in-flight renders (§2.4).

Choosing `<N>`: read the loop-gain table (§3.2) first. Gain is `a / trigger`, and
above 1 the fleet stops tracking demand and runs to a fixed point. **The model
predicts runaway at trigger ≤ 5**: marginally at 5 (gain 1.04 with the fitted
a ≈ 5.2, 1.2 with the structural 6), clearly at 4 (1.3–1.5). **2 is never right**
— gain ~2.6–3, the observed 38-replica plateau, and a "revert" command in this
repo carried 2 until 2026-08-15. 6 is the measured neutral point (~$89/day during
a sweep). 7–11 are untested; the model puts their gain between 6's 0.87–1.0 and
12's 0.45–0.5, so the nearer to 6, the nearer to a fleet that never drains. If
429s at trigger 12 ever cost real captures, the first lever is `minReplicas`
(§3.8), not the trigger.

**Trap: `az containerapp update --yaml` silently drops the scale-rule metadata.**
Measured 2026-07-17: the rule came back with the right name and type and no
`concurrentRequests`, so ACA used its default of 10 — the cause of the 2026-07-16
504 incident. The update reported success. Re-apply with the explicit flag and
verify with `show`.

**`minReplicas` / `maxReplicas`: use the script**, because a raw
`--min-replicas 0` is a silent no-op (the CLI's outer gate is plain truthiness,
so 0 never enters the PATCH body; source lines in the script's header):

```bash
./azure-deployment/batch-scale.sh status    # read
./azure-deployment/batch-scale.sh fix 2     # min = max = 2: the fixed fleet for an announced window
./azure-deployment/batch-scale.sh release   # min 0, max back to deploy-image.sh's ACA_MAX_REPLICAS
./azure-deployment/batch-scale.sh up 1      # emergency only: a floor, max untouched
./azure-deployment/batch-scale.sh down      # undo `up` (keeps max as it is, so never after `fix`)
```

**For MAS's announced windows, the fleet is fixed, not autoscaled** (since 2026-11-04;
`tasks/optimization-experiments.md`, protocol and lever 2). At their shape the scaler lands on 2 or 3
replicas by chance (§4.5), so a fixed 2 makes the cost predictable, and the warm fleet removes the
cold-start 429 burst. Every `fix`/`release`/`up`/`down` mints a revision (§2.4), so do them with
nothing in flight. Outside windows the app autoscales from zero as before. A floor around the clock
is still declined (§3.8).

### 3.6 Ceilings — what can and cannot be bought

**Environment core quota: 100**, shared with MAS's edge app (`aitosoft-edge-se` in `aitosoft-aca-se`
since 2026-11-04; `aitosoft-edge` in the West Europe environment before). The replica ceiling
is `(100 − other apps' cores) / 2`; compute it from the two commands below rather
than trusting a figure (every document said `aitosoft-edge` held 0.25 cores for
weeks after it went to 1.0 — §4.3).

```bash
az containerapp env list-usages -n "$ACA_ENV" -g aitosoft-prod -o table
az containerapp list -g aitosoft-prod --query "[].{name:name, cpu:properties.template.containers[0].resources.cpu, min:properties.template.scale.minReplicas, max:properties.template.scale.maxReplicas}" -o table
```

**Per-replica size: 2 vCPU / 4 GiB was the maximum of the West Europe, Consumption-only
environment.** Tested there 2026-08-02; the error enumerates the allowed set. `-se`'s
`aitosoft-aca-se` is a workload-profiles environment where 4 vCPU / 8 GiB is possible (below; untried):

```
$ az containerapp update -n crawl4ai-service -g aitosoft-prod --cpu 2.0 --memory 8.0Gi
ERROR: (ContainerAppInvalidResourceTotal) ... must add up to one of the following
CPU - Memory combinations: [0.25/0.5Gi] [0.5/1.0Gi] [0.75/1.5Gi] [1.0/2.0Gi]
[1.25/2.5Gi] [1.5/3.0Gi] [1.75/3.5Gi] [2.0/4.0Gi]
```

The command is atomic, so nothing changed. The cause is `workloadProfiles: null`,
a legacy Consumption-only environment. Microsoft's docs contradict each other on
the limits; this rejection is the tiebreak.

**The escape route, priced from Microsoft's docs, not from an attempt.** A
workload-profiles (v2) environment's built-in Consumption profile allows 4 vCPU /
8 GiB at the same meter rate, keeps scale-to-zero, and has no management fee
(those apply only to Dedicated profiles). Per-replica cost doubles because the
resources double. The real price:

- Migration is not in-place: new environment, new `defaultDomain`, so a new FQDN —
  a MAS-visible contract change. (`az containerapp env update
  --workload-profile-type` exists; do not read the flag as an in-place path for a
  live environment.)
- At 4 vCPU per replica the quota gives roughly half as many replicas.
- **If the bigger replica raises `render_capacity`, re-check upstream's
  `GLOBAL_SEM` in the same change.** `server.py` wraps `AsyncWebCrawler.arun`
  class-wide in a semaphore of `crawler.pool.max_pages` permits (`config.yml`; not
  the deep-crawl `max_pages` above it), and the patchright retry's `arun` takes a
  permit too. It runs after the first leg has released its own, so demand is at
  most `render_capacity` — safe only while `render_capacity` < `max_pages`. Past
  that, requests wait silently inside the 180 s fence: the 2026-07-16 incident
  RenderGate was built to end (`aitosoft_admission.py` docstring; the call-site
  comment in `aitosoft_patchright_fallback.py`).
- The 240 s ingress timeout (§6.6) would become configurable:
  `properties.ingressConfiguration.requestIdleTimeout` on the environment needs
  premium ingress, which needs workload profiles (`ingressConfiguration` and
  `workloadProfiles` both null, 2026-11-03). It is an idle timeout, and we send
  nothing until the response is ready, so for us idle = elapsed.
- **Try the cheap lever first:** Microsoft's FAQ says memory-limit overrides are
  "evaluated on a per-case basis". One support ticket might remove the need, and
  nobody has filed one.

**2026-11-04: MAS's cutover made this migration for its own reasons.** `aitosoft-aca-se` has
`workloadProfiles: [Consumption]` where `aitosoft-aca` has `null`, and it has its own 100-core
quota (`list-usages`: 1 used, MAS's edge app). So the 4 vCPU / 8 GiB size, a configurable ingress
timeout and the quota headroom should now be available to `crawl4ai-service-se`. **Read from the
environment's type and Microsoft's docs, not from an attempt;** nobody has tried a resize there, and
the `GLOBAL_SEM` caveat above still applies if `render_capacity` moves with it.

Not needed today. **Right-sizing down is refuted:** the busiest replica exceeds
3.0 GiB in 99 % of minutes, so 1.5 vCPU / 3 GiB does not fit.

### 3.7 Trigger 6 → 12: the smaller fleet is cheaper per request

The only controlled production comparison: the same MAS sweep, one setting
changed on 2026-08-14. Full regimes, 122 h at trigger 6 against 54 h at trigger 12
(read in the 2026-08-17 review; the underlying logs have since expired, §5.1):

| | trigger 6 | trigger 12 |
|---|---|---|
| mean fleet | 11.05 | 1.97 |
| max fleet | 19 | 3 |
| replica-hours | 1,344 | 106 |
| slot utilisation (per-render `[COMPLETE] ⏱` line, excludes queue wait) | 8.9 % | 40 % |
| browser launches per admitted request | 0.339 | 0.110 |
| mean queue wait | 0.041 s | 0.919 s |
| RenderGate rejects per admit | 1× | 27× |
| cost per 1,000 requests | $3.28 | $0.51 (6.4× cheaper) |
| p50 / p99 latency | — | +3.2 % / +67 % |

**Over-provisioning manufactured its own load.** MAS sends a per-company browser
identity, so at 12 replicas a company's ~7 pages scattered round-robin and each
replica paid its own cold Chromium launch. The 12-hour readout put the pool hit
rate at 26.6 % → ~65 % and total fleet CPU at 3.44 → 1.55 cores.

Trap: earlier readouts quote slot utilisation 7.0 % → 54 % and p99 −28 %. The 54 %
came from `sum(RequestDuration)`, which includes admission queue wait; the p99
improvement did not survive the full regimes. Matched windows of different
lengths give slightly different figures for the same comparison (trigger-6
utilisation reads 7.0, 8.7 or 8.9 %); quote the window with the number.

What it does not say:

- **`maxReplicas` is not a cost lever.** Lowering it 45 → 20 saved nothing:
  replica-minutes above 20 across the sweep were 0. It is tail protection.
- **The fleet is only weakly elastic now, by design.** One scale-up event in 30
  minutes of real traffic. A synthetic arm at 1.44× production rate (30 req/min,
  fanout 4, 12 min, `raw://`) held 1 replica throughout, through 38 × 429 (10.6 %)
  and a mean admission wait of 5.26 s against the 15 s limit. Do not wait for
  replicas to appear as confirmation that a burst was handled.

  That arm used a pooled client with 300 s keep-alive (~4 connections carried all
  360 requests) while its trigger-6 comparison used httpx's 5 s default, so two
  variables moved; it is not a clean trigger A/B, and the separating arm
  (`--no-keepalive` at the same rate) has never been run. The consequence: **if
  MAS's client ever starts holding connections longer, our scale-up may largely
  disappear**, and the trigger would need to come down in the same change. We have
  asked MAS not to change their HTTP client in the same sweep as anything else
  (`tmp/mas-repo-messages/52-to-mas-…`).

### 3.8 429s: four sources, one field

Every 429 envelope carries `capacity_gate` (since `0.9.2-capacity-gate`,
2026-08-17):

| `capacity_gate` | source | means | sweep count |
|---|---|---|---|
| `render_slots` | RenderGate: 2 slots + 4 queued full, or 15 s queue wait exceeded | the replica is full — the only real capacity signal | 660 |
| `memory` | the pool's memory guard refusing a new browser; carries `memory_pct` and `limit_pct` | a threshold-crossing on a signal centred on its threshold (§6.4) — not a capacity signal | ~9,870 |
| `browser_pool` | the `max_browsers` cap with nothing idle to evict | | 0 |
| `unspecified` | anything that answered 429 outside render admission: slowapi's inbound limit (1000/min, `memory://` storage, keyed on the ingress proxy's address, so effectively per replica process), or the background-job quota (unreachable at `per_principal: 0`) | never fired; carries no `Retry-After` | 0 |

Sweep counts are the final sweep, 2026-08-09 → 08-16 (console tokens; 10,532 wire
429s). `failure_class` stays `"capacity"` for all four, so older counts remain
comparable. **An absent `capacity_gate` on a 429 means an older image** — the
field is unconditional.

The memory share depends on the regime: 99.1 % of 429s at trigger 6 (47 RenderGate
of 5,434), 88.0 % at trigger 12 (613 of 5,098), 93.7 % across the sweep. Reading
the total as a capacity ceiling sends you at `maxReplicas`, which was never the
constraint. What MAS lost to all of them: **29 captures of 60,874 attempts**; their
retry ladder absorbed the rest (§5.6).

**Cold start is where RenderGate 429s live.** From the start of one trigger-12
sweep, 2-minute bins:

| bin | requests | 429 | p50 | fleet |
|---|---|---|---|---|
| 17:56 | 50 | 14 | 8,716 ms | 1 |
| 17:58 | 46 | 3 | 5,646 ms | 1 |
| 18:00 | 47 | 0 | 4,552 ms | 2 |
| 18:02 | 52 | 0 | 5,840 ms | 2 |

All of it landed at 1 replica; the second replica arrived and the 429s stopped.

**2026-11-04, two joint runs at 5 companies in flight on `-se`:** 54 and 51 wire 429s in 790 and 814
requests, split 32 + 22 and 46 + 5 between `render_slots` and `memory` (console tokens; the
wire counts agree with MAS's to the request). The `render_slots` share is the cold start:
run (i)'s 32 landed 08:32–08:34 on one replica, run (ii)'s 45 of 46 in its first six minutes. MAS's
brain issues up to 6–7 `scrape_page` calls in one turn (2.3–2.4 per scraping turn, MAS's count), and
the gate's own lines show it: `REJECT (queue full): in_use=2/2 queued=4`, i.e. a seventh concurrent
request on one replica. Nothing ran out of retries in either run.

**The ingress is round-robin, decided per request, with session affinity off**
(`stickySessions: null`). Envoy picks the endpoint, then the connection pool, so a
keep-alive client does not pin to a replica. A larger fleet dilutes bursts rather
than absorbing them, and dilution needs the replicas to exist already. MAS's
control: three crossings of 5 concurrent in minute one produced their single 429;
seven crossings after KEDA had scaled produced none.

**So the lever for cold-start 429s is the replica floor, not `maxReplicas` or the
trigger.** A floor around the clock was priced and declined: one pinned replica costs up to ~$7.3/day
at the active rate, less if it qualifies for the idle rate (unmeasured, §4.3). **For an announced
window it's used** (2026-11-04): the fleet is fixed at 2 for the window's duration (§3.5). In window
3 that removed the cold-start burst (render-gate 429s 29 → 7) and gave the day's best latency. **A
single warm replica would not have done it.** The burst lands *at* one replica after it's up,
because MAS's brain fans out to 12–13 in flight against a replica's 6 (per-minute table by replica
count, 2026-11-04, in `tasks/optimization-experiments.md`).

### 3.9 Measuring load

**MAS's `--concurrency N` bounds companies in flight, not renders.** Each
company's agent fetches several pages in parallel: up to 4 when MAS measured it on 2026-08-06, and up to 6–10 per turn (mean ~2.2) with the brain of 2026-11-04 (§3.8). The August measurement
over 3,541 runs: 74 % of companies issued ≥ 2 simultaneous fetches, and at
`--concurrency 2` the peak was 7 in flight — which our side saw as 6 admitted
(`2/2 rendering, 4 queued`) + 1 rejected. So:

- **The in-flight ceiling is ≈ 4N and does not grow with cohort size.** A bigger
  cohort buys duration, not concurrency.
- In the final sweep MAS ran ~5 companies in flight, and mean true concurrency was
  1.68 — agents spend most of their time off our service.
- The fleet's render ceiling is `render_capacity × maxReplicas` (query both); at
  trigger 12 the sweep never got near it (max 3 replicas).

**A replica count is not a load measurement.** MAS's segment 3 (2026-08-08) ran
its whole 30-minute window at the then-cap of 30 replicas at a true concurrency of
~1.2.

- **Concurrency** is `sum(RequestDuration) / window`, from `ContainerAppHTTPLogs`
  only; `StartTime` is arrival, so exact in-flight comes from sweeping overlaps.
  Our console log records `RenderGate ADMIT` but never the release, so it cannot
  give concurrency. `RequestDuration` includes queue wait; for **slot
  utilisation** use the per-render `[COMPLETE] ⏱` line, which starts after the
  gate.
- **Replica count:** the Azure Monitor `Replicas` metric at 1-minute resolution
  (§4.4), cross-checked with `az containerapp replica list` — not `dcount` of
  replica names at coarse bins (§5.3).
- **Health probes do not feed the scaler.** ACA probes hit the pod IP and never
  reach Envoy. The 125 `/health` requests in the sweep's ingress log were all
  `curl/7.88.1` from our own monitoring sessions.

### 3.10 The load generator — test scaling without a third party

**A `raw://` URL is a full-fidelity load generator** — RenderGate, the pool, a
real Chromium launch on a cold replica, the consent pass, scraping, markdown and
the collapse guard; only the navigation is skipped. Render time is a dial
(~1.3 s + `delay_before_return_html`). **Zero egress holds only for
self-contained HTML**: replaying a stored real capture as `raw://` makes the
browser fetch the customer's images and scripts and fire their analytics. The
mechanism, the caveat and how to strip a capture: `TESTING.md` §"`raw://`: the
full render path with no navigation".

```bash
python test-aitosoft/sustained_rate_probe.py --label <name> --rate-per-min 30 \
  --fanout 4 --duration-min 12 --keepalive-expiry 300
python test-aitosoft/cold_burst_probe.py --help    # 429s by capacity_gate, TTFB, queue pressure
cat test-aitosoft/cold_burst_probe.kql             # server-side readback
```

Neither is collected by pytest. They read the token from `CRAWL4AI_API_TOKEN`
without printing it, refuse a warm app without `--allow-warm`, and cap their own
rate and duration. They are committed rather than rebuilt because a rebuilt
generator is not a valid B-arm against a recorded A-arm.

**Trap: httpx's default `keepalive_expiry` is 5.0 s.** At 19 req/min with
`--fanout 4` arrivals are 12.6 s apart, so a "pooled" arm silently became a second
un-pooled arm. Set `--keepalive-expiry` explicitly on both arms.

Reach for this before any live host: it is byte-identical across A/B arms and
costs no third party anything.

---

## 4. Cost

### 4.1 The instruments, and what each cannot tell you

- **There is no configured cost export.** The figures here came from portal
  usage exports that Tero downloaded (some into gitignored `tmp/azure-costs/`).
  If cost matters again, configuring an export is the first move.
  ```bash
  az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.CostManagement/exports?api-version=2023-11-01"
  # -> {"value": []}
  ```
- **The Cost Management query API returns `rows: []`, by documented design.** The
  subscription's quota ID is `Sponsored_2016-01-01`, which Microsoft lists by name
  among offers Cost Management does not support. Not a permissions artefact: the
  same query against another subscription returned records. **Trap: "the API
  returned no records" is not "there was no cost"** — reading it that way let
  ~$89/day run unnoticed for five days.
  ```bash
  az rest --method get --url "https://management.azure.com/subscriptions/$SUB?api-version=2022-12-01" --query subscriptionPolicies.quotaId -o tsv
  ```
- **The usage export is in USD and has no currency column**, no app-name column,
  and no resource column (`ResourceGuid` is a meter ID). Its fields:
  `SubscriptionName, SubscriptionGuid, Date, ResourceGuid, ServiceName,
  ServiceType, ServiceRegion, ServiceResource, Quantity, Cost`. **Its Container
  Apps lines cover the whole environment** — ours *and* MAS's edge app — so attribution needs
  subtraction (§4.3). Since 2026-11-04 there are two environments (`aitosoft-aca-se`, and the idle
  West Europe `aitosoft-aca` until MAS deletes it); the export's `ServiceRegion` should separate
  them (unverified: no export has been read since the move).
- **Our own replica-hours predict the invoice** (§4.4), which makes the Azure
  Monitor `Replicas` metric the usable instrument — within its 30-day query window
  and 93-day retention (§5.1).

### 4.2 The rate, and the currency trap

Measured against `prices.azure.com` on three meters, 2026-08-17:

```
$0.000034 / vCPU-second  +  $0.000004 / GiB-second
  = $0.3024 / replica-hour at 2 vCPU / 4 GiB
```

**Trap: euro figures in older files are dollars.** They were read off the USD
export. Azure's EUR list is 0.8775 × USD.

| as written in older files | actually |
|---|---|
| `€398.89 for one sweep` | $398.89 ≈ €350 |
| `~€89/day → ~€14.5/day` | ~$89 → ~$14.5/day ≈ €78 → €12.7 |
| `~€0.10/replica-hour` | $0.3024/replica-hour — the old figure was ~3× low, which made over-provisioning look affordable |

### 4.3 Idle billing, and the other app in the export

ACA's idle rate discounts **vCPU only** — memory bills the same — so an idle
replica is ~3.5× cheaper, not the ~8.5× a naive read of the price page suggests.
Idle requires `minReplicas > 0` and the revision sitting at its minimum; above the
minimum every replica bills active. **At `minReplicas: 0`, our app (`-se` or West Europe) never
bills idle**, and scale-to-zero means it bills nothing between sweeps.

So the export's idle lines are other apps — in practice `aitosoft-edge`, pinned at
`min = max = 1`. **It was resized from 0.25 vCPU / 0.5 GiB to 1 vCPU / 2 GiB at
2026-08-14 14:12 UTC** (revision `aitosoft-edge--0000043`, verified 2026-11-03 with
`az containerapp revision list -n aitosoft-edge --all`). Idle vCPU-seconds in the
export went from ~19,100–19,450/day (2026-08-09..13) to ~78,000/day, and idle cost from
~$0.23 to ~$0.93/day. **Trap: the ~4× jump in idle cost from 2026-08-14 is the
platform repo's app, not this service.** `aitosoft-edge` also contributes ~$0.49/day
of active cost, which is the background to subtract below.

For scale: 2026-08-10..14 (trigger 6), idle was $1.02 of $374.54.

### 4.4 Our accounting predicts the invoice

Two reconciliations, in two regimes:

**Trigger 6, 2026-08-10..14:** 8,893,189 billed vCPU-seconds ÷ 2 vCPU = 1,235
replica-hours, against 1,262 counted independently from Log Analytics replica
counts — within 2.1 %, and within 0.5–1.7 % day by day. Memory billed at exactly
2.0× the vCPU-seconds (the enforced 1 vCPU : 2 GiB pairing).

**Trigger 12, checked 2026-11-03** against a usage export for the two full
trigger-12 sweep days:

| day (UTC) | export: Container Apps active | minus `aitosoft-edge` (~$0.49) | `Replicas` metric (1-min average, summed) × $0.3024 |
|---|---:|---:|---:|
| 2026-08-15 | $14.86 | $14.37 | 48.0 h → $14.52 |
| 2026-08-16 | $13.81 | $13.32 | 44.1 h → $13.33 |

Within 1 %. So **$0.605 per hour of sweep (2 replicas × $0.3024) is invoiced, not
just modelled**, and a config change can be priced from our own telemetry before
it is made. Reproduce the replica-hours (verified 2026-11-03):

```bash
az monitor metrics list --resource "$APP_ID" --metric Replicas --interval PT1M --aggregation Average \
  --start-time 2026-08-15T00:00:00Z --end-time 2026-08-16T00:00:00Z \
  --query "sum(value[0].timeseries[0].data[?average!=null].average)" -o tsv    # ÷ 60 = replica-hours
```

**Trap: across a revision change, the unsplit series averages the revisions instead of adding
them.** At the 0.9.5 deploy on 2026-11-04, one replica ran on each of two revisions at 09:14, and
the unsplit 1-min Average read 1.0. Split by revision, it read 1.0 + 1.0 (09:13: 0.75 unsplit
against 1.0 + 0.5). The recipe above is right only for spans with one revision. Every deploy, and
every `minReplicas` change, mints a revision. For those spans, split and sum the series:
`--filter "revisionName eq '*'"`, then sum every `timeseries[*]`.

**Cost per company ≈ $0.605/h × company wall-clock ÷ companies in flight.** For
August: 97 s ÷ 5 in flight = 0.33¢, matching $0.51 per 1,000 requests × 6.4
requests per company.

### 4.5 Where the bill stands

- **Trigger 6:** Container Apps cost $398.89 for 2026-08-09..14 (18,374 companies;
  $0.0217/company, $0.0032/page) at 8.9 % slot utilisation.
- **Trigger 12:** 6.4× cheaper per request. The fleet held at 2 across a 1.6× swing
  in load, so the bill is `2 × $0.3024 × wall-clock`. The remaining idle capacity
  is queueing headroom, not over-provisioning — 29 % of admits already wait, and a
  one-replica probe rejected 10.6 %. **At August's request rate the fleet was at its floor; do not
  re-run the over-provisioning argument against it.** At the 2026-11-04 joint runs' higher rate it
  ran at 3 (next bullets).
- **Between sweeps:** $0 for this service. The standing line is MAS's edge app (`aitosoft-edge-se`,
  plus `aitosoft-edge` until West Europe is deleted).
- **Levers:** for MAS's windows our own lever is the fixed fleet (§3.5; window 3). The rest are
  MAS's: pages per company and their `delay_before_return_html: 2.0` (~37 % of our mean render time)
  act through their wall-clock per company (`tasks/optimization-experiments.md`, levers 1 and 4).
- **2026-11-04, the joint runs and series 1 on `-se` (75 companies each; the ledger in
  `tasks/optimization-experiments.md` is the home for per-window figures): the cost per *request* follows
  the fleet size the scaler happens to pick, and the cost per company follows that times pages per
  company.** Instruments: Azure Monitor
  `Replicas` (1-min average, split by revision and summed over the window plus the whole tail, to
  the minute the fleet reached zero) × $0.3024, against MAS's request counts. Script:
  `azure-deployment/replica-minutes.sh <t0> <t1> <t2>`.

  | | requests / company | replica-min | ¢ / request | ¢ / company | fleet |
  |---|---:|---:|---:|---:|---|
  | August trigger-12 sweep | 6.4 | — | 0.052 | 0.33 | 2 at ~19 req/min |
  | run (i), v0.9.2 | 10.53 | 87.0 (69.5 + 17.5 tail) | 0.056 | 0.58 | 3 at ~32 req/min |
  | run (ii), v0.9.5 | 10.85 | 89.5 (68.0 + 21.5 tail) | 0.055 | 0.60 | 3 at ~32 req/min |
  | window 1, never-scraped | 9.32 | 64.0 (48.0 + 16.0) | 0.046 | 0.43 | **2** at ~28 req/min |
  | window 2, never-scraped | 8.75 | 95.0 (77.5 + 17.5) | 0.073 | 0.64 | **3** from minute 13, at ~22 req/min |
  | window 3, fleet **fixed at 2** | 8.99 | 70.0 (56.0 + 14.0) | 0.052 | 0.47 | 2 by `batch-scale.sh fix 2` |

  **Windows 1 and 2 retire "cost per request is flat".** Nothing changed on our side between them,
  and the fleet went to 3 at a *lower* request rate. Window 2 had ~14 % more render-seconds (p90
  16.5 s vs 12.0), but 50 % more fleet for two-thirds of the window. The scaler is burst-driven
  (§3.2), so at this shape 2 or 3 is close to chance (3 of 4 windows went to 3). **Window 3 fixed the
  fleet at 2** (`batch-scale.sh fix 2`): −28 % per request against window 2, with the cold-start
  429s gone and the best latency of the three windows. Against window 1's lucky 2 it is +14 %, the
  warm-up minutes. **A `minReplicas`/`maxReplicas` change mints a revision that starts as many
  replicas as the old one had, even with nothing calling** (2 at 16:21:05 after the release, idle
  ~5 min). So a release costs about one natural tail.

  **Corrected 2026-11-04 (afternoon).** The first readout of each run summed the metric before the
  fleet reached zero and reported 77.5 and 81.5 replica-minutes (0.049 / 0.050 ¢ per request, 0.52 /
  0.55 ¢ per company). Re-read once the fleet was at zero, the same recipe gives the table above.
  The tail steps 3 → 2 → 1 → 0 over ~10–16 min after the last request (each step waits out the
  300 s scale-down window; the last replica waits out the 300 s cooldown), so **read replica-minutes
  only once `Replicas` is back at 0.** The August figure is day-scale and invoice-checked (§4.4), so
  it never had this problem.

  So the fleet ran at 3 at ~32 requests/min where August held 2 at ~19 (two points, not a curve).
  Render slots were ~70 % busy inside each window and 53–57 % counting the tail: the summed
  `RequestDuration` of the 200s (5,934 s and 5,649 s, queue waits included) over replica-minutes ×
  60 × 2 slots. Consequences:
  - **a faster brain shortens a run without making our cost per company cheaper**: the same pages
    and render-seconds arrive sooner, and the fleet scales up to meet them;
  - **pages fetched per company is the lever on our side of the bill**: ≈0.055 ¢ of render each;
  - **a short window carries fixed overhead**: a cold start (3–4 min at one replica, with the
    `render_slots` 429 burst) and an idle tail of ~10–16 min after the last request, 20–24 % of a
    25-minute window's replica-minutes. For comparing configurations on short windows, price per
    request, and report the window and its tail separately.
  MAS's model cost was 0.52–0.77 ¢ per company across these runs, and their all-in ~2.3–2.6 ¢ (web
  search the largest line). So our render is roughly a fifth of a company's total cost. Readouts: `tmp/research/run-i-readout-2026-11-04.md` (gitignored), `tmp/mas-repo-messages/80-to-mas-…`.
- **Cheaper architecture, priced and rejected:** ACA capped at 4 (~$29/day) matches
  6 PAYG D4as_v5 VMs (~$30/day) with no migration and keeps scale-to-zero, which
  matters because a sweep is ~17 % of the calendar. Azure Functions cannot run
  these containers; ACI has no autoscaling.

---

## 5. Observability

### 5.1 Tables, routes and retention

**Console and system logs arrive via the environment's `appLogsConfiguration`
into legacy custom tables** — `ContainerAppConsoleLogs_CL`,
`ContainerAppSystemLogs_CL`, with `_s` / `_d` suffixed columns.
**`ContainerAppHTTPLogs` arrives via the `aca-http-logs` diagnostic setting into a
native table** — no suffixes, typed columns. The diagnostic setting is HTTP only on
purpose: console and system already arrive the other way, and enabling both would
double-ingest and double-bill. Every suffix trap below follows from this.

```bash
az monitor diagnostic-settings list --resource \
  "$(az containerapp env show -n "$ACA_ENV" -g aitosoft-prod --query id -o tsv)" -o json
az containerapp env show -n "$ACA_ENV" -g aitosoft-prod --query properties.appLogsConfiguration -o json
```

**Log Analytics retention is 30 days** (`PerGB2018`, no daily cap):

```bash
az monitor log-analytics workspace list -g aitosoft-prod --query "[].{sku:sku.name, retention:retentionInDays, cap:workspaceCapping.dailyQuotaGb}" -o table
```

The August sweep's per-request logs are gone. The only surviving per-request
record of it is MAS's data dump in gitignored `tmp/mas-repo-messages/49-data/`
(61,937 timing rows, 5,511 retry rows, hourly aggregates, per-host 500 tables,
terminal outcomes). **After each sweep, archive the aggregates you will want
while the window is open** — or raise retention, which nobody has priced.

**Azure Monitor platform metrics are retained 93 days, but the metrics API
silently truncates any window longer than ~30 days** to its last ~30 days, with no
error. Verified 2026-11-03: a daily `Replicas` query for 2026-08-10 → 11-03
returned 2026-10-03 onward; a query for 2026-08-14 → 08-17 returned all of it.
Query in ≤ 30-day windows.

### 5.2 What each instrument answers

| Instrument | Answers | Cannot answer |
|---|---|---|
| `ContainerAppHTTPLogs` | What MAS received: `StatusCode`, `RequestDuration` (ms), `StartTime` (arrival), `BytesSent`, `ResponseFlags`, `ResponseCodeDetails`, `UpstreamRequestAttemptCount`, `UpstreamHost`, `EnvoyPodName`, `ConnectionId`, `ReplicaName`, `UserAgent`. The only surface that sees a request the ingress handled without a container | Anything inside the app. No history before 2026-08-05 |
| `ContainerAppConsoleLogs_CL` | Our counters: `RenderGate ADMIT`/`REJECT`, `RESULT`/`ORIGIN`/`TERMINAL FAILURE`, `RENDER DEFECT`, `COLLAPSE RECOVERED`, `CONSENT DECLINED`, `WALL-CLOCK FENCE 504`, the `📊 Pool:` memory line, `supervisord started with pid 1` | Wire outcomes; anything the ingress absorbed; slot release, so not concurrency |
| `ContainerAppSystemLogs_CL` | Platform events in `Reason_s`: `KEDAScaleTargetActivated`, `SuccessfulRescale`, `ContainerStarted`, `OOMKilled`, `ReplicaUnhealthy` | Usually *why*; an isolated memory kill emits nothing (§6.2) |
| Azure Monitor metrics | `Replicas` (per minute — the basis of every replica-hour figure), `RestartCount`, `UsageNanoCores`, `MemoryPercentage` | Anything per request |

**Console and wire disagree by design.** Segment 2 (2026-08-06): console showed
39 `RESULT FAILURE` lines while the wire showed 261 × 200, 12 × 500, 1 × 429,
because most failure classes are deliberately 200 + `success: false`. Quoting
console counts as MAS's error rate overstates it ~3×.

### 5.3 Query traps — each cost a session

`BadArgumentError: The request had some invalid properties` names nothing. It
usually means an identifier in the query is wrong (a column name, or a reserved
word), not that the logic is unsupported; check column names against a real row
first.

| Trap | What happens | Do instead |
|---|---|---|
| **`contains` and `has` are term-based on `_CL` text columns** | A multi-word needle becomes an AND of terms, not a phrase. Measured 2026-08-16 on `CONSENT STRUCTURAL`: `contains` 383, `has` 383, `contains_cs` 0, `indexof(…) >= 0` 0; the truth is 0, and the 383 were ordinary `CONSENT DECLINED … structural=False` lines. It can only over-count, and over-counts most on the rare tokens you are hunting — here it produced a false refutation of a correct claim | `indexof(Log_s, "…") >= 0` for every multi-word token. Slower, irrelevant at our volume. `contains` is often harmless (`RenderGate ADMIT` gave 184,404 under both) but you cannot know in advance |
| `ContainerAppConsoleLogs` without `_CL` | Exists, is empty, returns no error — answers "zero" to everything (re-verified 2026-11-03) | Always `_CL` |
| `first`, `last`, `kind` as column names | `BadArgumentError` — reserved words (verified 2026-11-03 with `summarize kind=count()`) | `t0`, `t1`, `n_kind` |
| `-o tsv` on `az monitor log-analytics query` | Columns come back alphabetical, not in `project` order; positional reads silently transpose numbers | `-o json`, key by name |
| Metrics API window > ~30 days | Silently truncated to the last ~30 days (§5.1) | ≤ 30-day windows |
| Console logs are workspace-wide | `aitosoft-edge` logs into the same table at ~280× our volume when we are idle (1.37 M vs 4.9 k lines, 30 days to 2026-11-03) | `where ContainerAppName_s == "crawl4ai-service-se"`. The replica column is `ContainerGroupName_s`; there is no `ReplicaName_s` |
| `ContainerAppHTTPLogs` is environment-wide | Same problem | `where ContainerAppName == "crawl4ai-service-se"` |
| `ContainerAppHTTPLogs` column guesses | `StatusCode_d`, `ReplicaName_s`, `DurationMs_d`, `ContainerAppName_s` do not exist | Unsuffixed: `StatusCode`, `ReplicaName`, `RequestDuration` (ms), `ContainerAppName`. Wrap arithmetic in `toreal()`; columns arrive as strings in some paths |
| `ConnectionId` alone | Unique only per Envoy pod (there are 2); keying on it merged connections and inflated lifetime 3× | Key on `(EnvoyPodName, ConnectionId)` |
| `ContainerAppSystemLogs_CL.Count_d` | A cumulative per-pod tally (the Kubernetes event `count`), so `count()` under-counts and `sum(Count_d)` over-counts. One replica's `OOMKilled` rows read 1,2 → 3,4 → … → 9,10: `count()` 10, `sum` 55, truth 5 | Count distinct `(ReplicaName_s, TimeGenerated)` |
| Grepping `Log_s` for OOM | `OOM` appears only in `Reason_s`, and the exit code is quoted (`exit code '137'`) | `where Reason_s == "OOMKilled"`, then parse the exit code out of `Log_s` (§6.2) |
| A marker inside an exception message | Repeated by the traceback: one dead-domain request emits `DNS: host does not resolve` in four console lines (sweep: 5,252 vs 1,313) | Count the single-emission token: `ORIGIN FAILURE` + `failure_class=origin_unreachable` |
| `[FETCH]`, `[COMPLETE]`, `Anti-bot retry` lines | They are crawl4ai's `AsyncLogger`, which prints only while the request's `verbose` is on: `arun` sets `self.logger.verbose = config.verbose`, and `CrawlerRunConfig.verbose` defaults to `True` but is on the untrusted allowlist, so a client can switch these lines off. MAS did not, through the August sweep. Two of our measurements stand on them: `max_retries` (read from `Anti-bot retry n/1`) and slot utilisation (the `[COMPLETE] ⏱` line, §3.7) | If they fall to zero while `RenderGate ADMIT` continues, suspect a client sending `verbose: false` before suspecting the service. Our own counters (`RenderGate`, `… FAILURE`, `CONSENT …`, `📊 Pool:`) use stdlib `logging` and cannot be silenced this way |
| Summing `[COMPLETE]` lines per request | A patchright-retried request emits two, against one `ADMIT` (segment 2: 289 lines, 261 admits). Summing all of them put Kübler's segment-1 cost at 266.5 s; the 2026-08-06 correction dropped the first-leg lines as "nested inside the request's total" and got 196.9 s, i.e. the sum read ~35 % high. Caveat: in today's code the two legs are separate, sequential `arun` calls with their own timers (`api.py` `_crawl_with_patchright`), which does not look nested, so which figure is right is unsettled | Count requests by `ADMIT`. Before summing `[COMPLETE]` seconds, decide whether you want slot time (both legs hold the slot) or something else, and say which |
| `contains "reap"` | Matches supervisord's benign `reaped unknown pid … exit status 0` by the thousand | Match the full token with `indexof` |
| `az containerapp replica list -o table` | Hides `restartCount`, the field that answers "did anything crash" | `-o json --query "[].{name:name, created:properties.createdTime, restarts:properties.containers[].restartCount}"` |
| `RestartCount` metric at `PT1M` | Emitted only every 5 minutes (reads 0 four bins in five), and cumulative per replica | Sum the series; cross-check console `supervisord started with pid 1` (they matched exactly at 74) |
| `dcount(replica)` at 10-minute bins | Reports churn as concurrency (30 vs 6) | 1-minute bins; the `Replicas` metric |
| `dcount(...)` without `by ContainerGroupName_s` | A per-replica count cannot bound a global cardinality | Add the `by`, then reason about the union |
| A memory trend from a per-tick window **maximum** | A maximum only grows as the window grows; consecutive ticks manufacture a rising line from flat data | Keep `by bin(...)` |
| A memory **percentile** | The janitor samples every 10 s above 80 %, 30 s above 60 %, 60 s otherwise, oversampling high states ~6× (measured overstatement 5.3× for time-above-X) | `max` and event counts are unbiased; percentiles are not |
| Pairing `mem=` with `hot=`/`anon=` on the same line | The janitor reads `mem_pct` before its sleep and logs it after, so it is up to 60 s older than the counts beside it | Treat `mem=` as the previous tick's |
| Counting 504s from the console | The fence logs one `WALL-CLOCK FENCE 504` line each, but a 504 the ingress produces itself (its 240 s timeout, a cold-start failure) never reaches the app | Count 504s in `ContainerAppHTTPLogs`, which cannot miss them |
| `dcountif()`, bounded `make_set()`, datetime aggregates in `summarize` | Rejected by the query endpoint | `dcount()` + `where`; unbounded `make_set()`; `min()`/`max()` outside |
| Running a query right after the event | Ingestion lags several minutes; an early query answers "nothing happened" | Query ~5 min after, and again ~30 min after |

**Counting rules:**

- **Count failures by `failure_class=`, never by token.** `RESULT FAILURE` (the
  result loop) and `ORIGIN FAILURE` / `TERMINAL FAILURE` (the exception path) are
  disjoint; no request emits both. Querying one token reported 9
  `origin_unreachable` events in segment 2 when the truth was 21 on 13 companies,
  because a dead domain is refused before render admission and only ever emits
  `ORIGIN FAILURE`.
- **We cannot count HTTP 404s; MAS can** (13:1 in segment 3). A 404 with a styled
  "not found" body renders fine ⇒ `success: true`, no log line, while the envelope
  still carries `status_code: 404`. `failure_class` answers "whose fault";
  `status_code` answers "what did the origin say".
- **Ingress `/crawl` − `RenderGate ADMIT` = pre-admission dead-DNS refusals +
  `RenderGate REJECT` + requests that never reach the gate** (static mode, which
  returns before it; 400s and 401s refused earlier). A memory 429 is refused
  *after* admission and has already logged `ADMIT`, so it is not in this identity.
  Trap: the older form "= pre-admission refusals + 429s" reconciled segment 2 only
  because segment 2 had no memory 429s.

  **The final sweep does not reconcile, and nobody knows why.** 186,178 − 184,404
  = 1,774, against 1,313 DNS + 660 REJECT = 1,973: 199 more refusals than the
  subtraction leaves room for (0.1 % of requests), and the never-gated terms widen
  the gap rather than close it. The logs expired before anyone looked. Untested
  candidates: mismatched window edges (199 is ~11 minutes of sweep traffic),
  duplicated console ingestion, or an `ORIGIN FAILURE … origin_unreachable` raised
  after admission. Next sweep, join `ADMIT` and `ORIGIN FAILURE` on `url=`. The
  companion identity, `RenderGate REJECT` + memory refusals = wire 429s, held to
  the request at trigger 12 (613 + 4,485 = 5,098) and was off by 4 at the regime
  boundary.

### 5.4 Starting queries

```bash
az monitor log-analytics query -w "$LAW_ID" --analytics-query '<kusto>' -o json
```

```kusto
// Wire truth: what MAS received
ContainerAppHTTPLogs
| where TimeGenerated > ago(20m)
| where ContainerAppName == "crawl4ai-service-se"
| summarize n=count(), p95_s=round(percentile(toreal(RequestDuration),95)/1000.0,2),
            max_s=round(max(toreal(RequestDuration))/1000.0,2)
    by StatusCode, ResponseFlags, ResponseCodeDetails, via_activator=isempty(ReplicaName)
```

**An empty `ReplicaName` does not mean no container saw the request.** In the
final sweep, 29 rows had one; 22 were `200` / `via_upstream`. All carried
`UpstreamHost 100.100.248.100:4045` — the ACA activator, a fixed platform
address — and each landed on a `KEDAScaleTargetActivated`. They are requests
buffered during scale-from-zero: a cold-start marker, never a failure.

**The real "ingress could not get an answer from a container" signal is
`ResponseFlags != "-"` or `UpstreamRequestAttemptCount > 1`**: 2 rows in 186,178
(`503` / `URX,UF` / `upstream_reset_before_response_started`). A raced upstream
close shows as `503`/`UC`, never as a 502.

```kusto
// Platform events — replica history stated, not inferred
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(1h)
| where ContainerAppName_s == "crawl4ai-service-se"
| where Reason_s in ("SuccessfulRescale","AssigningReplica","ContainerStarted","OOMKilled")
| project TimeGenerated, Reason_s, ReplicaName_s, Log_s | order by TimeGenerated asc
```

```kusto
// Pool memory — read anon, not the percentage (§6.4)
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(20m)
| where ContainerAppName_s == "crawl4ai-service-se"
| where indexof(Log_s, "Pool:") >= 0 and indexof(Log_s, "mem=") >= 0
| extend mem_pct = toreal(extract(@"mem=([\d.]+)%", 1, Log_s)),
         anon_mb = toreal(extract(@"anon=([\d.]+)MB", 1, Log_s))
| summarize n=count(), max_mem=max(mem_pct), max_anon=max(anon_mb), anon_p50=percentile(anon_mb,50)
    by bin(TimeGenerated, 5m)
```

All three verified to run 2026-11-03. For a whole run window, `azure-deployment/window-readout.sh`
packages these and more (failures by class and replica, memory, platform events);
`azure-deployment/window-watch.sh` is the during-the-run version.

### 5.5 The memory alert fires and pages nobody

```bash
az monitor metrics alert show -n crawl4ai-se-memory-high -g aitosoft-prod \
  --query "{enabled:enabled, sev:severity, window:windowSize, freq:evaluationFrequency, crit:criteria}" -o json
az monitor action-group show -n crawl4ai-oncall -g aitosoft-prod \
  --query "{email:emailReceivers, sms:smsReceivers, webhook:webhookReceivers, arm:armRoleReceivers, push:azureAppPushReceivers}" -o json
# Fired instances (monitorCondition is not a field of the alert resource — querying it there returns null forever)
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&timeRange=30d" \
  --query "value[?contains(name,'crawl4ai')].{name:name, state:properties.essentials.monitorCondition, start:properties.essentials.startDateTime}" -o table
```

- **The action group has zero receivers of any kind** (re-verified 2026-11-03).
  The alert is enabled and evaluating; nobody is paged.
- **It reads platform `MemoryPercentage`** (`max > 85` over 5 min,
  `azure-deployment/setup-memory-alert.sh`) = `WorkingSetBytes / limit` — the same
  working-set definition as our guard, divided by ~3.92 GiB allocatable, so ~2.2
  points higher. It inherits the guard's problem (§6.4): a threshold at 85 on a
  signal whose median is above 85. Over 30 days to 2026-08-16 it fired 32 times
  for 170.8 hours, longest episode 52 hours. The two readings are one measurement
  with two denominators, not corroboration.
- Fixing delivery without moving the threshold would page continuously, which is
  why it stays unwired. `azure-deployment/setup-memory-alert.sh <email>` recreates
  the rule and a receiver (idempotent).

### 5.6 What normal looks like, and what defects cost

`az` cannot answer this, so it is recorded. Both columns are the final MAS sweep;
the first is its trigger-6 opening, the second the whole run.

| | first 39.4 h (2026-08-09 14:19 → 08-11 05:44, trigger 6) | whole sweep, 175.5 h (2026-08-09 → 08-16; trigger 12 from 08-14) |
|---|---|---|
| `/crawl` requests | 36,783 | 186,178 |
| 200 | 94.9 % | 93.6 % |
| 429 | 4.1 % | 5.66 % (RenderGate 0.35 %) |
| 5xx | 0.68 % | 0.69 % |
| 504 | 0 | 0 |
| ingress could not reach a container | — | 2 |
| mean true concurrency | 1.45 | 1.68 |
| p50 / p90 / p99 | 4.99 / 7.17 / 29.68 s | — |
| largest response | 31.1 MB | 32.6 MB (none over 100 MB) |
| container restarts | — | 74 (40 before 08-14, 34 after) |

- **A 504 is abnormal** — zero across the whole sweep.
- **`BytesSent` is the only payload-size instrument in either repo.** Nothing read
  it until 2026-08-09, when one page turned out to have returned 232 MB four times
  at HTTP 200 `success: true` with no log line. If asked "is anything
  pathological", this column answers what no counter does.
- **A 429 rate is not a threshold** (§3.8).

**Size the harm before opening an investigation.** MAS's terminal accounting for
the sweep counts pages we cost them, which is the unit that matters:

| attributed to us | captures lost (of 60,874 attempts) |
|---|---:|
| our 500s (`render_error`) | 156 |
| our 429s (`capacity`) | 29 |
| `render_defect` | 27 |
| `unrenderable_content` | 4 |

86.1 % of attempts stored; 95 % of all failures were the origin (dead domains,
404s, blocks). Two requests failed hard at the wire, both when the two replicas
restarted together. So a 5xx costs MAS ~5× what a 429 does, the opposite of where
attention naturally goes. The memory-guard family took weeks of sessions across
two repos and cost 29 captures; the most valuable change in six months was one
config number (§3.7). **If you cannot state an upper bound on what a defect costs,
that bound is the first measurement.**

---

## 6. Failure modes that leave no trace

### 6.1 Exit 137 has at least three causes on ACA

1. A real OOM — the cgroup memory limit.
2. SIGKILL after the 30 s grace on scale-down or scale-to-zero (§2.4). Expected.
3. **Ephemeral-storage eviction at the 8 GiB cap.** We launch Chromium with
   `--disable-dev-shm-usage`, which moves its shared memory into `/tmp` — the same
   ephemeral budget. Nothing watches it, and it has the identical signature to an
   OOM. If you chase a 137 and the memory series is unremarkable, this is the
   untested hypothesis.

### 6.2 ACA labels roughly one memory kill in five

ACA emits `OOMKilled` only for a repeat kill inside the kubelet crash-backoff
window. Measured over the 53-hour trigger-12 window: 34 container restarts, of
which 7 were labelled — those came 1.2–6.8 minutes after the same replica's
previous boot — and 27 unlabelled, median 178 minutes after, none under 10.
**An isolated memory kill produces no platform event at all**: no `OOMKilled`, no
`StoppingContainer`, no rescale pair. It appears only as a restart.

- Across the whole sweep: 8 labelled kills (the first at **2026-08-13 12:42:18**
  on the 12-replica fleet, 7 after the trigger change) and 74 restarts.
- **2 `OOMKilled` rows carried exit code 0** — scale-downs mislabelled during a
  node event. Parse the exit code; never trust `Reason_s` alone.
- ACA emits two rows per kill for one pod. Trap: they read as two containers.
- **The complete instrument is restarts**: console `supervisord started with pid`
  differenced against each replica's first boot, or the `RestartCount` metric
  (summed). They agreed exactly at 74. "No `OOMKilled` tonight" is not "no OOM
  tonight".

```bash
az monitor metrics list --resource "$APP_ID" --metric RestartCount --interval PT1M --aggregation Total -o json
```

### 6.3 A container restarts without the replica changing

The replica object survives and its `createdTime` never moves; most restarts carry
no `Reason_s`. A session reading `az containerapp replica list -o table` sees
healthy replicas and concludes nothing happened — this happened here twice. The
`properties.containers[].restartCount` field on the same object does show it
(§5.3 for the `-o json` query).

```kusto
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h)
| where ContainerAppName_s == "crawl4ai-service-se"
| where Reason_s == "ContainerStarted"
| project TimeGenerated, ReplicaName_s, Log_s | order by TimeGenerated asc
```

Any `ContainerStarted` not within ~10 s of that replica's creation is a silent
restart; confirm with console `supervisord started with pid 1`. Ordinary scale
churn produces the same line, so rule out a `SuccessfulRescale` scale-down/up pair
before calling one a crash.

### 6.4 Memory: no reading predicts a kill, and there is no leak

**The guard's threshold sits inside its own signal.** `crawler_pool`'s memory guard
refuses a new browser when `utils.get_container_memory_percent()` reaches
`memory_threshold_percent` (85). That reading is cache-inclusive — it subtracts
only `inactive_file`, and under sustained crawling the cache is *active*
(2026-08-10: the guard read 88.7 % while `anon` was 68.6 %, with 583 MB of active
file cache counted in). Its distribution: p25 82 %, p50 86.5 %, p75 90 % over 11 h
and ~6,000 samples (2026-08-14/15); unconditional p50 86.6 % with 60.8 % of samples
above 85 % over the 53-hour trigger-12 window — while `anon` stayed flat (p50
~2,900 MB of 4,096). So ~1,000 refusals a night is a threshold-crossing count on a
signal centred on the threshold: a one-point wobble moves it tens of percent. Both
repos once read a trend into it ("5.9 → 9.2 per 100 admits"; "68.7 per 1,000,
outside the band"), and both were the same artefact. **Count refusals; never
interpret them or size memory pressure from them.** (`max_browsers` is not the
fix: refusals logged `resident=4/6`, under the cap, and the cap fired 0 times in
186,178 requests.)

**Six per-company browsers on 4 GiB can stall a replica without killing it (2026-11-04, joint run
(i), `-se`).** Replica `2jqt7` reached `anon` 3,886 MB with the file cache squeezed to 68 MB, the
pool's 10 s tick went silent for 67 s (08:53:57–08:55:04), and the readiness probe timed out for
55 s (08:54:05–08:55:00), so ACA took it out of rotation. No restart, no OOM, no lost work. Run (ii)
on v0.9.5 / Chrome 157 peaked at `anon` 2,824 MB (p50 ~2,200–2,400 per replica, against
~2,600–3,000 in run (i)): suggestive of lower browser memory, but the cohorts differ, so not a
measurement. Levers if it grows: fewer browser identities from MAS (64–70 launches for 75
companies), or 4 vCPU / 8 GiB now that `aitosoft-aca-se` is a workload-profiles environment (§3.6).

**Kills come with no warning in any sampled series.** At the labelled kill on
2026-08-15 04:30, `anon` was 2,835–3,445 MB and the guard read 80.5–93.5 % in the
preceding 90 s — the middle of the all-night band. It self-recovered in seconds and
cost no pages. The kill lands on a transient allocation between 10-second samples.
Consequence for any future memory change: reading `anon` instead of the
cache-inclusive figure would let the pool grow further in a system that dies
without warning, so it must not ship alone; bounding the allocation
(`max_browsers` 6 → 4) is the stronger option. Both are closed as not worth
shipping at 29 captures (`tasks/done/post-sweep-closure-2026-08-17.md`).

**There is no leak — two instruments agree.** Splitting the 53.4-hour window in
half, our `anon` p50 moved 2,932 → 2,958 MB (+26 MB, +0.6 %); MAS's independent
gauge moved +0.13 points. Their 4,455 refusal readings reproduce our 4,485 refusal
log lines to one decimal on every percentile (p25 87.0 / p50 89.2 / p75 91.6 /
p95 95.4 / max 99.4). The ~4-point overshoot they saw above 85 is not a cached
gauge (the reading is fresh per call); it is the distribution conditional on being
above a threshold set below its own median. Their gauge, sampled on request
arrival, is the less biased of the two — ours picks its sampling interval from the
reading it just took.

**Blast radius grew as the fleet shrank:** at 12 replicas one OOM removed 8 % of
the fleet; at 2 it removes 50 %.

**Operational rule:** you cannot escalate on a memory number. Detect a kill after
the fact (§6.2, §6.3), check whether it cost pages, and restart only if pages are
being lost now.

### 6.5 Cold start, and why "KEDA scaled" is not "capacity arrived"

Measured 2026-07-16/17: ~8–12 s from scheduling to render-capable on a node with
the image cached (container start → "Application startup complete" ≈ 4.3 s; the
browser launches inside the lifespan, so serving implies browser-ready). On an
uncached node add ~40 s for the 1.79 GB image pull.

**Scale-out ramp ≠ serving ramp.** On 2026-07-17 KEDA went 0 → 30 in 72 s, but
only 6 replicas served anything for the next 68 s; the rest waited on node
provisioning and image pulls, the last until +190 s. Every 504 in that incident
started inside the 6-replica window. A replica
count from `replica list` or `SuccessfulRescale` is capacity ordered; for capacity
available, take each replica's first `RenderGate ADMIT`.

Scale-in in the same run: "All metrics below target" ~7 minutes after the last
request, then 30 → 1 within a minute, then zero. **This is the home for scale-to-zero time:**
measured 2026-11-04 on small fleets, 6–16 min after the last request (each step down waits out the
300 s scale-down window, and the last replica the 300 s cooldown); a revision change from
`batch-scale.sh release` or a deploy adds its own replicas for ~5 min (§4.5).

**`ReplicaUnhealthy` is cold-start noise.** The sweep logged 3,030, dominated by
`Readiness probe failed` / `Startup probe failed … connection refused` during
container start and stop — exactly when probes should fail. Ignore it unless it
persists on a replica that is neither starting nor stopping. Fleet churn is normal
too: the first 39.4 h logged 588 container starts, 388 `SuccessfulRescale` and 277
`StoppingContainer` at an average of 8.34 replicas, which is why §6.3's restart
detection needs the rescale cross-check.

**Trap: `az containerapp logs show` on a scaled-to-zero app causes a cold start**
(verified 2026-08-16: `KEDAScaleTargetActivated` 0 → 1 with zero ingress requests).
It bills, and it perturbs what you are measuring. Use Log Analytics unless you need
a live tail on an already-warm app.

### 6.6 The timeout stack, outermost first

| Bound | Value | Owner |
|---|---|---|
| MAS client hard abort | 210 s | MAS |
| Azure ingress timeout | 240 s | ACA platform; not configurable on West Europe's Consumption-only tier. `-se`'s workload-profiles environment may allow it (§3.6; untried) |
| Our wall-clock fence (starts after render admission) | 180 s | `config.yml limits.wall_clock_s` |
| RenderGate queue wait | 15 s | `config.yml admission_max_wait_s` |
| Grace on a revision change or scale-down | 30 s (unset ⇒ ACA default) | ACA, §2.4 |

- **Worst case ≈ 200 s** (15 s queue + browser acquisition + 180 s fence) against
  MAS's 210 s abort — a 10-second margin, not a mechanism. Do not raise the fence
  without telling MAS.
- The stretch between admission and the fence is unfenced, and the budget from
  there to Azure's 240 s is ~40 s, inside which a cold browser launch can take 30 s.
  A hang there escapes every timer we own and lands on the ingress.

---

## 7. Probing the network from inside the container

**You rarely need `az containerapp exec`.** `render_mode: "static"` is an
in-container httpx GET that returns the origin's status, size and error class:

```bash
curl -s -X POST "$CRAWL4AI_API_URL/crawl" -H "Authorization: Bearer $CRAWL4AI_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"urls":["https://api.ipify.org"],"render_mode":"static"}' \
  | jq -r '.results[0].markdown.raw_markdown'
```

Swap the URL to ask "can the crawler reach this, and what does it get?". Egress comes from
Azure's shared SNAT pool; neither environment has VNet integration, so no address is contractual
and we inherit co-tenants' reputation. West Europe's app lists 1 `outboundIpAddresses` entry;
`crawl4ai-service-se` lists **161** (2026-11-04). In use, 7 of 7 probes from one warm `-se` replica
(2026-11-04 07:51–07:56 UTC) left from the same single address, which is in that list (both
regions' addresses are in `PRIVATE.md`). Whether another replica, or the same one later, leaves from
a different one is unmeasured. **The 2026-11-04 cutover changed our egress address, and blocks are
IP-based**, so block rates from before and after the cutover are different instruments.

**First measured case (2026-11-04 evening): some hosts silently drop `-se`'s egress and accept West
Europe's.** In MAS's window 4, 10 URLs on 7 hosts failed `ERR_TUNNEL_CONNECTION_FAILED` after 30.3–30.9 s:
two attempts at the egress proxy's 15 s connect timeout, with no SYN-ACK. They were spread over
both replicas. Two of the hosts answer MAS in ~2 s.
- A bare TCP connect from an `az acr run` task (ACR is in West Europe) reached jekura.fi,
  terapiapalvelut.fi and www.selosella.fi in 30–40 ms.
- One static-mode request to `https://jekura.fi/` through `-se` timed out after 15 s. The same
  request through the West Europe app returned 200 with 3,417 characters.
- **Tell the two kinds of tunnel failure apart by duration:**
  - a refusal in ~1 s means port 443 is closed (an http-only site);
  - a ~30 s timeout means the host is dead or drops our address.
- MAS's archive: companies with any tunnel failure, 1.4 % on West Europe egress (since July)
  against 2.4 % on Sweden Central (n = 11, a lead).
- The West Europe app is held until this is sized (MAS's task-524). The fix options are in
  `tasks/optimization-experiments.md` lever 12.

When you do need a shell: `exec` needs a pty (wrap in `script -qec "…" /dev/null`),
and the command travels in the websocket URL, so anything over ~300 characters
fails with `Could not find container` or a 404 handshake. Keep exec commands tiny.
It is the only instrument for two things:

```bash
# Whether the cgroup has swap — an open prerequisite of the memory work, never run.
script -qec "az containerapp exec -n $APP -g aitosoft-prod --command 'cat /sys/fs/cgroup/memory.swap.max'" /dev/null
# The resolver ACA injects — what it costs and how we bound it: FINDINGS.md §"Egress, DNS and dead hosts"
script -qec "az containerapp exec -n $APP -g aitosoft-prod --command 'cat /etc/resolv.conf'" /dev/null
```

---

## 8. Troubleshooting

| Symptom | First move |
|---|---|
| 401 | Token mismatch. Confirm the env var exists without printing it (§0, `envNames`); check the header is `Authorization: Bearer <token>` |
| 429 | Read `capacity_gate` (§3.8). Only `render_slots` means full. An absent field means an older image |
| 500 | Ours by contract. Count `RESULT FAILURE` / `TERMINAL FAILURE` by `failure_class=` (§5.3) |
| 504 | The 180 s fence: one `WALL-CLOCK FENCE 504` line each, with URL. Zero in the final sweep; a few during a cold ramp are tolerable, a cluster after the fleet has settled is not |
| Slow first request | Cold start (§6.5) |
| Replica non-Running > 10 min | Restart it — but "all Running" is not evidence nothing crashed (§6.3) |
| App runs but is unreachable | Compare the endpoint with `az containerapp show … --query properties.configuration.ingress.fqdn`; an environment migration changes it (§3.6) |
| `BadArgumentError` from Kusto | §5.3 — a column name or reserved word |
| Deploy fails on drift | Nothing was built or shipped (§2.2). Reconcile and re-run |
| Deploy refuses on replica count | §2.3. Wait for the fleet to drain (~7–9 min after the last request) |

---

## 9. Not in this file, deliberately

- Any current configuration value, image or revision — §0.
- Secrets, workspace GUIDs, IP addresses, subscription IDs — `PRIVATE.md`.
- How the crawler works — `CLAUDE.md`, `FINDINGS.md`, `AITOSOFT_CHANGES.md`.
- The overnight tick loop — `OVERNIGHT_PLAYBOOK.md`, which points back here.
- The pre-commit secret check — `CLAUDE.md` §Security, with why it has that exact
  form.

---

## 10. What I am least sure of

- **`a ≈ 5.2` and the loop-gain table are a fit over 1,370 scaling decisions in one
  regime, not an observation.** The metric names are observed. What raises
  confidence is that the structural argument (6 upstream connections per replica
  under `--keep-alive 300`) lands within ~15 %. A way to read the scaler's input
  directly would supersede §3.2.
- **Nothing has been run at triggers 7–11.**
- **The upstream-keep-alive mechanism and the client-connection mechanism are not
  fully separated.** The downstream model is refuted at the new operating point,
  but the discriminating arm (`--no-keepalive` at a matched rate, or varying
  `gunicorn --keep-alive`) has never been run. It decides a few dollars a day.
- **The surge arm in §3.7 moved two variables** — an elasticity observation, not a
  trigger A/B.
- **The full-regime p50/p99 deltas (+3.2 % / +67 %) and replica-hours in §3.7 come
  from the 2026-08-17 review; the logs behind them expired.** The `Replicas`
  metric is still retained (to ~2026-11-15 for 08-14) and could re-derive the fleet
  rows; nothing can re-derive the latency rows except MAS's `49-data/`.
- **The price of `minReplicas: 1`** is bracketed between the idle and active rates;
  whether a pinned crawl4ai replica (a pre-warmed browser and a janitor loop)
  qualifies as idle between sweeps has never been observed.
- **The workload-profiles migration is priced from Microsoft's docs, not from an
  attempt**, and the support-ticket route is cheaper and untried.
- **The ephemeral-storage cause of exit 137 is reasoned, not observed** — nothing
  measures it.
- **Cost figures come from portal downloads a human made**; the 2026-08-15/16
  export used for the trigger-12 check is not in `tmp/azure-costs/`.
- **Most of the evidence behind §3 and §6 has expired from Log Analytics.** What is
  written here is what survived into task files. Re-derive anything load-bearing
  while a sweep is running.

---

## Related

| Doc | When |
|---|---|
| `azure-deployment/deploy-image.sh` | The deploy itself, heavily commented — the executable half of §2 |
| `azure-deployment/batch-scale.sh` | The fixed fleet for MAS's windows (`fix`/`release`), the emergency floor (`up`/`down`), and the CLI no-op it works around |
| `azure-deployment/setup-memory-alert.sh` | Recreates the alert and a receiver |
| `OVERNIGHT_PLAYBOOK.md` | The tick loop when Tero says "monitor overnight" |
| `tasks/done/autoscaler-ratchets-to-the-cap.md` | The scale-rule investigation and controlled runs (§3.2) |
| `tasks/done/trigger-12-readout-2026-08-14.md` | The trigger A/B readout (§3.7) |
| `tasks/done/crawl-cost-is-idle-replicas-not-slow-renders.md` | The cost investigation (§4) |
| `tasks/done/post-sweep-closure-2026-08-17.md` | Why the memory and cost items are closed |
| `tmp/mas-repo-messages/49-data/`, `50-…`, `52-…`, `54-…` (gitignored) | MAS's sweep dump; our OOM corrections; the per-company cost formula; the invoice check |
| `PRIVATE.md` (gitignored) | Workspace ID, egress address |

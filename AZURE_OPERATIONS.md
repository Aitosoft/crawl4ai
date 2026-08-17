# Azure Operations — `crawl4ai-service`

**The single Azure reference for this repo.** Renamed from `DEPLOYMENT_INFO.md`
on 2026-08-17 and rewritten, because a doc audit found ~20 wrong or stale Azure
claims spread across five files and **almost every one was a duplication, not an
omission** — a value `az` answers in one call, transcribed into prose, which then
drifted. Whichever copy a session read first decided its action.

> **The organising rule: if `az` can answer it in one call, this file writes the
> call, not the number.**
>
> Configuration is **queried**. Behaviour and measurements are **recorded** —
> those are the things `az` cannot answer, and they are the only reason this file
> is longer than a page. If you catch yourself adding a replica count, a trigger
> value, an image tag or a revision name to this file, you are re-creating the
> defect it was written to remove.
>
> Corollary, and it is the expensive half: **a number that is here is here
> because no command returns it.** Treat every one as dated evidence, not as
> config.

**Why we own this at all** (owner's framing, 2026-08-17): upstream will develop
the scraper and we benefit from that. What upstream will not do for us is the
Azure deployment. That part we have to be absolute experts in.

---

## 0. Live state — query it, never read it here

```bash
az containerapp show -n crawl4ai-service -g aitosoft-prod --query "{image:properties.template.containers[0].image, rev:properties.latestRevisionName, min:properties.template.scale.minReplicas, max:properties.template.scale.maxReplicas, trigger:properties.template.scale.rules[0].http.metadata.concurrentRequests, cpu:properties.template.containers[0].resources.cpu, mem:properties.template.containers[0].resources.memory}" -o json
az containerapp env list-usages -n aitosoft-aca -g aitosoft-prod -o table
az containerapp revision list -n crawl4ai-service -g aitosoft-prod -o table
az acr repository show-tags --name aitosoftacr --repository crawl4ai-service --orderby time_desc -o tsv
```

Those four answer: what is running, how much environment quota is left, what
revisions exist, and what you could roll back to. **They beat every document in
this repo, including this one.** `CLAUDE.md` and `AITOSOFT_CHANGES.md` have each
pointed at the other as authoritative for current state while both were a
revision behind — two documents, both wrong, pointing at each other.

Two more that answer the questions the first four do not:

```bash
# Every app in the environment — the quota is shared, so this is a capacity fact
az containerapp list -g aitosoft-prod --query "[].{name:name, cpu:properties.template.containers[0].resources.cpu, mem:properties.template.containers[0].resources.memory, min:properties.template.scale.minReplicas, max:properties.template.scale.maxReplicas}" -o table

# Probes, env var NAMES (never values), grace period, revision mode
az containerapp show -n crawl4ai-service -g aitosoft-prod --query "{probes:properties.template.containers[0].probes, envNames:properties.template.containers[0].env[].name, grace:properties.template.terminationGracePeriodSeconds, mode:properties.configuration.activeRevisionsMode}" -o json
```

---

## 1. The resources, and the two names people confuse

All in resource group **`aitosoft-prod`**, West Europe (co-located with MAS).

| Resource | Type | Purpose |
|---|---|---|
| `aitosoft-prod` | Resource group | Everything below |
| `aitosoftacr` | Container Registry | Image tags — the real rollback surface |
| **`aitosoft-aca`** | Container Apps **environment** | Runtime environment, shared with MAS |
| `crawl4ai-service` | Container App | This service |
| `aitosoft-edge` | Container App | **MAS's**, same environment, shares the core quota |
| `workspace-aitosoftprodnCsc` | Log Analytics | Console/system/HTTP logs |
| `crawl4ai-memory-high` | Metric alert | See §5.5 — it fires and nobody hears it |
| `crawl4ai-oncall` | Action group | Zero receivers of any kind |

> ⛔ **The environment is `aitosoft-aca`. `wonderfulsea-6a581e75` is the
> environment's DNS label, not its name.** It appears in the endpoint FQDN
> because the app FQDN is `<app>.<environment defaultDomain>`, and several
> `az containerapp env …` invocations written against it fail confusingly. Get
> both from one call:
>
> ```bash
> az containerapp env show -n aitosoft-aca -g aitosoft-prod \
>   --query "{defaultDomain:properties.defaultDomain, workloadProfiles:properties.workloadProfiles}" -o json
> ```
>
> That `defaultDomain` is also **why an environment migration is a MAS-visible
> contract change** — see §3.6.

**Endpoint** (deliberately tracked, not in `PRIVATE.md` — it is fail-closed
behind the token and is live tooling config; only `/health` is public):

```
https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io
```

**Auth:** `Authorization: Bearer $CRAWL4AI_API_TOKEN`, upstream's
`AuthGateMiddleware` since v0.9.2 — fail-closed, constant-time. The token lives
in `.env` and in the app's env vars. **Never in a document, never in a commit.**

**Infrastructure identifiers** — Log Analytics workspace GUID, egress address,
the dev container's home-ISP connection — are in gitignored **`PRIVATE.md`**.
The line, so it does not get re-decided: *identifiers that let someone act* go
there; *facts and reasoning* stay here.

```bash
export LAW_ID=$(az monitor log-analytics workspace list \
  --query "[?name=='workspace-aitosoftprodnCsc'].customerId | [0]" -o tsv)
```

That derivation works without `PRIVATE.md` at all, which is why it is the form
every query below assumes.

**MAS-side configuration** (they hold the values):

```bash
CRAWL4AI_API_URL=https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io
CRAWL4AI_API_TOKEN=<from this repo's .env>
```

---

## 2. Deploying

### 2.1 The only supported path

```bash
./azure-deployment/deploy-image.sh <tag>
```

It builds in ACR (no local Docker), **never touches env vars** — that is how
MAS's token gets broken — and never touches replica limits, probes or scale
rules. Read the script; it is commented at the level this file would otherwise
have to duplicate.

### 2.2 ⛔ The drift checks run **BEFORE** the build

The order in the script is: **drift checks → `az acr build` → `az containerapp
update --image`.** Confirm it in one call rather than trusting this sentence, because
line numbers drift:

```bash
grep -nE 'DRIFT CHECKS|ACA_SCALE_TRIGGER=|ACA_MAX_REPLICAS=|az acr build|--image' azure-deployment/deploy-image.sh
```

**Five places in this repo said the checks run after the image swap.** That is
the opposite of the truth, and the difference decides what you do next:

- **Today: a drift failure means nothing was built and nothing shipped.** Fix the
  constant or fix production, then re-run. Do not go looking for a half-deployed
  service.
- **Before 2026-08-14 it meant the image was already live** and the deploy had
  reported failure anyway — a red deploy *and* a changed production, the worst of
  both. It fired for real when MAS lowered `maxReplicas` on their side while the
  script still declared the old value.

The checks compare live ACA against two constants declared **in the script
itself** (`ACA_SCALE_TRIGGER`, `ACA_MAX_REPLICAS`) — not against `render_capacity`.
Pinning them to `render_capacity` was a category error, retired 2026-08-08 (§3.1).
`minReplicas` is deliberately **not** checked, because `batch-scale.sh`
legitimately pins it above zero for an emergency window.

**If you change a scale setting in Azure, change the constant in the same
session** or the next deploy hard-fails. That is the check working.

```bash
grep -nE '^(ACA_SCALE_TRIGGER|ACA_MAX_REPLICAS|DEPLOY_REPLICA_CEILING)=' azure-deployment/deploy-image.sh
```

### 2.3 The pre-deploy fleet gate, and the quota that causes it

`deploy-image.sh:46-63` refuses to deploy above `DEPLOY_REPLICA_CEILING` live
replicas. **This is not caution, it is a measured failure.** 2026-08-08, fleet at
38 replicas (76 cores), scale rule changed:

```
FailedCreate ×25: pods "crawl4ai-service--0000039-…" is forbidden:
  exceeded quota: consumption, requested: cpu=2k, used: 98250, limited: 100k
```

**Any** `az containerapp update` touching `properties.template` — image, scale
block, env vars, probes — mints a new revision, and **the new revision needs its
own replicas while the old one drains**. Both count against the environment
quota. The new revision sat in `ActivationFailed` / `Unhealthy` with **0
replicas while holding 100 % of the traffic weight** for ~8 minutes. Production
stayed up only because ACA kept routing to the old revision's survivors — the
platform being forgiving, not a margin to rely on. Had the old revision finished
draining first, the app would have been down with replicas on neither side.

```bash
az containerapp replica list -n crawl4ai-service -g aitosoft-prod --query 'length(@)'
az containerapp env list-usages -n aitosoft-aca -g aitosoft-prod -o table
```

This is a live risk **mid-sweep**, i.e. exactly when someone wants to ship a fix.
It is also an independent argument for keeping the fleet small.

### 2.4 A revision change kills in-flight renders, and the grace period is wrong for us

`terminationGracePeriodSeconds` is **unset**, so ACA applies its default of
**30 s** — against our **180 s** wall-clock fence (`config.yml limits.wall_clock_s`).
A revision transition therefore destroys up to **150 s of in-flight render work**
per draining replica.

```bash
az containerapp show -n crawl4ai-service -g aitosoft-prod \
  --query properties.template.terminationGracePeriodSeconds -o tsv    # null == platform default
```

**This is observable, not theoretical.** One 39-hour sweep logged **739 ×
`killing 'gunicorn' (9) with SIGKILL`** on the scale-down path: supervisord's
`stopwaitsecs` elapses and gunicorn is killed rather than exiting cleanly, so
**any render still in flight when a replica scales down is killed.** Measured
impact in that window was ~6 requests of 36,783 (4 × `DC`, 2 × `SI` at the
ingress) — but that was at a true concurrency of **1.45**, and **the impact
scales with concurrency**, so it is not a constant.

The CLI exposes the knob (`az containerapp update --termination-grace-period` /
`--tgp`, verified present in the installed `containerapp` extension), so this is
a one-flag change **if we decide we want it**. It has not been made, deliberately:
raising it to 180 s makes every revision transition — including every deploy —
take three minutes per replica to drain, and the measured harm today is ~6
requests in 36,783. **Recorded so the next person reasoning about a mid-sweep
deploy knows the number is 30 and not 180, and knows the loss is already in the
logs.**

### 2.5 Rollback — read the cost before you type it

**Most incidents do not want an image rollback.** Between 2026-08-06 and
2026-08-09 the image did not change at all; the only production change was the
**scale trigger**. If the symptom is capacity, cost or replica count, roll back
*that* (§3.5), not the image.

**Roll back by re-deploying the TAG, never by activating an old revision.** The
app is in `activeRevisionsMode: Single`; old revisions are deactivated and
garbage-collected, so a revision name is not a rollback target. The **image tags**
survive, in ACR:

```bash
az acr repository show-tags --name aitosoftacr --repository crawl4ai-service --orderby time_desc -o tsv
./azure-deployment/deploy-image.sh <older-tag>
```

Two things the tag list cannot tell you, so they are recorded here:

- **`0.9.2-egress-dns` is burned** — it shipped a `NameError` and lasted 8
  minutes. Never roll back to it.
- **Rolling back past `0.9.2-consent-guard` (2026-08-06) reverts the consent
  guard**, and that is not theoretical: segment 4 logged 23 ×
  `CONSENT DECLINED node=html structural=True` in ~300 renders (**7.7 %**). On
  the image below it, every one of those is a 15-byte capture at **HTTP 500**,
  which MAS retries 3×. It also reverts collapse recovery,
  `unrenderable_content`, the browser-pool cap and the egress DNS fix. **Do not
  reach for it to fix a capacity symptom.**

Rolling back past the `0.9.2-failure-class` contract (`status_code` = final
redirect hop; `failure_class` on every result; origin faults at HTTP 200 +
`success:false`; 5xx reserved for us) **reverts a cross-repo contract** — MAS's
retry branch reads the wire status, not the body. Coordinate first.

**Image only — NEVER set env vars during a rollback.**

### 2.6 Manual equivalents, if you need the steps piecemeal

```bash
az acr build --registry aitosoftacr --image crawl4ai-service:<tag> --file Dockerfile .
az containerapp update -n crawl4ai-service -g aitosoft-prod \
  --image aitosoftacr.azurecr.io/crawl4ai-service:<tag>
curl -s -o /dev/null -w '%{http_code}\n' "$CRAWL4AI_API_URL/health"
```

`deploy-aitosoft-prod.sh` — which regenerated the API token on every run and
would have broken MAS — was deleted 2026-07-17 with the rest of the
North-Europe-era scripts. The legacy North Europe deployment `crawl4ai-v2-rg`
no longer exists (`az group exists` → false, 2026-07-17).

### 2.7 Rotating the token (a deliberate, standalone change — never during a deploy)

```bash
NEW_TOKEN="crawl4ai-$(openssl rand -hex 24)"
az containerapp update -n crawl4ai-service -g aitosoft-prod \
  --set-env-vars CRAWL4AI_API_TOKEN="$NEW_TOKEN"
# then update this repo's .env AND tell MAS, in that order
```

This mints a revision (§2.3, §2.4). Do it when the fleet is small and no sweep
is running.

### 2.8 Provisioning reference

The app already exists; this is the reproduce-from-scratch record.

**Env vars** — read the *names* live (`az containerapp show … env[].name`), never
the values. Only two matter: `CRAWL4AI_API_TOKEN` (Bearer token, MAS holds the
value) and `GUNICORN_BIND=0.0.0.0:11235` (upstream's `entrypoint.sh` otherwise
binds `[::]`, which is an IPv6-bind surprise waiting to happen). `ENVIRONMENT`,
`LOG_LEVEL`, `MAX_CONCURRENT_REQUESTS` are inert leftovers from the old deploy
script.

**Probes** — read them live; the shape is what matters and it is deliberate:
HTTP startup and readiness on `/health` (the lifespan pre-warms the browser
before serving, so **passing readiness == browser-pool-ready**), and a TCP
liveness probe with generous thresholds so it **never kills a busy replica**.
Probes are set via YAML (`az containerapp update --yaml`), not flags.

**Other v0.9.2 notes:** Redis inside the container is password-protected
automatically (ephemeral password from `entrypoint.sh`). Auth is upstream's
`AuthGateMiddleware`, so `/docs`, `/metrics` and `/playground` now require the
token too.

---

## 3. Scaling — where Azure's own documentation is the problem

### 3.1 The scale rule is not what its name says, and pinning it to `render_capacity` was a category error

|  | what it is | units | protects anything? |
|---|---|---|---|
| `render_capacity` (`config.yml`) | hard cap on simultaneous renders per replica, enforced in-process by RenderGate | **concurrent renders** | **yes — this is the safety mechanism** |
| `concurrentRequests` (ACA scale rule) | the autoscaler's trigger: *when Azure adds a replica* | Microsoft defines it as **"requests in the past 15 seconds divided by 15"** — a **rate** | no |

Two numbers in different units can never meaningfully be equal. Requiring them
equal pinned the trigger at 2, which is the **runaway** setting (§3.4), and
made the fleet maximally twitchy. **Raising the trigger cannot oversubscribe a
replica** — the gate, not the scaler, bounds renders.

The in-process side of this lives in the repo, not in Azure, so read it there —
`grep -nE 'render_capacity|admission_queue|wall_clock_s|max_browsers|memory_threshold_percent' deploy/docker/config.yml`.

Per-replica render capacity is 2 because the replica is 2 vCPU (benchmarked
2026-07-17; >2 concurrent renders degrade all requests). Independently
re-measured from production telemetry: `fleet_cores = -0.13 + 2.45 × concurrency`
(r² 0.738) ⇒ **~2.4 cores demanded per in-flight render**, so a 2 vCPU replica at
2 concurrent renders is **already oversubscribed ~2.4×**. There is no headroom to
raise it into.

### 3.2 What the scaler actually reads — the part no public source documents

The documented formula is
`desiredReplicas = ceil(currentMetricValue / targetMetricValue)`. At the sweep's
measured arrival rate it predicts **1 replica**; the fleet held **11–12**. Every
request-based model was simulated second-by-second over three full days,
including the 300 s scale-down stabilization — **all refuted by 5–11×**:

| model | mean fleet | observed |
|---|---|---|
| documented (reqs-in-15 s ÷ 15) | 1.0 | 11–12 |
| reqs in one second | 1.0–2 | 11–12 |
| reqs in 15 s, undivided | 2.1–2.25 | 11–12 |
| instantaneous in-flight | 1.8 | 11–12 |

**The scaled object is backed by eight external metrics**, recovered
2026-08-11 from a `FailedComputeMetricsReplicas` error that enumerated them:

```
s0-upstream_rq_total    s0-upstream_rq_active    s0-upstream_cx_total    s0-upstream_cx_active
s1-upstream_rq_total    s1-upstream_rq_active    s1-upstream_cx_total    s1-upstream_cx_active
```

Two scalers (`activator`, `http-scaler`) × four Envoy metrics — **and two of the
four are connection counts** (`cx`), which appear in no Microsoft documentation.
An ACA maintainer states publicly (`microsoft/azure-container-apps#536`) that
*"scaling http apps takes into account **active connections as well as
requests**"*; that sentence is the only public acknowledgement and it is in an
issue thread.

**The consequence is the important part.** `upstream_*` is **Envoy → replica**,
so the metric is **replica-proportional by construction** and the scaler is
**self-referential**: more replicas ⇒ more upstream connections ⇒ a higher
metric ⇒ more replicas. Fitting `metric = a·R + b·L` over **1,370 individual
scaling decisions within one regime** gives **a ≈ 5.2**, i.e. loop gain
`a / trigger`:

| trigger | loop gain | behaviour |
|---|---|---|
| 2 | ~2.6 | **runaway** — observed plateau of 38 replicas, then the cap |
| 6 | **≈ 0.87** | near-instability: the fleet keeps whatever size a burst gave it and never drains |
| **12** | **≈ 0.45** | actively drains |

That is why a **2× trigger change produced a 4.7× fleet change** — a
super-proportional response no request-rate model can produce, and why trigger 2
once plateaued at **38 replicas** (a fixed point, held flat for four samples, not
a runaway to infinity).

**Two independent routes give the same slope, which is the strongest thing here.**
The structural argument was written months before the metric names were
recovered: a replica accepts at most `render_capacity 2 + admission_queue 4` = **6**
concurrent HTTP requests, and our own `gunicorn --keep-alive 300`
(`supervisord.conf`; gunicorn's default is **2**) holds those upstream
connections open — so the metric should be **≈ 6 × replicas**. The fit over
scaling decisions says **≈ 5.2 × replicas**. **They agree within ~15 %, from
completely different evidence.** The structural version also names the fix as
**ours** — one line, `--keep-alive`, no MAS coordination.

**What this means for choosing a trigger.** The repo's own reading of the same
model: at 2 the loop is `3 × replicas` (runaway); at **6 it is `1 × replicas` —
exactly neutral**, so the fleet keeps whatever size a burst gave it and never
drains, which is why slot utilisation was 7.0 % on *every day* of a five-day
sweep to one decimal; at **≥ 7 it is contractive** and drains to the demand
floor. **12 is not a tuned value, it is just "above 6"** — and **6 was the worst
available setting**, sitting on the neutral point. ⚠️ "Anything ≥ 7 lands in the
same place" is an **inference**: we have run 2, 6 and 12. **Nothing has been run
at 7–11.**

**Honesty about status:** no ACA metric exposes the scaler's *value*, so `a ≈ 5.2`
is a fit over decisions, not an observation. What *is* observed is the metric
**name list**, and **our recovery of it appears to be net-new** — it is in no
Microsoft doc, no KEDA doc and no blog we could find, and the repo's own prior
conclusion was the flat "no ACA metric exposes the scaler's input, so it is
unfalsifiable from here." Knowing the names does not make the value readable, but
it does turn "connections might matter" into "two of the eight inputs are
connection counts." If you touch the scale rule, this section is the model to
reason with, **and the fit is the part to distrust first.**

**A refuted sibling, recorded so it is not re-fitted.** A model built on
*downstream* (client → Envoy) connections — "≈65 open, held ~300 s, independent
of fleet size" — predicted 6 replicas at trigger 12 and observed 2. **No single
fleet-independent connection count produces 12 replicas at trigger 6 and 2 at
trigger 12.** The surviving model is the *upstream* one, which is
replica-proportional by construction.

### 3.3 Documented ACA behaviour that amplifies the loop

- **Scale-up stabilization: 0 s.** Instant.
- **Step: geometric** — 1, 4, 8, 16, 32 … clamped at `max(4, 2 × current)`.
- **Scale-down stabilization: 300 s.** Damped.

Instant up, damped down, on a self-referential metric. That combination is the
whole behaviour. It is directly visible in our own logs: the 2026-07-17
scale-out went **0 → 4 → 8 → 16 → 19 → 30 in 72 seconds** — the documented
geometric sequence, clamped at `maxReplicas`, with no damping whatsoever.

### 3.4 The knobs that do not exist — **stop re-investigating this**

Verified 2026-08-08 against the ARM spec and Microsoft's docs, and re-confirmed
since:

- **`pollingInterval`** — a real, writable ARM field (API ≥ `2024-08-02-preview`)
  and a **no-op**: Microsoft documents it as *"doesn't apply to HTTP and TCP
  scale rules"*.
- **`cooldownPeriod`** — real, writable, and governs **only** the final replica →
  0 transition.
- **The 300 s scale-down stabilization window** — the thing that actually damps
  scale-in — has **no configuration surface anywhere in ACA**.
  `microsoft/azure-container-apps#1418` asks for one; open since 2025-02, **one
  comment, zero Microsoft engagement in 18 months**. KEDA itself exposes
  `behavior.scaleDown.stabilizationWindowSeconds`; Azure simply does not surface
  it.

**The only levers are `concurrentRequests`, `minReplicas` and `maxReplicas`.**

### 3.5 Changing a scale setting

```bash
# The trigger — the cost lever. Takes effect on the next KEDA poll.
az containerapp update -n crawl4ai-service -g aitosoft-prod \
  --scale-rule-name http-renders --scale-rule-type http \
  --scale-rule-http-concurrency <N>

# Verify (deploy-image.sh does this automatically against ACA_SCALE_TRIGGER)
az containerapp show -n crawl4ai-service -g aitosoft-prod \
  --query "properties.template.scale.rules[?name=='http-renders'].http.metadata.concurrentRequests | [0]" -o tsv
```

Then **edit `ACA_SCALE_TRIGGER` in `azure-deployment/deploy-image.sh` to match**,
or the next deploy hard-fails its drift check (§2.2). It mints a revision, so
every replica restarts and every in-flight render dies (§2.4).

> ⚠️ **`az containerapp update --yaml` silently drops the scale-rule metadata
> value.** Measured 2026-07-17: the rule was created with the right name and type
> and *no* `concurrentRequests`, which means ACA falls back to its default of 10.
> Re-apply with the explicit `--scale-rule-http-concurrency` flag, and
> **verify with `az containerapp show`, never with the update response** — the
> update returned success.

> ⛔ **A "revert" command in this file said `2` until 2026-08-15, and 2 is the
> runaway setting.** Anyone reaching for it mid-incident would have made the
> incident dramatically worse and paid for the privilege. Read the live value
> first (§0) and the loop-gain table (§3.2) before choosing a number. **There is
> no circumstance in which 2 is the right answer.** If the rule is *missing*
> entirely, ACA falls back to a default of 10 — that is what caused the
> 2026-07-16 504 incident.

**`minReplicas` / `maxReplicas`** — prefer the script, because a raw
`--min-replicas 0` on its own is a **silent no-op**:

```bash
./azure-deployment/batch-scale.sh status    # read
./azure-deployment/batch-scale.sh up 1      # EMERGENCY ONLY: pin warm capacity
./azure-deployment/batch-scale.sh down      # back to scale-to-zero
```

The CLI-source lines proving the no-op are in `batch-scale.sh`'s own comment
block (`azext_containerapp/containerapp_decorator.py:791,983,986` — the *outer*
gate is plain truthiness, so `0 or None or None` → falsy → the scale block never
enters the PATCH body). `up N` worked only because N ≥ 1 is truthy; `down`
printed its success line and did nothing. **The valve could be opened and not
closed.** Both branches now verify rather than trusting the exit code.

**Warm-replica pinning before a batch is RETIRED (2026-07-17).** RenderGate plus
the explicit scale rule make scale-out respond to real traffic. `batch-scale.sh`
is an emergency valve only.

### 3.6 Ceilings — what can and cannot be bought

**Environment core quota.** `ManagedEnvironmentConsumptionCores` is **100** and
`aitosoft-edge` (MAS's app, same environment) holds a fixed share:

```bash
az containerapp env list-usages -n aitosoft-aca -g aitosoft-prod -o table
az containerapp list -g aitosoft-prod --query "[].{name:name, cpu:properties.template.containers[0].resources.cpu, min:properties.template.scale.minReplicas, max:properties.template.scale.maxReplicas}" -o table
```

> **`aitosoft-edge` was resized mid-sweep and no document noticed.** Every file
> in this repo said "0.25 cores" for weeks. It is **1.0 vCPU / 2 GiB at
> `min = max = 1`**, i.e. **1 core permanently**, which puts our absolute ceiling
> at **(100 − 1) / 2 = 49 replicas**, not 50. That is exactly the kind of number
> this file must not carry — **run the two commands above**; they are one call
> each and they cannot drift.

**Per-replica size: 2 vCPU / 4 GiB is this environment's hard maximum.** Tested
2026-08-02, and the error text is the evidence — it enumerates the whole
allowed set:

```
$ az containerapp update -n crawl4ai-service -g aitosoft-prod --cpu 2.0 --memory 8.0Gi
ERROR: (ContainerAppInvalidResourceTotal) ... must add up to one of the following
CPU - Memory combinations: [0.25/0.5Gi] [0.5/1.0Gi] [0.75/1.5Gi] [1.0/2.0Gi]
[1.25/2.5Gi] [1.5/3.0Gi] [1.75/3.5Gi] [2.0/4.0Gi]
```

**The list ends at 2.0 / 4.0Gi.** The command is atomic, so nothing changed. The
reason is `workloadProfiles: null` — a legacy Consumption-only managed
environment. Microsoft's own docs contradict each other on the limits; **our
`az` rejection is the tiebreak**, and it is why the April note that
`--memory 8.0Gi` "doubles headroom at zero cost" was never a valid command, and
why `tasks/README.md`'s "4 vCPU / 8 GiB is the likely shape" was a guess about a
different environment type.

**But the escape route was mis-priced, and this is the correction that matters.**
A workload-profiles (v2) environment's **built-in Consumption profile** allows
**4 vCPU / 8 GiB at the identical meter rate**, with **scale-to-zero intact** and
**no management fee** — management fees apply only to **Dedicated** profiles.
The per-replica cost is 2× **because the resources are 2×**, not because the
billing model changed. What it actually costs:

- **Migration is not in-place.** New environment, redeploy, and a **new FQDN**,
  because the app FQDN embeds the environment's `defaultDomain` (§1). That is a
  **MAS-visible contract change** and the real price. (`az containerapp env
  update -w <name> --workload-profile-type …` exists and the flag is present,
  but converting a *live* environment is not the same operation as standing up a
  new one and moving to it — do not read the flag's existence as an in-place
  path.)
- At 4 vCPU/replica the 100-core quota gives **25 replicas, not 49**.
- **And before any of that: Microsoft's FAQ says memory-limit overrides are
  *"evaluated on a per-case basis"*. One support ticket may remove the need
  entirely, and nobody has tried it.** That is the cheap lever; try it first.

**Right-sizing downward is refuted:** the busiest replica exceeds 3.0 GiB in
99 % of minutes, so 1.5 vCPU / 3 GiB does not fit.

### 3.7 The trigger A/B — the only controlled comparison anyone has run

Identical production traffic, one setting changed. This is measurement, not
modelling, and it is the strongest evidence in this file:

| | trigger 6 | trigger 12 |
|---|---|---|
| mean fleet | 11.05 | **1.97** |
| max fleet | 19 | **3** |
| replica-hours | 1,344 | **106** |
| slot utilisation | 8.9 % | **40 %** (true, after excluding queue wait) |
| browser launches per admit | 0.339 | **0.110** |
| queue wait | 0.041 s | **0.919 s** |
| RenderGate rejects per admit | 1× | **27×** |
| cost per request | — | **6.4× cheaper** |

**A smaller fleet is more efficient per request — the over-provisioning was
manufacturing its own load.** Mechanism: MAS sends a per-company browser
identity, so at 12 replicas a company's ~7 pages scattered round-robin and **each
replica paid its own cold Chromium launch**. Pool hit rate went 26.6 % → ~65 %,
total fleet CPU 3.44 → 1.55 cores, p99 −28 % against p50 +3.8 %.

> **You will find slightly different numbers for this in the task files, and they
> are not contradictions.** A matched 32-minute window gives fleet 12 → 2,
> utilisation 8.7 % → 54 %, launches per admit 0.369 → 0.132; the sweep-wide
> figures above are the same comparison integrated over days. Slot utilisation at
> trigger 6 reads **7.0 % or 8.7 % or 8.9 %** depending on the window. **The
> conclusion is invariant across all of them**; quote the window with the number.

Two things this does **not** say, both of which were claimed and are wrong:

- **`maxReplicas` is not a cost lever.** Lowering it 45 → 20 saved **exactly
  zero** — replica-minutes above 20 across the entire sweep: **0**. It is tail
  protection.
- **The fleet is now only weakly elastic, and that is the designed behaviour.**
  One scale-up event in 30 minutes of real traffic. A synthetic arm at **1.44×**
  the production rate (30 req/min, fanout 4, 12 min, `raw://`) held **1 replica
  for all twelve minutes** through **38 × 429 (10.6 %)** and a mean admission
  wait of **5.26 s** against the 15 s limit. **Do not wait for replicas to appear
  as confirmation that a burst was handled.**

  ⚠️ **Read that arm narrowly.** It ran a pooled client with a 300 s keep-alive
  expiry, so ~4 TCP connections carried all 360 requests and the 38 rejections
  rode the same 4. The trigger-6 arm it is compared against ran httpx's 5 s
  default — effectively one connection per request. **Two variables moved; it is
  not a clean trigger A/B.** The third arm that would separate them
  (`--no-keepalive` at the same rate) is designed and has never been run.

  **And the coupling that follows from it is the most important operational
  consequence in this file:** if MAS ever fixes their client's
  `keepAliveTimeout` — which we have contemplated asking for — **our scale-up
  largely disappears and we sit pinned near 1 replica**, which is what this arm
  demonstrates. If that ask is ever made, **the trigger must come down in the
  same change.**

**A replica count is not a load measurement.** Concurrency is
`sum(RequestDuration)/window`, which lives **only** in `ContainerAppHTTPLogs` —
our own `RenderGate ADMIT` logs admission but never release, so console logs
cannot produce it. And `dcount` of replica names at 10-minute resolution reports
*churn* as concurrency (it said 30 where a 1-minute bin said 6). Bin at 1 minute
and cross-check with `az containerapp replica list`.

### 3.8 429s: two mechanisms, opposite fixes, and only one is capacity

`RenderGate REJECT` (concurrency, real) and `refusing new browser`
(`crawler_pool`'s memory guard, benign) both emit **HTTP 429 + `Retry-After`**
with a byte-identical envelope. Across the full sweep the split was **~99 %
memory guard**. Reading the total as a capacity ceiling sends you at
`maxReplicas`, which was never the constraint.

**Split the count before reading anything into it, and never treat a 429 rate as
a threshold.** MAS's terminal accounting for the whole 175-hour sweep: our 429s
cost them **29 captures of 60,874 attempts (0.05 %)** — their retry ladder
absorbed the rest.

**Cold start is where the 429s live, and it is visible in two-minute bins.** From
the start of one sweep at trigger 12:

| bin | requests | 429 | p50 | fleet |
|---|---|---|---|---|
| 17:56 | 50 | **14** | 8,716 ms | 1 |
| 17:58 | 46 | 3 | 5,646 ms | 1 |
| 18:00 | 47 | **0** | 4,552 ms | **2** |
| 18:02 | 52 | **0** | 5,840 ms | 2 |

**All of it landed while the fleet was at 1 replica. The second replica arrived
and the 429s stopped.** No intervention.

**`minReplicas` is the lever for that window, and it is priced.** The ingress is
**round-robin, decided per request, session affinity off** (`stickySessions: null`);
Envoy picks the endpoint *then* the connection pool, so a keep-alive client does
**not** pin to a replica. A big fleet therefore *dilutes* bursts rather than
absorbing them — and dilution needs the replicas to already exist. MAS's own
control: three crossings of 5 concurrent in minute one produced their single 429;
seven crossings after KEDA had scaled produced none. Replica warmth was the only
variable.

**But `minReplicas: 1` costs about half the current bill** (~$7.3/day against
~$14.5/day) to remove an ~11.5 s cold start that only occurs at gaps between
batches, and it also makes the cheaper idle rate permanently unreachable in a
different way (§4.4). **Priced and declined.** Revisit only if cold-start 429s
start costing captures — MAS's terminal accounting says they cost 29 in 60,874.

### 3.9 The load generator — test scaling without touching a third party

**A `raw://` URL is a full-fidelity load generator with zero egress.**
`deploy/docker/utils.py` returns early for `raw:` **before** any DNS or SSRF
check, and `async_crawler_strategy.py` still routes it through the browser
whenever `needs_browser` — which `remove_consent_popups`, the flag MAS sends on
every production request, sets. So it exercises RenderGate, the pool, **a real
Chromium launch on a cold replica**, the consent pass, scraping, markdown and the
collapse guard. **Only the network navigation is skipped.**

Render duration is a **dial**: `delay_before_return_html` is on the untrusted
allowlist, and wall time is linear at **~1.3 s overhead + the delay**.

```bash
python test-aitosoft/sustained_rate_probe.py --label <name> --rate-per-min 30 \
  --fanout 4 --duration-min 12 --keepalive-expiry 300
python test-aitosoft/cold_burst_probe.py --help    # 429s, TTFB, queue pressure
# server-side readback:
cat test-aitosoft/cold_burst_probe.kql
```

Neither is collected by pytest (no `test_` prefix). They read the token from
`CRAWL4AI_API_TOKEN`, never print or store it, refuse a warm app without
`--allow-warm`, and cap their own rate and duration. They were **committed rather
than rebuilt each time for a reason: a rebuilt generator is not a valid B-arm
against a recorded A-arm.**

> ⚠️ **The trap that cost this instrument its first run.** httpx's default
> `keepalive_expiry` is **5.0 s** (verified by executing
> `httpx.Limits().keepalive_expiry`, not by reading docs). At 19 req/min with
> `--fanout 4` the gap between arrivals is **12.63 s**, so every pooled
> connection expired before the next tick and **the "pooled" arm was silently a
> second copy of the un-pooled arm.** A pool that expires between uses is not a
> pool — and that is precisely the defect being attributed to MAS's client.
> **Both arms must set `--keepalive-expiry` explicitly.**

**Reach for this before any live host.** Unlike a third party it is byte-identical
across A/B arms, and it costs no reputation.

---

## 4. Cost

### 4.1 How to actually get a number — the instrument does not exist yet

**There is no configured cost export.**

```bash
az rest --method get --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/providers/Microsoft.CostManagement/exports?api-version=2023-11-01"
# -> {"value": []}
```

The figures below came from **a human downloading a usage export from the portal**
into gitignored `tmp/azure-costs/`. Say that plainly, because a future session
will otherwise spend an hour looking for an automated export that does not exist.
**If cost matters again, configuring one is the first move.**

### 4.2 Cost Management returns nothing, and that is documented behaviour

```bash
az rest --method get --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)?api-version=2022-12-01" --query subscriptionPolicies.quotaId -o tsv
# -> Sponsored_2016-01-01
```

**Microsoft documents quota ID `Sponsored_2016-01-01` by name in the list of
offers Cost Management does not support.** The API genuinely returns `rows: []`,
and an agent verified that is not a permissions artefact by running the identical
query against a different subscription, which returned records.

> ⛔ **"The API returned no records" and "there was no cost" are different
> statements.** Reading the first as the second is what let **~$89/day run
> unnoticed for five days**. The usage *export* has the data all along.

### 4.3 The rate, and the currency correction

Measured against `prices.azure.com` on three meters, 2026-08-17:

```
$0.000034 / vCPU-second  +  $0.000004 / GiB-second
  = $0.3024 / replica-hour at 2 vCPU / 4 GiB
```

> ⛔ **The usage export is denominated in USD and carries no currency column.**
> Every euro figure in this repo derived from it is really dollars. Azure's EUR
> list is **0.8775 × USD**, so:
>
> | as written across the repo | actually |
> |---|---|
> | `€398.89 for one sweep` | **$398.89 ≈ €350** |
> | `~€89/day → ~€14.5/day` | **~$89 → ~$14.5/day ≈ €78 → €12.7** |
> | `~€0.10/replica-hour` (old `DEPLOYMENT_INFO.md:452`) | **$0.3024/replica-hour — the old figure is ~3× low** |
>
> The last one is the dangerous direction: **it made over-provisioning look
> affordable.**

### 4.4 The idle rate is unreachable, and it is smaller than it looks

The ACA "idle" rate is **CPU-only** — memory bills the same idle and active — so
idle is ~**3.5×** cheaper, not the ~8.5× that a naive read of the price page
gives. And it is **structurally unavailable to us**: Microsoft requires
`minReplicas > 0` **and** the revision to be *at* the minimum, and states that
above the minimum **all** running replicas bill active. `minReplicas: 0`
disqualifies us permanently. Measured share of a full sweep billed at idle:
**$1.02 of $374.54**. **Stop treating the idle rate as a lever.**

### 4.5 Our own accounting predicts the invoice — use it to price a change

**8,893,189 billed vCPU-seconds ÷ 2 vCPU = 1,235 replica-hours**, against
**1,262 replica-hours** counted independently from Log Analytics replica counts —
**within 2.1 %**, and it holds **day by day** (−0.5 %, −0.6 %, −0.6 %, −1.7 %),
not just in aggregate. The residual is the right size for `aitosoft-edge`.
Memory billed at exactly **2.0×** the vCPU-seconds, confirming the enforced
1 vCPU : 2 GiB pairing.

**That reconciliation is the most useful cost fact here: a config change can be
priced from our own logs before it is made.**

Scale of the thing: the 18,374-company sweep cost **~$399** (**$0.0217/company**,
**$0.0032/page**) at trigger 6 and **8.9 %** slot utilisation. At trigger 12 the
same work is **6.4× cheaper per request** ($3.28 → $0.51 per 1,000). The
baseline when we are idle is **$0** — scale-to-zero works; the small standing
line item is `aitosoft-edge` at `minReplicas: 1`, not us.

**And the headline is now spent.** At trigger 12 the fleet is a constant 2 across
a 1.6× swing in load, so the bill is `2 × $0.3024 × wall-clock`, full stop. The
remaining idle is **queueing headroom, not over-provisioning** — 29 % of admits
already wait, and a one-replica probe rejected 10.6 %. **The fleet is at its
floor.** Do not re-run the over-provisioning argument against it.

**Cheaper architecture, priced and rejected:** ACA at a cap of 4 (~$29/day)
matches 6 PAYG D4as_v5 VMs (~$30/day) with zero migration and keeps
scale-to-zero, which matters because a sweep is ~17 % of the calendar. Azure
Functions cannot run these containers; ACI has no autoscaling.

---

## 5. Observability — four instruments, and each answers a different question

### 5.1 The `_CL` suffix rule, and the one sentence every trap follows from

**Console and system logs arrive via the environment's `appLogsConfiguration`
into legacy custom tables** — hence `ContainerAppConsoleLogs_CL`,
`ContainerAppSystemLogs_CL`, with `_s` / `_d` typed-suffix columns.
**`ContainerAppHTTPLogs` arrives via the `aca-http-logs` diagnostic setting into
a native table** — no suffix, typed columns.

```bash
az monitor diagnostic-settings list --resource \
  "$(az containerapp env show -n aitosoft-aca -g aitosoft-prod --query id -o tsv)" -o json
az containerapp env show -n aitosoft-aca -g aitosoft-prod \
  --query properties.appLogsConfiguration -o json
```

Every suffix trap below follows from that one sentence. The diagnostic setting is
**HTTP category only** — console and system are deliberately *not* added there,
because they already arrive by the other route and enabling both double-ingests
and double-bills.

### 5.2 What each instrument can and cannot answer

| Instrument | Answers | Cannot answer |
|---|---|---|
| **`ContainerAppHTTPLogs`** (native, no suffix) | **What MAS actually received.** Wire status, `RequestDuration` (ms), `StartTime` (= arrival, so true in-flight concurrency is a sweep over overlaps), `BytesSent`, `ResponseFlags`, `UpstreamRequestAttemptCount`, `ConnectionId`, `ReplicaName`, `UserAgent`, `XForwardedFor`. **The only surface that records a request the ingress handled with no container** — a cold-start 504, an ingress-terminated request, a 429 we never saw | Anything inside the app. **No history before 2026-08-05** |
| **`ContainerAppConsoleLogs_CL`** | Our own counters: `RenderGate ADMIT` / `REJECT`, `RESULT FAILURE`, `ORIGIN FAILURE`, `RENDER DEFECT`, `COLLAPSE RECOVERED`, `CONSENT DECLINED`, the `📊 Pool:` memory line | Wire outcomes. Anything the ingress absorbed. Slot *release* (only admission is logged), so **not concurrency** |
| **`ContainerAppSystemLogs_CL`** | Platform events: `KEDAScaleTargetActivated/Deactivated`, `SuccessfulRescale`, `AssigningReplica(Failed)`, `ContainerStarted`, `OOMKilled` (in `Reason_s`) | Anything about *why*, most of the time — see §6.2 |
| **Azure Monitor metrics** | `Replicas` (per-minute, the series every replica-hour figure is built on), `UsageNanoCores`, `MemoryPercentage`, `RestartCount` | Anything per-request |

> ⛔ **`ContainerAppConsoleLogs` — without the `_CL` — exists, is empty, and
> returns no error.** It silently answers "zero" to every question you ask it.
> There is no failure mode more expensive than a table that agrees with you.
> Same family, one layer over: `ContainerAppHTTPLogs`' columns arrive as strings
> in some query paths, so wrap any arithmetic in `toint()` / `todouble()` rather
> than assuming the type — `percentile(RequestDuration, 95)` works today, and a
> coercion costs nothing if it turns out to be redundant.

**Retention is 30 days** (`PerGB2018`, no daily cap — verify with
`az monitor log-analytics workspace list -g aitosoft-prod --query "[].{sku:sku.name, retention:retentionInDays, cap:workspaceCapping.dailyQuotaGb}" -o table`).
**Sweep data expires.** Any forensic question about a run older than a month is
unanswerable from Azure, which makes it time-critical to extract what matters
into a task file while the window is open.

**The two instruments disagree by design, and that is the point.** Segment 2:
console `RESULT FAILURE` showed 39 failures while the wire showed 261 × 200,
12 × 500, 1 × 429 — because most failure classes are deliberately 200 +
`success: false`. **Quoting console counts as MAS's error rate overstates it
~3×.**

**Free cross-check that costs nothing:** ingress `/crawl` requests −
`RenderGate ADMIT` lines = pre-admission refusals + 429s. It reconciled segment 2
exactly (274 − 261 = 12 + 1).

### 5.3 Query traps — each of these cost a session

`BadArgumentError: The request had some invalid properties` **names nothing**. It
means *"some identifier in your query is wrong"*, not *"unsupported function"* —
so the first move is always to check column names against a real row, not to
rewrite the logic.

| Trap | What happens | Do instead |
|---|---|---|
| **`-o tsv` on `az monitor log-analytics query` orders columns alphabetically** | Not in `project` order. A tick that reads positionally silently transposes its own numbers and reports them with confidence | **`-o json`, always.** Key by name |
| `az containerapp replica list -o table` | **Hides `restartCount`** — the one field that answers "did anything crash" | `-o json --query "[].{name:name, created:properties.createdTime, restarts:properties.containers[].restartCount}"` |
| `az monitor metrics list … RestartCount --interval PT1M` | ACA emits the metric **only every 5 minutes**, so at PT1M it reads 0 four minutes in five; and it is **cumulative per replica**, so a replica appearing mid-window brings its history in with it | **Sum the series, never sample a bin.** Cross-check against console `supervisord started with pid 1` — they matched exactly at 74 restarts |
| `dcountif()`, `make_set()` with a limit, datetime aggregates in `summarize` | Rejected by the Log Analytics query endpoint | Use `dcount()` + a `where`, `make_set()` unbounded, `min()`/`max()` outside the aggregate |
| `summarize first=min(...)` then `order by first` | `BadArgumentError` — `first`/`last` collide with the aggregate names | Rename to `t0` / `t1` |
| **`contains` and `has` are TERM-based on `_CL` text columns** | A multi-word needle becomes a term-**AND**, not a phrase. Measured 2026-08-16 on `CONSENT STRUCTURAL`: `contains` **383**, `has` **383**, `contains_cs` **0**, `indexof(…) >= 0` **0** — and **0 is the truth**. The failure is **silent and directional: it can only over-count, and it over-counts most on exactly the rare tokens you are looking for** | **`indexof(Log_s, "…") >= 0` for every multi-word token** — `RenderGate REJECT`, `RenderGate ADMIT`, `ORIGIN FAILURE`, `RESULT FAILURE`, `TERMINAL FAILURE`, `RENDER DEFECT`, `COLLAPSE RECOVERED`, `WALL-CLOCK FENCE 504`, `Janitor reaped`, `refusing new browser`, `Memory pressure`, `Browser cap reached`. It gets no free-text-index acceleration, so it is slower. **`contains` is often harmless** — `RenderGate ADMIT` returned 184,404 under both — **but you cannot know that in advance** |
| `contains "reap"` for the janitor | Matches supervisord's benign `reaped unknown pid … exit status 0` and floods with thousands of false positives (2026-04-17) | Match the full token with `indexof` |
| `ContainerAppConsoleLogs_CL` has **no `ReplicaName_s`** | The obvious column does not exist | The replica column is **`ContainerGroupName_s`** |
| `ContainerAppConsoleLogs_CL` is **workspace-wide** | `aitosoft-edge` logs into it too, so `dcount(ContainerGroupName_s)` counted their replica as ours | **Every console query needs `ContainerGroupName_s startswith 'crawl4ai'`** |
| `ContainerAppHTTPLogs` is **environment-wide** | Same problem, different table | Filter `ContainerAppName == "crawl4ai-service"` |
| `ContainerAppSystemLogs_CL.Count_d` | It is a **cumulative per-replica tally**, not an event count | Count rows, or diff the tally |
| `ContainerAppHTTPLogs` column guesses | `StatusCode_d`, `ReplicaName_s`, `DurationMs_d`, `ContainerAppName_s` **do not exist** | Unsuffixed: `StatusCode`, `ReplicaName`, **`RequestDuration`** (ms), `ContainerAppName` |
| `ConnectionId` alone | Unique only **per Envoy pod**, and there are 2 — keying on it merged ids across pods and inflated connection lifetime 3× | Key on **`(EnvoyPodName, ConnectionId)`** |
| Grepping `Log_s` for OOM | The word `OOM` appears **only in `Reason_s`**, never in `Log_s`, and the exit code is quoted (`exit code '137'`) — both obvious greps miss it | `where Reason_s == "OOMKilled"` |
| `dcount(replica)` at 10-minute bins | Reports **churn** as if it were concurrency (said 30 where a 1-minute bin said 6) | Bin at 1 minute; cross-check `az containerapp replica list` |
| Reading a memory trend off a per-tick window **maximum** | A maximum can only grow as the window grows, so consecutive ticks manufacture a rising line out of flat data | Keep `by bin(...)`; `max` and event *counts* are unbiased, **percentiles are not** |
| Quoting a memory **percentile** at all | The janitor's sampling interval is itself a function of memory (**10 s above 80 %, 30 s above 60 %, 60 s otherwise**), so high states are oversampled ~6× — measured overstatement **5.3×** for time-above-X | `max` and refusal *counts* are unbiased because they are events, not samples |
| Pairing `mem=` with the `hot=`/`anon=` beside it on the same line | The janitor reads `mem_pct` **before** its sleep and logs it **after** the cleanup, so the percentage is up to `interval` seconds (≤60 s) **older** than the counts printed next to it | Treat each `mem=` as belonging to the **previous** tick |
| `dcount(...)` without `by ContainerGroupName_s` | A per-replica count cannot bound a global cardinality — with ~5 replicas each seeing a fifth of the hosts, the number means nothing. Nobody ran it with the `by` | Add the `by`, then reason about the union |
| Searching for fence 504s in the console log | `api.py`'s "Crawl exceeded the time limit" produced **no console line** on 0.9.2 — **zero matching lines ≠ zero 504s** | Count 504s at the ingress (`ContainerAppHTTPLogs`), which cannot miss them |

Two counting rules that are not query syntax but belong with them:

- **Count failures by `failure_class=`, never by the log token.** `RESULT FAILURE`
  (result loop) and `ORIGIN FAILURE` / `TERMINAL FAILURE` (exception path) are
  **disjoint** — no request emits both. Querying the token reported **9**
  `origin_unreachable` events when the truth was **21 on 13 companies**, a **57 %
  undercount**, because a dead domain is refused *before* render admission.
- **We cannot count HTTP 404s at all and MAS can — 13:1 against us.** A 404 that
  serves a styled "page not found" body renders fine ⇒ `success: true`, no log
  line anywhere, while the envelope still carries `status_code: 404`.
  **`failure_class` answers "whose fault"; `status_code` answers "what did the
  origin say". Never substitute one for the other.**

### 5.4 Starting points

```bash
export LAW_ID=$(az monitor log-analytics workspace list \
  --query "[?name=='workspace-aitosoftprodnCsc'].customerId | [0]" -o tsv)
az monitor log-analytics query -w "$LAW_ID" --analytics-query '<kusto>' -o json
```

```kusto
// Wire truth: what MAS received, and what the ingress answered alone
ContainerAppHTTPLogs
| where TimeGenerated > ago(20m)
| where ContainerAppName == "crawl4ai-service"
| summarize n=count(), p95_s=round(percentile(RequestDuration,95)/1000.0,2),
            max_s=round(max(RequestDuration)/1000.0,2)
    by StatusCode, ResponseFlags, no_container=isempty(ReplicaName)
```

> ⛔ **An empty `ReplicaName` does NOT mean "no container saw it", and this file
> said it did.** Measured across the final 186,178-request sweep: **29 rows with
> an empty `ReplicaName`, 22 of them `StatusCode 200` with
> `ResponseCodeDetails = via_upstream`.** All 29 carry
> `UpstreamHost 100.100.248.100:4045` — **the ACA activator, a fixed platform
> address, not a pod IP** — and every one lands on a `KEDAScaleTargetActivated`
> moment. **They are requests buffered during scale-from-zero.** Read them as a
> cold-start marker if you like; **never as a failure.**
>
> **The real "the ingress could not reach a container" signal is
> `ResponseFlags` / `ResponseCodeDetails`**, and it is vanishingly rare: **2 rows
> in 186,178** (`503` / `URX,UF` / `upstream_reset_before_response_started`). The
> 30-day baseline is `ResponseFlags == "-"` and
> `UpstreamRequestAttemptCount == 1`; a raced upstream close appears as
> **503/`UC`**, never as a 502.

**Ingestion lags.** Run any query ~5 minutes after the event and again ~30
minutes later — measured 2026-08-08, our own `/health` probes were not queryable
for several minutes. A query run too early answers "nothing happened", which is
the same failure shape as the unsuffixed-table trap.

```kusto
// Platform events — replica history stated, not inferred from console-log bins
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(1h)
| where ContainerAppName_s == 'crawl4ai-service'
| where Reason_s in ('SuccessfulRescale','AssigningReplica','ContainerStarted','OOMKilled')
| project TimeGenerated, Reason_s, Log_s | order by TimeGenerated asc
```

```kusto
// Pool memory distribution — note the app filter and the bin
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(20m)
| where ContainerGroupName_s startswith 'crawl4ai'
| where Log_s contains "Pool:" and Log_s contains "mem="
| extend mem_pct = toreal(extract(@"mem=([\d.]+)%", 1, Log_s)),
         anon_mb = toreal(extract(@"anon=([\d.]+)", 1, Log_s))
| summarize p50=percentile(mem_pct,50), p99=percentile(mem_pct,99), max=max(mem_pct),
            anon_p50=percentile(anon_mb,50), n=count() by bin(TimeGenerated, 5m)
```

**Read `anon`, not the percentage** — §6.3.

### 5.5 The memory alert fires and nobody hears it

```bash
az monitor metrics alert show -n crawl4ai-memory-high -g aitosoft-prod \
  --query "{enabled:enabled, sev:severity, window:windowSize, freq:evaluationFrequency, crit:criteria, actions:actions}" -o json
az monitor action-group show -n crawl4ai-oncall -g aitosoft-prod \
  --query "{email:emailReceivers, sms:smsReceivers, webhook:webhookReceivers, arm:armRoleReceivers}" -o json
```

Four things worth knowing before you act on this alert:

1. **The action group has zero receivers of any kind** — email, SMS, webhook and
   ARM-role lists are all empty (Tero was removed as the only receiver
   2026-04-17). The alert is enabled and evaluating; **nobody is paged.**
2. **It fired 32 times over 170.8 hours in 30 days.** That is not a rare event —
   it is a near-permanent condition, for the reason in §6.3.
3. ⛔ **The `monitorCondition` query this repo prescribed returns `null`
   unconditionally, because that field does not exist on the `metricAlerts`
   resource.** Three documents told sessions to read it as "is it firing right
   now", and it can only ever answer `null`. The working channel is the alerts
   API:
   ```bash
   az rest --method get --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&timeRange=30d" \
     --query "value[?contains(name,'crawl4ai')].{name:name, state:properties.essentials.monitorCondition, start:properties.essentials.startDateTime}" -o table
   ```
4. **It reads the platform metric `MemoryPercentage`, not our
   `get_container_memory_percent`** — documented in
   `azure-deployment/setup-memory-alert.sh:62`, which several docs claimed was
   undocumented. The two are **not independent**: `MemoryPercentage` is
   `WorkingSetBytes / limit`, the *same* working-set definition as ours, except
   Azure divides by ~3.92 GiB allocatable, so it reads **~2.2 points higher**.
   **It therefore inherits the whole pathology in §6.4** — a threshold at 85 on a
   signal whose median already sits above 85. Which is exactly what "32 fires in
   170.8 hours, longest single episode 52 hours continuous" means: **that is not
   an event, it is the weather.** Do not treat one as corroboration of the other;
   they are one measurement with two denominators.

`azure-deployment/setup-memory-alert.sh <email>` recreates the rule *and*
re-subscribes a receiver. It is idempotent.

**Rate limiting is per-replica, not global** (upstream's limiter uses `memory://`
storage) — accepted risk from the 2026-04-14 scale audit. Fine for a single
trusted client; do not rely on it as a global cap.

---

### 5.6 What "normal" looks like on the wire

`az` cannot answer this, so it is recorded. Both windows are real MAS sweeps;
the difference between them is the scale trigger, not the traffic.

| | 39.4 h sweep, trigger 6 | final 175.5 h sweep, trigger 12 |
|---|---|---|
| `/crawl` requests | 36,783 | **186,178** |
| 200 | 94.9 % | ~95 % |
| **429** | 4.1 % (1,521) | ~1–2 % |
| 500 | 0.68 % (249) | 0.26 % of captures lost |
| **504** | **0** | **0** |
| p50 / p90 / p99 | 4.99 / 7.17 / 29.68 s | ~5.2 / ~10.6 / ~23.0 s |
| max | 245 s | — |
| egress | 11.75 GB, p50 234 KB, p99 1.8 MB | — |
| max single response | **31.1 MB** | 3.42 MB in the matched window |
| ingress rows with no container | 14 (misread — see §5.4) | 29, of which 22 were **200s** |

Three things to read off it:

- **A 504 is genuinely abnormal.** Zero across both sweeps.
- **`BytesSent` is the only instrument for payload size anywhere in either
  repo**, and nothing read it until 2026-08-09 — when it turned out one page had
  been returning **232 MB, four times, at HTTP 200 `success: true`, with no log
  line of any kind**. The four responses over 10 MB in the 39-hour window all
  returned 200 in 8–47 s and nothing flagged them. **If you are asked "is
  anything pathological", this column is the question no counter answers.**
- **429 rate is not a threshold** (§3.8). 4.1 % here was ~99 % memory guard.

---

## 6. The failure modes that leave no trace

### 6.1 Exit 137 has at least three causes on ACA

1. **A real OOM** — the cgroup limit hit.
2. **SIGKILL after the 30 s grace on scale-to-zero** (§2.4). Ordinary, expected.
3. **Ephemeral-storage eviction at the 8 GiB cap** — and this one is ours to
   worry about, because we launch Chromium with **`--disable-dev-shm-usage`**
   (`config.yml`, `browser_manager.py`), which moves Chromium's shared memory
   into `/tmp`, which is **that same ephemeral budget**.

**Nothing watches ephemeral storage, and it has the identical signature to an
OOM.** So a 137 is not, on its own, a memory finding. If you are chasing one and
the memory series is unremarkable, this is the hypothesis nobody has tested.

### 6.2 ACA labels a memory kill only for a *repeat* kill

Measured over the sweep: **7 labelled kills came 1.2–6.8 minutes after the
previous boot of that replica; 27 unlabelled restarts came a median 178 minutes
after, none under 10.** The label appears only when the kill lands inside the
kubelet crash-backoff window.

**An isolated memory kill produces no platform event at all.** It is invisible
to `Reason_s`, invisible to `az containerapp replica list`, and invisible to any
alert.

### 6.3 A container restarts without the replica changing

The replica object survives, **`createdTime` never changes**, and most restarts
carry **no `Reason_s`**. A monitoring session reading the replica list sees
healthy replicas and concludes nothing happened. That has happened here twice.

```kusto
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h)
| where ContainerAppName_s == 'crawl4ai-service'
| where Reason_s == "ContainerStarted"
| project TimeGenerated, Log_s | order by TimeGenerated asc
```

Cross-check each timestamp against replica `createdTime`: **any `ContainerStarted`
not within ~10 s of a replica creation is a silent restart.** Confirm with the
console line `supervisord started with pid 1`. **Ordinary scale churn produces
the same line**, so look for the `SuccessfulRescale` scale-down/up pair before
calling one a crash.

### 6.4 Memory: the guard's threshold sits inside its own signal, and no reading predicts a kill

Two facts that together mean **you cannot escalate on a memory number**:

- Our guard reads a **cache-inclusive** working-set figure. Its 85 % threshold
  sits **below the median of its own signal** (p25 82 %, p50 ~86.5 %, p75 90 %),
  so it reads above its own trip point **~58–61 % of every hour, all night**,
  while true `anon` is **flat** (p50 ~2,900 MB of 4,096, unchanged over 12 h).
  ~1,000 refusals/night is a **threshold-crossing count on a signal centred on
  the threshold** — a 1-point distributional wobble swings it tens of percent.
  Both repos independently read a trend into it and both were reading the same
  artefact. MAS's 4,455 refusal readings reproduce our distribution **to one
  decimal on every percentile**. **Count refusals; never interpret them.**
- **The first confirmed `OOMKilled` / exit 137 in the service's history
  (2026-08-15 04:30) fired at ordinary readings**: `anon` 2,835–3,445 MB and the
  guard at 80.5–93.5 % in the preceding 90 s — the middle of the all-night band.
  It self-recovered in seconds and **cost zero pages**. The kill lands on a
  transient allocation *between* 10-second samples.

**There is no leak.** Splitting a 53-hour window in half: our `anon` p50 moved
**2,932 → 2,958 MB, +0.6 %**; MAS's independent gauge moved **+0.13 points**. Two
repos, two instruments, no accumulation.

**Blast radius grew when the fleet shrank.** At 12 replicas an OOM removed 8 % of
the fleet; at 2 it removes **50 %**.

**So the operational rule is:** detect a kill *after the fact* (§6.2, §6.3),
check whether it cost pages, and **restart only if pages are being lost now.**

### 6.5 Cold start, and why "KEDA scaled" is not "capacity arrived"

Measured 2026-07-16/17: **~8–12 s** from scheduling to render-capable on a node
with the image cached (container start → "Application startup complete" ≈ 4.3 s,
and the browser launch is *inside* the lifespan, so serving implies
browser-ready). On an **uncached** node, **+39.9 s** for the image pull — the
image is **1.79 GB** — so ~50 s total.

> **Scale-out ramp ≠ serving ramp, and the gap is where the 504s live.** In the
> 2026-07-17 measurement KEDA went **0 → 4 → 8 → 16 → 19 → 30 in 72 seconds**,
> but **only 6 replicas served any traffic for the next 68 seconds** — the other
> 24 were waiting on node provisioning and the image pull. Serving waves landed
> at +68 s, +80 s, +135 s, last replica at +190 s. **Every 504 in that incident
> started inside the 6-replica saturation window and none after it.** So a
> replica count from `az containerapp replica list` or from `SuccessfulRescale`
> is *capacity ordered*, not capacity available. If you need capacity available,
> take first-`RenderGate ADMIT` per replica from the console log.

Scale-in behaved correctly in the same run: first "All metrics below target"
~7 minutes after the last request (the KEDA cooldown), then 30 → 16 → 9 → 4 → 2
→ 1 within a minute, then to zero.

**`ReplicaUnhealthy` events are cold-start noise, not deaths.** One 39-hour
window logged **755** of them against **588** container starts — **≈1.3 per cold
start** — and every sample read `Readiness probe failed … connect: connection
refused` or `Startup probe failed …`, i.e. a replica that had not finished
booting. **Do not read 755 as 755 unhealthy replicas.** Read the reason string
first, and normalise churn per hour against a control window (16.5/h overnight
against 28.5/h in a control segment: *lower*, not new).

For scale, the same window: **588 `ContainerCreated`/`ContainerStarted`, 298
`ImagePulled`, 277 `StoppingContainer`, 388 `SuccessfulRescale`, 38
`TriggeredScaleUp`, 30 `ScaleDown`** — for an average of 8.34 replicas. **The
fleet churns continuously and that is normal.** It is also why §6.3's
silent-restart detection needs the `SuccessfulRescale` cross-check.

### 6.6 The timeout stack, outermost first

These are not all Azure's, but they only make sense together, and the outermost
one is Azure's and is not configurable in our tier:

| Bound | Value | Owner |
|---|---|---|
| MAS client hard abort | 210 s | MAS |
| **Azure ingress timeout** | **240 s** | **ACA platform** |
| Our wall-clock fence (starts *after* render admission) | 180 s | `config.yml limits.wall_clock_s` |
| RenderGate queue wait | 15 s | `aitosoft_admission.py` |
| `terminationGracePeriodSeconds` on a revision change | **30 s** (unset ⇒ ACA default) | ACA, §2.4 |

Two consequences that have each bitten:

- **The gap between render admission and the fence is unfenced**, and the budget
  from there to Azure's 240 s is only **~40 s** — inside which a cold browser
  launch can already take 30 s. That gap is where a hang escapes every timer we
  own and lands on the ingress instead.
- **Worst case ≈ 200 s** (15 s queue + browser acquisition + the 180 s fence)
  against MAS's 210 s abort. That is a 10-second margin, not a mechanism. Do not
  raise the fence without telling them.

⚠️ **`az containerapp logs show` on a scaled-to-zero app causes a cold start** —
verified: KEDA activation with zero ingress requests. That is a real cost (a
replica boots and bills) and, worse, it **perturbs the thing you are measuring**.
Prefer Log Analytics queries; reach for `logs show` only when you need the live
tail and know the app is already warm.

---

## 7. Probing the network from inside the container

**You almost never need `az containerapp exec`.** `render_mode: "static"` is an
in-container httpx GET that returns the origin's real status, byte count and
error class — use it as the network probe:

```bash
curl -s -X POST "$CRAWL4AI_API_URL/crawl" -H "Authorization: Bearer $CRAWL4AI_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"urls":["https://api.ipify.org"],"render_mode":"static"}' \
  | jq -r '.results[0].markdown.raw_markdown'
```

Swap the URL for any host to answer "can the crawler reach this, and what does it
get?" — status, timing and `error_message` all come back inside a 200. Egress is
a single Azure West Europe address (in `PRIVATE.md`); the environment has **no
VNet integration**, so it comes from Azure's shared SNAT pool and is **not
contractually stable**.

If you do need a real shell, `az containerapp exec` has two traps: it needs a pty
(wrap it in `script -qec "…" /dev/null`), and the command is carried **in the
websocket URL**, so anything over roughly 300 characters fails with
`Could not find container` or a 404 handshake. **Keep exec commands tiny.**

Two things it is genuinely the only instrument for.

**Whether the cgroup has swap** — a one-command question that has been an open
prerequisite on the memory work since it was written and has still never been
run. If swap exists, the whole memory framing shifts:

```bash
script -qec "az containerapp exec -n crawl4ai-service -g aitosoft-prod --command 'cat /sys/fs/cgroup/memory.swap.max'" /dev/null
```

**The resolver ACA injects:**

```bash
script -qec "az containerapp exec -n crawl4ai-service -g aitosoft-prod --command 'cat /etc/resolv.conf'" /dev/null
```

ACA injects `options ndots:5` plus four search domains. Against a nameserver that
never answers that is **22.75 s** per `getaddrinfo` (8 UDP queries) versus 12.74 s
in this devcontainer. **Measure the resolver in the environment that runs, not
the one you are typing in.** `RES_OPTIONS="timeout:2 attempts:2 ndots:1"` in
`supervisord.conf` is what bounds it; it needs no root.

---

## 8. Troubleshooting

| Symptom | First move |
|---|---|
| **401** | Token mismatch. Confirm the env var *exists* (never print it): `az containerapp show -n crawl4ai-service -g aitosoft-prod --query "properties.template.containers[0].env[].name" -o tsv`. Check the header is `Authorization: Bearer <token>` |
| **429** | **Split it before reading anything into it** (§3.8). `RenderGate REJECT` = concurrency; `refusing new browser` = the memory guard, ~99 % of them, benign |
| **500** | Ours by definition (`failure_class` reserves 5xx for us). Query `RESULT FAILURE` / `TERMINAL FAILURE` by `failure_class=`, not by token (§5.3) |
| **504** | The 180 s wall-clock fence. One `WALL-CLOCK FENCE 504` line per event, with URL. Expect a few during cold ramp; investigate only if they cluster *post*-ramp or grow across windows |
| **Slow first request** | Cold start (§6.5) |
| **Replica non-Running > 10 min** | Restart — **but the replica list is blind to a container restart** (§6.3), so "all Running" is not evidence that nothing crashed |
| **App runs but is unreachable** | Check the ingress FQDN against `az containerapp show … properties.configuration.ingress.fqdn`. An environment migration changes it (§3.6) |
| **`BadArgumentError` from a Kusto query** | §5.3. It names nothing; check column names against a real row first |
| **Deploy hard-fails on drift** | **Nothing was built and nothing shipped** (§2.2). Reconcile the constant or production, then re-run |
| **Deploy refuses on replica count** | §2.3. Wait for the fleet to drain (~9 min after the last request) |

---

## 9. What this file deliberately does not say

- **Any current configuration value.** §0 is the answer. If you want to add one,
  add the query instead.
- **Which image is deployed, or which revision.** Both drift within hours and
  both have caused wrong actions.
- **Secrets, workspace GUIDs, IP addresses, subscription IDs.** `PRIVATE.md`.
- **How the crawler works.** `CLAUDE.md` and `AITOSOFT_CHANGES.md`.

Before every commit, this must produce no output:

```bash
git grep -InE '(crawl4ai-(test-)?|jwt-secret-)[0-9a-f]{32,}' -- .
```

---

## 10. What I am least sure of

Written in the same spirit as a task file, because this document now carries
claims that decide production actions.

- **`a ≈ 5.2` and the loop-gain table are a fit over 1,370 scaling decisions
  within one regime, not an observation.** No ACA metric exposes the scaler's
  value. The **metric-name list is observed** and is the solid part; the gain is
  the part to distrust first. What raises my confidence is that a completely
  independent structural argument (6 upstream connections per replica, from
  `render_capacity` + `admission_queue` under `--keep-alive 300`) lands within
  ~15 % of it. If someone finds a way to read the scaler's input directly, that
  supersedes §3.2 entirely.
- **"Anything ≥ 7 lands in the same place" is an inference. We have run 2, 6 and
  12; nothing has been run at 7–11.**
- **The `gunicorn --keep-alive 300` mechanism and the downstream-connection
  mechanism are not fully separated.** The downstream version is refuted *at the
  new operating point* (no fleet-independent connection count gives 12 replicas
  at trigger 6 and 2 at trigger 12), which is strong but not the same as running
  the discriminating arm. Nobody has run the third arm (`--no-keepalive` at a
  matched rate, or varying `gunicorn --keep-alive`) that would settle it — and it
  decides ~$7/day, not ~$75/day, which is why it keeps not being run.
- **The surge arm in §3.7 moved two variables** (trigger *and* client connection
  pooling). I have written it as an elasticity observation, which it is; it is
  **not** a trigger A/B and must not be quoted as one.
- **The workload-profiles migration is priced from Microsoft's documentation, not
  from an attempt.** The claims that the Consumption profile allows 4 vCPU / 8 GiB
  at identical rates with no management fee, and that scale-to-zero survives,
  come from docs. **The support-ticket route (a per-case memory override) is
  cheaper than all of it and has never been tried** — try that before believing
  any of this paragraph.
- **The ephemeral-storage cause of exit 137 is reasoned, not observed here.** The
  8 GiB cap and the `--disable-dev-shm-usage` → `/tmp` chain are both real; no
  eviction has been caught in the act, because nothing measures it.
- **Every cost figure derives from portal downloads a human made** (§4.1). They
  reconcile to our own replica-hour accounting within 2.1 % day by day, which is
  strong — but there is no automated export, so none of it is reproducible from
  a command today.
- **The 30-day retention means most of the evidence behind §3.7 and §6 has
  already expired.** What is written here is what survived into task files. If a
  number matters, re-derive it while a sweep is running, not afterwards.

---

## Related

| Doc | When |
|---|---|
| `azure-deployment/deploy-image.sh` | The deploy itself — heavily commented; it is the executable half of §2 |
| `azure-deployment/batch-scale.sh` | The emergency valve, and the CLI no-op it works around |
| `azure-deployment/setup-memory-alert.sh` | Recreates the alert and its receivers |
| `OVERNIGHT_PLAYBOOK.md` | Tick-by-tick monitoring during a sweep — signal interpretation, intervention thresholds |
| `AITOSOFT_CHANGES.md` | Why the service is the way it is (authoritative change log) |
| `tasks/done/autoscaler-ratchets-to-the-cap.md` | The scale-rule investigation |
| `tasks/done/crawl-cost-is-idle-replicas-not-slow-renders.md` | The cost investigation, in full |
| `tasks/done/trigger-12-readout-2026-08-14.md` | The A/B readout in §3.7 |
| `tasks/done/post-sweep-closure-2026-08-17.md` | What was closed after the final sweep, and the USD correction |
| `PRIVATE.md` (gitignored) | Workspace ID, egress addresses |

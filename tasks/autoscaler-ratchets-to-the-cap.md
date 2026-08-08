# The autoscaler ratchets to `maxReplicas` on a load that justifies one replica

**Status:** OPEN — diagnosed 2026-08-08, not fixed. One config value is the
likely change; **the measurement is the actual work.**
**Size:** M. The edit is a single number in the ACA scale rule. Validating it
honestly is two controlled experiments and a live run.

**Written by the coordinator session that measured it during MAS's segment 3.
Argue with it.** Ten consecutive sessions have found the previous session's file
materially wrong about something load-bearing, and this one already found
*itself* wrong once while being written — see "The root cause I was about to
ship, and the query that killed it". Every measurement below is re-runnable in
minutes against stored Log Analytics data; re-run the ones the change rests on.

**Read this before you plan anything: the over-provisioning is currently doing
safety work by accident.** This is not a cost-only cleanup, and treating it as
one is the way to cause a regression MAS will feel.

---

## The finding in one paragraph

On 2026-08-08, MAS ran segment 3 (50 companies, `--concurrency 3`, 04:54–05:24
UTC). Our fleet scaled to **30 replicas — the `maxReplicas` ceiling at the time —
and sat there.** Measured from ingress request durations, the true concurrency
over that entire window was **~1.2 requests at a time, peaking at 2.9 in any
minute**. At the scale rule's target of 2 concurrent per replica, that workload
justifies **one** replica. The scaler climbed monotonically for ten minutes with
no scale-down, then took over twenty minutes to drain. The shape is a ratchet:
scale-up responds to every small burst, scale-down is heavily damped, so the
replica count tracks the accumulated peak of every burst across the run rather
than current load.

---

## Why this is not a pure cost win, and why that framing matters most

`render_capacity: 2` (RenderGate, `aitosoft_admission.py`) and the ACA scale rule
`concurrentRequests: 2` are set to the same number, and `config.yml:183-184` says
they MUST match. **They do different jobs, and only one of them is a safety
mechanism.**

- The **gate** is the hard cap. It cannot be exceeded. It is what prevents a
  2 vCPU replica from oversubscribing, and it has a 4-deep queue on top, so a
  replica can safely hold **6** in-flight requests (2 rendering + 4 queued).
- The **scale rule** only decides *when Azure adds a replica*. It protects
  nothing. Setting the trigger equal to the hard cap means "add a replica the
  instant any replica is full", which is maximally twitchy.

So the obvious change is to raise the scale trigger above the gate's capacity.
**But the reason to be careful is this:** MAS saw **zero 429s** across segment 3.
Part of that is because we were running 30 replicas for a 1-replica load — there
was always enormous spare capacity to absorb a burst. Reducing the
over-provisioning gives back exactly the headroom that has been absorbing MAS's
bursts.

**This task is therefore a trade, not a saving: cost against cold-start
rejections.** A change that halves our replica count and reintroduces 429s at
segment start is a bad trade, and our documented history says a 429 is the one
thing MAS's retry path handles but notices. Any proposal that does not measure
both sides is not finished.

---

## The evidence, and how to re-derive it in minutes

All of it is in Log Analytics. `LAW_ID` is in `PRIVATE.md` (do not inline it in a
tracked file). Window: `2026-08-08T04:54:00Z` .. `05:25:00Z`.

### 1. True concurrency was ~1.2, and this is the number the whole task rests on

```kql
ContainerAppHTTPLogs
| where TimeGenerated between (datetime(2026-08-08T04:54:00Z) .. datetime(2026-08-08T05:25:00Z))
| where ContainerAppName == "crawl4ai-service" and Path == "/crawl"
| extend d = toreal(RequestDuration)/1000.0
| summarize reqs=count(), busy_seconds=sum(d), concurrency=round(sum(d)/60.0,1)
    by bin(TimeGenerated,1m)
| order by TimeGenerated asc
```

Result: per-minute concurrency ranged **0.1 – 2.9**, mean ~1.2. Request duration
distribution over the same window: **n=299, p50 4.95 s, p90 9.35 s, p99 36.2 s,
max 51.6 s, mean 7.05 s**.

`ContainerAppHTTPLogs` is the right instrument here and `ContainerAppConsoleLogs_CL`
is not: only the HTTP table carries `RequestDuration`, and concurrency is
`sum(duration)/window`, which needs it. Our own `RenderGate ADMIT` lines log
admission but never release, so the console logs **cannot** produce a concurrency
figure. That is worth knowing before you try.

### 2. The scaler ramp, monotonic with no mid-run scale-down

```kql
ContainerAppSystemLogs_CL
| where TimeGenerated > datetime(2026-08-08T04:50:00Z)
| where ContainerAppName_s == "crawl4ai-service" and Reason_s == "SuccessfulRescale"
| project TimeGenerated, Log_s | order by TimeGenerated asc
```

`2 → 4 → 5 → 6 → 7 → 9 → 11 → 13 → 15 → 17 → 19 → 21 → 25 → 30`, from 04:54:43 to
05:05:09. First scale-down at **05:10:41** ("All metrics below target"), then
27 → 25 → 22 → 20 over the following twenty minutes. Fourteen `TriggeredScaleUp`,
seventeen `SuccessfulRescale`.

### 3. Replica count, confirmed by two independent instruments

Log-derived (`dcount(ContainerGroupName_s)` per 1-minute bin over
`ContainerAppConsoleLogs_CL`) showed a smooth ramp with plateaus —
6,6,6 / 12,12,12 / 19×5 / 30×4 — which is what distinguishes real scaling from
name churn. `az containerapp replica list` independently reported **22 alive**
while the log said 22–23. **Do not trust a 10-minute `dcount` for this**; at
10-minute resolution the same query reports 30 in a bucket where only a few were
concurrent, and that nearly became a wrong headline.

### 4. Two system-log warnings that look alarming and are not

`AssigningReplicaFailed` ×126 is literally `"Waiting for infrastructure to be
ready"` — normal while Azure provisions nodes during aggressive scale-out.
`ReplicaUnhealthy` ×33 is `Readiness probe failed ... connection refused`, i.e.
the probe arriving before gunicorn binds, once or twice per replica boot. Both
are scale-out noise. They are recorded here so the next session does not spend an
hour on them, as this one briefly did.

### 5. Quota, and the ceiling that actually exists

```bash
az containerapp env list-usages --ids <env-id> -o table
```

`ManagedEnvironmentConsumptionCores`: **limit 100**. MAS's `aitosoft-edge` shares
the environment but is `min=max=1` at 0.25 cores, so the quota is effectively all
ours. At 2 vCPU per replica the hard ceiling is **50 replicas**. This is verified
read-only; per the `--memory 8.0Gi` lesson in `CLAUDE.md`, a quota that permits a
value is not the same as a command that succeeds — see "What changed today".

---

## The root cause I was about to ship, and the query that killed it

My leading hypothesis was a **feedback loop**: more replicas → more health-probe
traffic → looks like load → more replicas → runaway to the cap. It fits the ramp
shape perfectly, it explains why the climb continues while real load is flat, and
it would have been a satisfying root cause with an obvious fix.

It is wrong. Health probes through the ingress during the whole run:

```kql
ContainerAppHTTPLogs
| where TimeGenerated between (datetime(2026-08-08T04:54:00Z) .. datetime(2026-08-08T05:25:00Z))
| where ContainerAppName == "crawl4ai-service"
| summarize requests=count() by Path
```

**One path only: `/crawl`, 299 requests. `/health` = 0.** Probes do not traverse
Envoy, so they cannot be in the scale metric. Recorded because it is exactly the
plausible-but-wrong root cause this repo keeps catching, and because a fix shipped
on it would have changed nothing while appearing to work.

**What I could not determine: the metric ACA's HTTP scaler actually uses.** Two
models fit the data loosely — rate-over-window, and burst-ratchet with damped
scale-down — and neither reproduces "30" arithmetically from a 1.2-concurrency
workload. I am not going to pretend to know it. **Design the experiment so it does
not need to be known**: change the number, measure the replica curve and the 429
curve, keep it or revert. That is cheaper than reverse-engineering KEDA and it is
the only evidence that would actually justify the change.

---

## The design space

**A. Raise the scale trigger above the gate's capacity.** `concurrentRequests`
2 → 3, 4 or 6. The gate still hard-caps renders at 2/replica, so no setting here
can oversubscribe a replica; the queue makes 6 defensible on paper. Cheapest edit,
directly targets twitchiness. **Risk: if the metric is not concurrency-based, this
may not move the replica curve at all** — which is itself a useful measurement,
and an argument for trying the smallest step first rather than jumping to 6.
Note `config.yml:183-184` asserts the two MUST match; **that comment becomes wrong
if you do this, and it must be rewritten with the reasoning, not just edited.**

**B. Damp scale-up or accelerate scale-down instead** (`cooldownPeriod`,
`pollingInterval`, KEDA stabilization). Targets the ratchet directly rather than
the trigger. Less familiar surface, and ACA exposes fewer of these knobs than
raw KEDA does — check what is actually settable before designing around it.

**C. Do nothing, deliberately.** The measured cost is roughly **€0.30 per run** of
wasted capacity. Over an 18,000-company sweep it is real but small, and the
over-provisioning is currently buying MAS's zero-429 record. `CLAUDE.md`
principle 7 lists "doing nothing" as a legitimate answer and this is a genuine
candidate for it. **If you land here, say so explicitly and close the task** —
do not leave it open as a permanent background worry.

**D. `minReplicas: 1` during sweep windows.** Solves cold starts, not the ratchet,
and costs money continuously rather than in bursts. Mentioned only because it
interacts with the acceptance test below and someone will suggest it.

### Things I talked myself out of

- **"Lower `maxReplicas` back to 30 (or lower) to bound the waste."** No. The cap
  is not the defect and capping is treating the symptom. MAS's 18,000-company
  plan needs ~40 replicas for ~80 concurrent renders; a tighter cap breaks the
  thing we just raised it for. The ratchet would also still exist, just against a
  lower ceiling.
- **"Use 1 vCPU replicas so more fit in the 100-core quota."** `render_capacity: 2`
  was benchmarked against 2 vCPU (2026-07-17); >2 concurrent renders on that
  hardware degrades all requests. Halving CPU means halving `render_capacity`,
  which buys nothing and re-opens a settled measurement.
- **"Compute the exact KEDA metric and derive the correct setting."** Tried, could
  not, and the attempt is not on the critical path. See above.

---

## The acceptance measurement, and why it is not optional

**A synthetic cold-start burst test is the primary evidence for or against this
change, not a final-review nicety.** Raising the scale trigger makes the scaler
*less* eager, which means fewer replicas per burst, which lands hardest exactly
at cold start — the one moment MAS's traffic is most likely to be rejected. The
change cannot be evaluated without measuring it.

It also closes a question segment 3 left genuinely open. MAS sent a throwaway
warm-up render ~90 s before the batch (11.8 s, closely matching our measured
9.59 s activation + 0.92 s first render), so **their zero-429 result is "the
mitigation worked", not "the effect is absent"**. They have declined to spend
cohort companies on a cold-start arm, correctly — each site is visited once. We
can answer it for them for free.

**Shape of the test:**

- **Target: `example.com`** (RFC 2606, reserved for exactly this). **Not our own
  service** — verified 2026-08-08 that pointing `/crawl` at our own `/health`
  returns HTTP 400 `URL blocked (SSRF protection)` with `failure_class:
  bad_request`. That is correct behaviour and it is why the obvious
  zero-third-party target is unavailable. `fixture_origin.py` is local and
  unreachable from Azure, so it cannot serve here either.
- **Procedure:** drain to true zero replicas (confirm with
  `az containerapp revision list`), then fire N concurrent `/crawl` requests.
  Record: count of 429s, TTFB of the first response, the `SuccessfulRescale`
  ramp, and the resulting replica high-water mark.
- **Pick N to bracket MAS's real shape**, not to stress the fleet: ~12 (flag 3,
  observed) and ~16 (flag 4, next). **Be sparing with a third party even a
  reserved one** — a burst of 80 to prove the big-run case is not justified when
  the 12/16 curve plus the scaler ramp will extrapolate it.
- **Run it before and after the change, same N**, or the result means nothing.

**Baseline reference from real traffic (segment 3, 2026-08-08):** 292 renders /
281 distinct URLs, **0 × 429**, 3.9 % retry amplification, peak 30 replicas,
true concurrency ~1.2. Any candidate setting has to hold the zero.

### The confound you are inheriting, stated plainly

**`maxReplicas` was raised 30 → 45 on 2026-08-08** (revision `--0000038`), so the
ratchet's ceiling has already moved and **a flag-4 run is not directly comparable
to segment 3's flag-3 run on 30**. Two variables have changed between those runs.
MAS's next experiment goes to `--concurrency 4` and is a genuine natural test of
the ratchet — but if you also ship a scale-rule change first, you have three
variables and no attribution. This is the same trap as "a control that shares the
suspected cause is not a control".

You decide the ordering; the constraint is that the synthetic burst test is
*controlled* and does not depend on MAS's schedule, so running it first de-risks
either choice.

---

## What I am least sure of

1. **That raising `concurrentRequests` moves the replica curve at all.** If the
   metric is not what its name says, the change is a no-op and the real lever is
   scale-down damping. This is the single biggest risk in the task, and it is why
   the measurement is the work rather than the edit.
2. **That the cost/429 trade is favourable at any setting.** It may be that the
   ratchet is cheap insurance and option C is correct. I have not measured the
   429 side at all — nobody has, because MAS warmed up.
3. **The €0.30/run figure.** Derived from ACA consumption list pricing and replica
   -minutes, not from an invoice. Order-of-magnitude only. If the decision comes
   down to cost, get the real number from Azure Cost Management first — and note
   that if it turns out to be trivially small, option C gets much stronger.
4. **Whether MAS's fan-out is genuinely staggered.** Our reading of the ramp
   (1 replica at batch start, only 6 renders in the first minute, zero 429s)
   suggests each company's agent fetches the homepage, waits, then fans out —
   which would mean bursts arrive spread over seconds and the cold-start risk is
   smaller than we told them. MAS can settle this for free from the gap between a
   company's 1st and 2nd fetch; it has been asked for and not yet answered.

---

## Where everything lives

| thing | where |
|---|---|
| RenderGate, capacity/queue/429 | `deploy/docker/aitosoft_admission.py` |
| `render_capacity`, `admission_queue`, and the "MUST match" comment | `deploy/docker/config.yml:180-188` |
| Gate acquire + 429 mapping | `deploy/docker/api.py:795-853` |
| ACA scale rule | `az containerapp show ... properties.template.scale` |
| Workspace ID for the queries | `PRIVATE.md` |
| Segment 3 cross-repo exchange | `tmp/mas-repo-messages/` (gitignored) |

## What changed today, 2026-08-08

- **`maxReplicas` 30 → 45**, revision `--0000038`. Verified after the change:
  image, `minReplicas`, scale rule, CPU/memory and all five env vars unchanged;
  `/health` 200; a bad token still 401 (fail-closed intact); MAS's real token
  renders successfully. Fleet ceiling is now **90 concurrent renders**, inside the
  100-core quota, sized for MAS's ~80.
- This raise is **not** part of this task's fix. It was needed for MAS's
  18,000-company plan and is recorded here because it moves this task's baseline.

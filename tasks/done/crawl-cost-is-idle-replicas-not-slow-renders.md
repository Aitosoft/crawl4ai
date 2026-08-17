# The bill is idle replicas, not slow renders — and we have the invoice to prove it

**Status:** open, **not yet implemented**, written 2026-08-14 by the coordinator
session after MAS's message `tmp/mas-repo-messages/42-from-us-your-renders-average-81s-against-your-own-80s-cap.md`
**Size:** S in code (config only), **L in judgement** — the cheap levers are one
`az` call each, but which one to pull rests on a mechanism that is *fitted, not
proven*, and the biggest lever is in the other repo.
**Gate:** nothing here should ship without the 20-minute two-arm experiment in
§6, which costs zero egress and settles the mechanism.

---

## Why this file exists

MAS reported that our renders average **81 seconds** against an 80,000 ms
`page_timeout`, that this is **95 % of their Azure bill** (~$85/day), and asked
us to run the one discriminator only we can run: the actual distribution of
render durations.

**Their cost figure is right — confirmed against the invoice — and their
diagnosis is wrong.** The renders are 5.39 s. The money goes somewhere else, and
the somewhere else was already half-documented in this repo.

**Do not reply to them with a correction alone.** They were right about the size
and the urgency, they retracted eight of their own hypotheses before sending, and
they asked to be corrected. §7 is what to send.

---

## 0. The finding in four lines

1. **Mean render is 5.39 s, not 81 s.** 93,076 requests, 2026-08-11 → 08-14.
   Exactly **4 requests** landed in the 75–85 s band. There is no spike at 80 s.
2. **Their Little's Law substituted provisioned capacity for occupancy.**
   Measured occupancy **1.639**; 1.639 / 0.3042 req/s = **5.388 s**, which equals
   the directly measured mean to three decimals.
3. **The cost is real and it is ours.** Container Apps **€398.89** of €421.86
   total Azure spend, 2026-08-09 → 08-14 — **94.6 % of Azure**.

   > ⛔ **CORRECTION, and it was ours as much as theirs.** This file first said
   > "the models that read the pages cost €1.97, so fetching costs **202×** the
   > intelligence." **That is wrong.** €1.97 is the Azure `Foundry Models` line
   > item, and **MAS's models do not run on Azure** — their real spend is
   > **$29.71–36.08/day** (their `43-…`, matching their provider's billing within
   > 3 %). Corrected ratio: crawl ~€75–90/day against models ~$30–36/day —
   > **~2.4×, not 202×.**
   >
   > **The error is instructive and is exactly the one MAS made in `42-…`:** a
   > total read off one invoice that did not contain the whole population. Both
   > repos did it on the same day, in opposite directions, and neither caught it
   > from inside its own data. **Do not quote a cross-repo ratio computed from
   > one provider's bill.**
   >
   > The waste is unaffected — it is ~7 % slot utilisation either way — but the
   > *rhetoric* changes: this is not "the crawler dwarfs the intelligence", it is
   > "the crawler costs ~2.4× the intelligence and roughly two thirds of that is
   > idle replicas". After the fix it should sit **below** model spend.
4. **We hold ~23.6 render slots to do 1.6 renders of work — 7.0 % utilisation,
   on every single day of the sweep.**

---

## 1. The duration distribution — the discriminator MAS asked for

`ContainerAppHTTPLogs`, `Path startswith "/crawl"`, 2026-08-11T00:00Z →
2026-08-14T13:00Z. **The duration column is `RequestDuration`, in milliseconds,
unsuffixed — there is no `DurationMs`** (querying it fails with a
`BadArgumentError` that names no column, which is how the mistake survives).

| n | mean | p50 | p75 | p90 | p95 | p99 | max |
|---|------|-----|-----|-----|-----|-----|-----|
| 93,076 | **5.39 s** | 4.84 | 5.64 | 6.82 | 8.10 | 29.48 | 267.12 |

Histogram, 5 s bins — **55.6 % under 5 s, 97.25 % under 10 s**:

```
 0–5   51,729  ████████████████████████████
 5–10  38,786  █████████████████████
10–15   1,016  ▌
15–30     719
30–35     577  ▎
35–75     183
75–85       4   <-- MAS's model predicts the MEAN lives here
85–100     22
100–105    42  ▏  <-- the only spike, and it is OURS (total_timeout)
≥105       18
```

**The 100 s spike is our own `total_timeout: 100000`** (`config.yml:118`), all 42
at HTTP 500, mean 100.46 s. Mechanism: attempt 1 hits MAS's 80 s `page_timeout`,
the retry leg starts, and our shared 100 s deadline cuts it.

`Page.goto: Timeout 80000ms exceeded.` fires **83 times in 93,076 requests
(0.089 %)**. Both fences together are **0.86 %** of total busy time.

**Queue wait is not hiding in this number.** `RenderGate ADMIT` logs it
explicitly: mean **0.036 s**, p50/p90/p95 all **0**, 98.47 % waited exactly zero,
mean `in_use` **1.154 / 2**. Ingress duration overstates render time by ~0.7 %.

---

## 2. Where the money actually goes

### The invoice (`tmp/azure-costs/`, uploaded by Tero 2026-08-14)

**The "Sponsored subscription, €0 cash" row in CLAUDE.md is WRONG and must be
struck.** The Cost Management API genuinely returns `rows: []` for this
subscription — an agent verified that is not a permissions artefact by running
the identical query against a different subscription, which returned records. But
the usage export has the data. **Sponsorship usage does not flow to Cost
Management; absence of records there is not absence of cost.**

Container Apps, €/day, deduplicated across three overlapping exports (the exports
share date ranges — summing them naively double-counts, which I did once):

| period | €/day |
|---|---|
| idle baseline, Jul 24 – Aug 7 | **€0.31 – 0.85** |
| Aug 8 – 9, ramp | €17.18 → €24.36 |
| **Aug 10 – 13, plateau** | **€78.79 – €92.58** |
| Aug 14, sweep ended midday | €32.68 |

The whole 18,374-company sweep: **€398.89**, i.e. **€0.0217/company**,
**€0.0032/page**.

**The €0.38/day baseline is not us** — it is `Standard Memory Idle Usage` at
~0.46 GiB continuous, which is MAS's `aitosoft-edge` at `minReplicas: 1`. Our
scale-to-zero works; crawl4ai costs **€0 when idle**. This is a sweep-shaped
cost, not standing infrastructure.

**Label the windows — this section originally mixed two.** €398.89 / 94.6 % is
**Aug 9–14**. The vCPU-second reconciliation below (8,893,189 vCPU-s ⇒ 1,235
replica-hours) and the "€1.02 of €374.54" idle figure are **Aug 10–14**; Aug 9–14
is 9,467,533 vCPU-s = 1,315 replica-hours.

**The dedupe key is over-specified and the attribution claim is inference.** Each
`ServiceResource` maps to exactly one `ResourceGuid` and there is exactly one row
per `(Date, ServiceResource)`, so `(Date, ServiceResource)` suffices (137
duplicate rows dropped). More importantly: **`ResourceGuid` is a *meter* id, not
a resource id — the export carries no per-app attribution at all.** So "the
€0.38/day baseline is `aitosoft-edge`" is an inference from the idle
memory:vCPU ratio being exactly 2:1, not a measurement. The real attribution
evidence is the replica-hour reconciliation below.

### The meter proves it is us, and validates our own instrument

**8,893,189 vCPU-seconds** billed at €0.000034/s. At 2 vCPU/replica that is
**1,235 replica-hours**. Independently, from Log Analytics replica counts:
**1,262 replica-hours**. **Within 2.1 %.**

That reconciliation is the most useful thing in this file: **our Log Analytics
replica accounting predicts the invoice**, so we can price a config change before
making it.

**And it holds day by day, not just in aggregate** — the review's strongest
check, and the reason every counterfactual here is money rather than modelling:

| day | `Replicas` PT1M | billed vCPU-s ÷ 2 | delta |
|---|---|---|---|
| 08-10 | 265.9 replica-h | 267.4 | −0.5 % |
| 08-11 | 303.5 | 305.4 | −0.6 % |
| 08-12 | 293.2 | 294.9 | −0.6 % |
| 08-13 | 255.4 | 259.8 | −1.7 % |

The residual is the right size for `aitosoft-edge`'s 0.25 vCPU.

Memory: 17,786,593 GiB-s — exactly 2.0× the vCPU-seconds, confirming the
enforced 1 vCPU : 2 GiB pairing.

**Idle usage was €1.02 of €374.54.** The ACA idle rate is *structurally*
unavailable to us: Microsoft requires `minReplicas > 0` **and** the revision to be
*at* the minimum, and states that above the minimum **all** running replicas bill
active. `minReplicas: 0` disqualifies us permanently. Stop treating idle rate as
a lever.

### Utilisation

| day | requests | mean replicas | concurrency | slots | **utilisation** | replica-h |
|---|---|---|---|---|---|---|
| 08-10 | 24,097 | 11.08 | 1.53 | 22.2 | 6.9 % | 266 |
| 08-11 | 28,133 | 12.65 | 1.80 | 25.3 | 7.1 % | 303 |
| 08-12 | 27,369 | 12.22 | 1.69 | 24.4 | 6.9 % | 293 |
| 08-13 | 24,310 | 10.64 | 1.50 | 21.3 | 7.0 % | 255 |

**7.0 % every single day** — a constant that exact is itself evidence the fleet
size is set by something proportional to load but unrelated to occupancy.

Instantaneous in-flight (true overlap sweep, 3 days, 259,200 samples): mean 1.58,
p95 **5**, p99 **7**, **max 13**.

CPU corroborates independently: 12.22 replicas × 0.325 vCPU measured =
**3.97 vCPU of real work against 24.4 provisioned — 16 %**.

---

## 3. Why the fleet is 12 when the documented formula says 1

Microsoft's documented ACA HTTP scaler:
`desiredReplicas = ceil(currentMetricValue / targetMetricValue)` where the metric
is *"requests in the past 15 seconds divided by 15"*. At 0.317 rps and
`concurrentRequests: 6` that is **1 replica**. To hold 12.2 the scaler's input
must read ≈ **73**.

Every request-based model was simulated second-by-second over three full days,
including the 300 s scale-down stabilization:

| model | mean fleet | observed |
|---|---|---|
| documented (reqs-in-15 s ÷ 15) | 1.0 | 11–12 |
| reqs in one second | 1.0–2 | 11–12 |
| reqs in 15 s, undivided | 2.1–2.25 | 11–12 |
| instantaneous in-flight | 1.8 | 11–12 |

**All refuted by 5–11×.** And MAS's traffic is *not bursty at the resolution that
would matter*: p90 is **2 requests/second**, max **7 in any single second of the
entire sweep**.

### The surviving hypothesis: connection count

**11.9 new connections/min held ~300 s ⇒ ~60 open ⇒ `ceil(60/6) = 10`**, against
observed 12.22. Reproduces out of sample on 08-10 and 08-13.

`ConnectionId` **is a TCP connection, not a per-request id** — proven three ways,
because the whole hypothesis dies if it is per-request:

1. **Distribution.** Requests-per-connection on 08-12: 12,178 connections carried
   1 request, 2,699 carried 2, … 1 carried 17. Rows sum to exactly 27,390
   requests over 17,208 connections. If it were per-request this table would be a
   single row reading `1 → 27,390`.
2. **One connection, two backends.** `ConnectionId 63389` served requests 9 s
   apart that landed on **different `ReplicaName`s** — Envoy round-robining a
   persistent downstream connection, impossible for a per-request id.
3. **The A/B separates on exactly this axis** (see below).

**Trap:** `ConnectionId` is unique only *per Envoy pod*, and there are 2. **Key on
`(EnvoyPodName, ConnectionId)`.** Keying on the id alone merged ids across pods
and inflated connection lifetime 3× (178.9 vs 57.0 modelled open connections).

### The 2026-08-08 A/B was confounded, and this is what with

| arm | requests | connections | **new conns/req** | replicas |
|---|---|---|---|---|
| uniform, **pooled** | 128 | **3** | **0.023** | **1** |
| bursty `--fanout 4` | 200 | 198 | **0.99** | **38** (trigger 2) |
| MAS sweep (`node`) | 123,601 | 79,823 | **0.646** | 12.2 |

`--fanout 4` forced four simultaneous requests, which httpx served on four
separate connections. **Burstiness and connection count co-varied perfectly.**
The uniform arm ran its entire 12 minutes on **three TCP connections**.

So CLAUDE.md's "the driver is burst shape" is **confounded, not established**, and
it does not transfer to the real sweep — which is not bursty at 1 s resolution.

Supporting, never documented and never denied: ACA maintainer `ahmelsayed`,
`microsoft/azure-container-apps#536`: *"Scaling http apps takes into account
**active connections as well as requests**."*

**What is still unproven:** no ACA metric exposes the scaler's input, so this is a
fit, not an observation. Connection *closes* are not logged, so the 300 s hold is
a fitted parameter.

### The downstream story contradicts itself, and the review caught it

Two claims in this section **cannot both be true**, and they differ by 75×. Mean
concurrently-open downstream connections as a function of the idle hold, measured
over 2 h of raw rows (08-12 10:00–12:00, 2,540 requests, 1,535 connections keyed
on `(EnvoyPodName, ConnectionId)`):

| idle hold | mean open | fleet = ceil(mean/6) |
|---|---|---|
| 0 s | 2.28 | 1 |
| **4 s** (undici's default) | **3.13** | **1** |
| 30 s | 8.66 | 2 |
| **300 s** (the fitted hold) | **64.88** | **11** |

**The fit needs ~300–390 s. But if MAS's client really expires at ~4 s, there are
3.1 open connections and the fleet is 1.** So the section used the 4 s reading to
justify the `keepAliveTimeout` ask while using the 300 s hold to justify the
mechanism. **Do not send that ask until this is resolved** — only one branch makes
it helpful.

Also retracted: **"reproduces out of sample on 08-10 and 08-13" discriminates
nothing.** New connections per request are 0.625–0.658 on *every* day (±3 %), so
a connection model with a 300 s hold is arithmetically the *same model* as a
request model with a ~194 s window. The strong evidence is the 2026-08-08 A/B
(10.7 req/min pooled → 1 replica vs 12 replicas at 19 req/min), not the daily
reproduction.

### The better hypothesis: it is OUR gunicorn, on the UPSTREAM leg

`supervisord.conf:23` runs gunicorn with **`--keep-alive 300`** (gunicorn's
default is **2**). A replica accepts at most `render_capacity 2 +
admission_queue 4` = **6 concurrent HTTP requests** (`config.yml:236-237`), so
Envoy needs at most **6 upstream connections per replica**, and at
`--keep-alive 300` they stay open.

**That makes the scaler's metric ≈ 6 × replicas, which is self-referential:**

| trigger | desired = ceil(6 × replicas / trigger) | behaviour |
|---|---|---|
| 2 | **3 × replicas** | runaway to the cap — **matches the observed 38** |
| **6 (today)** | **1 × replicas** | **neutral: the fleet keeps whatever size a burst gave it and never drains** |
| 12 | ½ × replicas | actively drains |

This explains three things the downstream story must call coincidences: the 300 s
constant (it *is* gunicorn's, not a fit), the trigger-2 ratchet-to-cap, and **why
slot utilisation was exactly 7.0 % on every single day** — at a neutral
equilibrium the fleet size is set by history, not by load. `6 × 12.2 = 73`, which
is exactly the metric value §3 needs; at trigger 2, `38 × 2 = 76`, the same
numerator.

**It is not proven either.** The point is that a second hypothesis fits the same
data with the same one free parameter, explains a constant the first must wave
at, and **its fix is ours** — one line, `--keep-alive`, no MAS coordination.

**§6 as designed cannot see it.** Both arms vary only *downstream* (client→Envoy)
reuse; Envoy's *upstream* pool is unaffected by how the client connects. So a
null result rules out downstream connections, **not connections**. Any re-run
needs a third arm varying `gunicorn --keep-alive`.

### Arm A, run 2026-08-14 — and it reproduced production

The botched-but-useful arm (httpx default 5 s expiry ⇒ effectively no pooling, at
MAS's exact shape: 19 req/min, fanout 4, ~5 s renders, `raw://`, zero egress):

**3 replicas at t=100 s → 6 at 366 s → 8 at 568 s → 11 at 973 s.**

**That is MAS's production plateau (11.81) reproduced synthetically, on a load
whose true concurrency is ~1.6 and for which the documented ACA formula predicts
1 replica.** Whatever the mechanism is, it is now reproducible in 16 minutes with
no third party involved — which is the single most useful thing to come out of
this file.

---

## 4. The over-provisioning manufactures its own load

This loop was not previously drawn and it ties four open items together:

```
autoscaler holds ~12 replicas
  -> each company's ~7 pages scatter round-robin across replicas
    -> the per-company browser signature misses the pool on each new replica
      -> 31,690 cold Chromium launches (~150 MB and ~0.9-3 s each)
        -> replica memory ratchets; guard reads 89.5 %
          -> memory guard refuses -> 429
            -> MAS retries -> more requests -> more connections -> more replicas
```

Measured: **7,550 distinct browser signatures, 31,690 launches — 4.2 launches per
signature**, pool miss rate **40.2 %** (31,690 misses vs 47,099 hits), stable at
32–48 % in every hour of 08-12.

**429 split, full sweep: 5,391 memory-guard refusals vs 48 RenderGate rejects
(99.1 %).** Mean guard reading at refusal **89.5 %**, mean resident **4.73/6** —
refused on percentage alone, never at the browser cap. This is
`tasks/memory-guard-charges-reclaimable-page-cache.md` confirmed at 13× the
original sample.

**Consolidating replicas attacks four of those five links at once.** That is the
argument for the cap that does not depend on the scaler mechanism at all.

---

## 5. The levers, priced against the real invoice

`maxReplicas` counterfactual from the per-minute `Replicas` metric on 08-12
(1,440 samples, mean 12.22, max 19):

| maxReplicas | replica-h | €/day | saving | mechanism-dependent? |
|---|---|---|---|---|
| 45 (before) | 293.2 | €88.68 | — | — |
| **20 (MAS's change today)** | **293.2** | **€88.68** | **€0.00** | — |
| 12 | 268.9 | €81.32 | €7 | no |
| 8 | 190.4 | €57.58 | **€29** | no |
| **6** | 143.8 | **€43.50** | **€44 (47 %)** | no |
| **4** | 96.0 | **€29.03** | **€50 (67 %)** | no |
| trigger 6 → 12 | — | ~€47 | ~50 % | no |
| **MAS fixes `keepAliveTimeout`** | — | **€80–84** | **85–90 %** | **yes** |

**MAS's 45 → 20 saves nothing** — replica-minutes above 20 across the entire
sweep: **0**; above 17: 0.2 %.

Capacity check for a cap of 6: 6 × (2 render + 4 queue) = **36 slots** against a
measured max in-flight of **13**. Cap 4 gives 24. Simulated across 3 days,
**0.000 % of seconds** would have queued at cap 8; 0.002 % at cap 6.

### The decision taken 2026-08-14 (Tero), REVISED after the second-opinion pass

**Raise the ACA scale trigger 6 → 12; leave `maxReplicas` at 20. Then ask MAS for
a bounded 30-minute sweep and measure it.**

The first decision was "cap `maxReplicas` at 4". **The review changed it, and the
reasoning is worth keeping** because the two options cost the same money:

| action | replica-h (08-12) | €/day | elastic? | ever tested? |
|---|---|---|---|---|
| today (trigger 6, cap 20) | 293.2 | €88.70 | yes | — |
| cap 6 | 143.8 | €43.51 | **no — at the cap 99.86 % of the day** | **never** |
| **trigger 12** | **146.6** | **€44.35** | **yes** | **yes** |
| cap 4 | 96.0 | €29.04 | **no** | **never** |

Four reasons the trigger wins at equal cost:

1. **It is the only one of the two ever run against production.** Trigger 2 → 6
   took the fleet **38 → 5** — a 7.6× reduction from a 3× change, super-
   proportional — at zero 429s. The cap has never been tested at all.
2. **Elasticity matters *because* this is an unattended multi-day run.** A cap of
   4 has no response to a surprise; trigger 12 still has 20 replicas behind it.
3. **The trigger is self-correcting under either mechanism.** If a smaller fleet
   lengthens requests, the metric rises and the fleet partially recovers. A cap
   cannot.
4. **A cap changes replica *lifetime*, and that is the untested part.** Measured
   over 08-11/08-12: **456 distinct replicas served `/crawl`**, median serving
   life **29.7 min**, mean 1 h 16 m, **122 requests each**. A cap of 6 pins the
   fleet at the cap 99.86 % of the day, turning 30-minute replicas into 3-day
   replicas **with no memory reset** — precisely the regime that produces 99.1 %
   of all our 429s, and which `autoscaler-ratchets-to-the-cap.md` already names
   as an open risk. Observationally reassuring but not decisive: memory-guard
   refusals per 1,000 requests are **flat (39–63)** across 4–16 replicas, but
   cap 6 puts per-replica load ~1.5× beyond anything measured and cap 4 ~2.2×.

**`maxReplicas` keeps a job — tail protection, not the lever.** 20 never binds
(0 replica-minutes above 19 on 08-12).

**And the cost the original table hid: the trigger 2 → 6 change cost p90 latency
+73 % (6.05 → 10.44 s).** Affordable against MAS's 210 s abort, but it is real,
it is measured, and "mechanism-dependent? no" should not have implied "free".

**The risk, stated honestly, is CPU and not capacity.** Slot arithmetic says cap 4
is safe (24 render+queue slots against a measured max in-flight of 13). The CPU
measurement above says something subtler: **a replica at `in_use=2/2` is already
oversubscribed ~2.4×**, and today that happens on **15.5 % of admits**. Capping to
4 does not change that ratio — it is fixed by `render_capacity: 2` against 2 vCPU
— but it **raises how often a replica sits at 2/2**. Expect p90/p99 latency to
rise; expect p50 to move much less.

Average-case arithmetic is comfortable: concurrency 1.58 × 2.4 = **3.8 cores of
demand against 8 available** at cap 4 (47 %). It is the p99 (in-flight 3.67 ⇒ 8.8
cores) that touches the ceiling, briefly.

**Per-replica queueing, which the aggregate-slot argument missed.** "6 × 6 = 36
slots vs max in-flight 13" assumes Envoy spreads perfectly; it round-robins per
request over variable-duration renders. The per-replica number was already in our
logs: **15,944 of 103,915 admissions (15.3 %) found `in_use=2/2`** at a fleet of
~12. Queueing needs two already in flight on the *same* replica, so halving the
fleet roughly quadruples the 1.54 % that wait at all (→ ~6 % at fleet 6, ~14 % at
fleet 4). Still short of a 429 — a 4-deep queue clears in ≤11 s at 2 slots × 5.4 s
against a 15 s limit — but the margin at fleet 4 is thin, **not the "0.002 % of
seconds" this file first claimed**.

**What to watch during the 30 minutes, in priority order:**

1. `RenderGate ADMIT waited=` — p50 and p99. Today p50 is **0**, 98.47 % wait
   exactly zero. Any sustained non-zero p50 means the cap is binding.
2. HTTP **429** rate, **split by mechanism** (`RenderGate REJECT` vs
   `refusing new browser`). These have opposite fixes; a rise in the first is the
   cap biting, a rise in the second is memory and is *expected* to worsen as
   pages concentrate on fewer replicas.
3. `RequestDuration` p50/p90/p99 against the baseline in §1 (5.39 / 6.82 / 29.48).
4. `anon` max per replica from the `📊 Pool:` line — the tail already touches
   94–97 % twice a day, and concentration pushes on exactly that.
5. **`OOMKilled` / exit 137.** This is the failure mode that matters, because it
   takes every in-flight render on the replica. Query it as
   `Reason_s == "OOMKilled"`, **not** by grepping `Log_s` — see §10.

**Abort rule:** ⛔ **the command this line carried until 2026-08-14 was the wrong
knob and would have read as a successful revert.** It said
`az containerapp update --max-replicas 20` — `maxReplicas` was *already* 20, so
that command is a no-op, and `maxReplicas` is not what changed. The change was
the scale **trigger**. This matters because the abort was written for an
unattended multi-day run: someone acting on it at 03:00 would have changed
nothing and believed the fleet was reverted. The real revert, and the only one:

```bash
az containerapp update -n crawl4ai-service -g aitosoft-prod \
  --scale-rule-name http-renders --scale-rule-type http \
  --scale-rule-http-concurrency 6
```

**Then edit `ACA_SCALE_TRIGGER` in `azure-deployment/deploy-image.sh` back to 6**
or the next deploy hard-fails its drift check (that is the check working).
Note it creates a new revision, so every replica restarts — that *is* the
memory reset, but it also drops every in-flight render.

**Trigger conditions, as amended by the 2026-08-14 readout:** any OOM kill
(`Reason_s == "OOMKilled"`) or exit 137 — unchanged and still the one that
matters. **The "429s above ~4.5 %" half did not survive contact:** the 30-minute
run finished at 6.5 % on our count / 7.46 % on MAS's and was *fine*, because
1.8 points of that is the capacity gate absorbed by their retry ladder and ~5
points is the memory guard, which was flat. Count the two gates separately —
`RenderGate REJECT` vs `refusing new browser` — and read only the first as a
capacity signal. A single number over both cannot be a threshold, which is
exactly what MAS told us in `45-…` §3.

### Rejected, with reasons

- **Raise `render_capacity` above 2.** Rejected on four independent grounds, and
  **the old supporting argument should be dropped** — `AITOSOFT_CHANGES.md:2134`
  is four lines of prose citing a `bench_capacity.py` that was never committed
  and does not exist in `git log --all`; it has no hardware statement, no request
  count, no absolute latencies, and its curve has **no knee at 2**. The memo
  (`capacity-scaling-memo-to-mas-2026-07-17.md:21`) says outright "matching your
  suggested number" — **the number came from MAS**. The durable reasons are:
  1. **CPU.** Newly measured from production telemetry (145 hourly bins,
     `UsageNanoCores`/`Replicas` joined to `sum(RequestDuration)/3600`):
     `fleet_cores = -0.13 + 2.45 × concurrency`, r² **0.738** ⇒ **~2.4 cores
     demanded per in-flight render, ~12 CPU-seconds per render**. Independently
     over the last 72 h: 0.335 cores/replica ⇒ 12.8 CPU-s/render. A 2 vCPU
     replica running 2 concurrent renders is **already oversubscribed ~2.4×**.
     R=4 or R=6 is oversubscribed under every fit. **The 16.5 % idle-CPU reading
     is a duty-cycle artefact, not headroom** — 22.6 slots serving 1.58
     concurrent is 7 % occupancy; *per render actually running*, demand exceeds
     the replica.
  2. **`max_pages: 5` caps it anyway, and it is two different things.**
     `crawler_pool.py:24` reads the key as *pages per browser*; **`server.py:91`
     reads it as a process-wide `asyncio.Semaphore` (`GLOBAL_SEM`) monkeypatched
     over `AsyncWebCrawler.arun` (`:156-159`)**. So `render_capacity > 5` is a
     no-op — the gate admits 6 and `arun` holds 5, and the excess waits **inside**
     the 180 s fence, which is the exact kynnos.fi failure mode RenderGate exists
     to prevent. (`aitosoft_patchright_fallback.py:272-280` already warns about
     this arithmetic.) Measured locally: raising `GLOBAL_SEM` to 64 gives **+87 %
     throughput at C=12**, so the apparent "knee at 4–6" is our own semaphore.
  3. **`max_browsers` cannot follow.** It is `3 × render_capacity` by
     construction (`config.yml:164-169`). R=4 ⇒ 12 browsers ⇒ ~5.2 GB on a 4 GiB
     replica at the measured ~434 MB/browser. Impossible.
  4. **It would not remove one replica.** The scaler never observes render
     occupancy — proven by the A/B where replicas went **38 → 5 from changing
     only the ACA trigger, with `render_capacity` fixed at 2**. Replicas required
     at R=2 for 3 days of real traffic: p50 1, p90 2, p99 2, max 7 — against
     11.31 actually run. **Replica-hours saved by raising it: zero.** What it
     would convert is **15 `RenderGate REJECT` in 3 days** (against 3,368
     memory-guard refusals) and 0.76 % of render-seconds in queue wait.

  **Falsifiers, so this can be re-opened honestly:** `RenderGate REJECT` becoming
  material (it is 0.02 %); `in_use=2/2` admits carrying the p90 latency (a 14.5 s
  wait against a 15 s budget did occur once); or MAS's fan-out rising so peak
  in-flight exceeds `2 × replicas`.

  **And the memory-guard fix is NOT a prerequisite for this** — it corrects a
  *reading* inflated ~14 points by active page cache; it supplies no anonymous
  memory. Ship it on its own merits (3,368 spurious 429s per 3 days) and its own
  risk (the 97.5 % `anon` excursion), not as a capacity enabler.
- **`minReplicas: 1` as a cost lever.** It raises the floor. RenderGate rejected
  48 requests in 124,843 — cold start is not a problem worth paying for. (It is
  still the right lever for cold-start 429s *if those ever matter*, which they
  currently do not.)
- **Right-sizing the container.** Refuted: the busiest replica exceeds 3.0 GiB in
  99 % of minutes, so 1.5 vCPU/3 GiB does not fit. **But CLAUDE.md's "2 vCPU /
  4 GiB is this environment's hard maximum" needs a caveat** — that is true of
  our legacy Consumption-only environment; a workload-profiles environment's
  *consumption* profile allows 4 vCPU / 8 GiB at identical rates. Migration means
  a new environment and a new ingress FQDN, not a new billing model.
- **Reducing render duration, as a cost lever *today*.** It saves €0 while
  replica count does not track occupancy. It becomes the lever that decides *how
  low the cap can go*, but only after the cap. See §8 — it is still worth doing,
  for a different reason.
- **Cheaper architecture.** ACA capped at 4 (€29/day) matches 6 PAYG D4as_v5 VMs
  (€30/day) with zero migration and keeps scale-to-zero, which matters because
  the sweep is ~17 % of the calendar. Azure Functions cannot run these
  containers; ACI has no autoscaling. **Reach for the cheap lever.**

---

## 6. The experiment that settles the mechanism — 20 minutes, zero egress

The data cannot separate "connections are in the scaler's metric" from "something
else with a ~300 s memory". This settles it and needs **no third party and no
MAS coordination**, because `raw://` is a full-fidelity load generator that still
launches a real Chromium (CLAUDE.md: `utils.py:354` returns early before DNS/SSRF
and `async_crawler_strategy.py:488` still routes it through the browser whenever
`needs_browser`, which `remove_consent_popups` sets).

> Two arms against `raw://`, **20 minutes each**, at MAS's exact measured shape —
> **19 requests/min, `delay_before_return_html` tuned to a ~5 s render,
> `--fanout 4`** — differing in **one variable only**: arm A uses a pooled client
> with keep-alive held open; arm B sends `Connection: close` so every request
> opens a fresh connection. Identical rate, identical burst shape, identical
> render time.
>
> **If arm B plateaus at ~10–12 replicas and arm A at ~1–2, connections are the
> metric.** If both plateau the same, connections are out and raising the trigger
> is the whole answer.

**20 minutes per arm matters:** the 2026-08-08 arms ran 9 minutes and the
trigger-6 arm was **still climbing** when it stopped, which is why its numbers
under-read.

### The trap that cost this experiment its first run — read before re-running

**httpx's default `keepalive_expiry` is 5.0 s** (verified by executing
`httpx.Limits().keepalive_expiry` on httpx 0.28.1, not by reading docs). At
19 req/min with `--fanout 4` the gap between arrivals is **12.63 s**. So every
pooled connection expired before the next tick and **the "pooled" arm was
silently a second copy of the no-keepalive arm.** It climbed to 6 replicas and
was on its way to being recorded as a control.

**A pool that expires between uses is not a pool** — and that is *precisely the
defect we are attributing to MAS's client*. Reproducing the bug inside the
instrument meant to measure it is the sharpest version of this repo's own
standing warning that a control sharing the suspected cause is not a control.

`sustained_rate_probe.py` now takes `--keepalive-expiry` (default 5.0, i.e.
httpx's own, deliberately left as the trap's value so the default is honest) and
sets `max_keepalive_connections` explicitly. **Both arms must set it.** The real
pooled arm needs a value above the arrival gap, e.g. `--keepalive-expiry 300`.

**Unexpected dividend:** the botched run is not wasted. It is a third arm —
"MAS's exact shape with an expiring pool" — and it produced a **growing fleet at
0.3 req/s**, which is the behaviour the hypothesis predicts and the behaviour MAS
exhibits.

---

## 7. What to send MAS

Their §1 invited attack on the derivation. Send:

- The distribution (§1) — it is what they asked for, and it refutes their
  headline cleanly: **4 requests of 93,076 in the 75–85 s band**.
- **Their arithmetic was fine; L in Little's Law is occupancy, not capacity.**
  Their replica count (10.6–12.7 vs measured 11.81), slot count (23 vs 23.62) and
  throughput (0.285 vs 0.3042 rps) were all correct.
- **`page_timeout: 80000` is theirs, not ours** — client-sent, and it is a
  *ceiling* on `page.goto`, not a dwell. It cannot add time to a page that loads.
  Their phrasing "your configured `page_timeout`" should be corrected. The only
  `80000` in this repo is inside an upstream example in the doc bundle we ship
  them, which is a plausible provenance.
- **Their `maxReplicas` 45 → 20 saves €0.** Peak was 19. Do not let them believe
  they have acted on cost.
- **The one ask that matters: `keepAliveTimeout`.** Their p50 connection span is
  5 s against ~7 pages per company — the pool expires between fetches. Send this
  **after** §6 confirms it, so it goes without a caveat.
- **Answer their §6 honestly: no, we do not cancel a render on client
  disconnect.** The slot, the browser page and the navigation run to the 180 s
  fence. At their 210 s abort against our ~200 s worst case it is rare today, but
  that is a 10-second margin, not a mechanism. **Size it for them: 7 `DC` + 7
  `SI` in 103,986 requests = 0.013 %.** And warn whoever fixes it that
  `request.is_disconnected()` **silently returns False forever** under our
  `@app.middleware("http")` stack (`starlette/middleware/base.py:110-127` — the
  `receive_or_disconnect` task group is a checkpoint inside an already-cancelled
  scope), so the obvious implementation ships as a no-op and passes any test that
  omits that middleware.
- **Their client is not in Azure, and nobody has said so out loud.** 100 % of
  `/crawl` is `UserAgent: node` over **HTTP/1.1 (zero h2)**, from
  `XForwardedFor` ∈ {the dev-container/home-ISP address in `PRIVATE.md` — 84,048
  requests; two others — 17,642 and 2,296}. **€399 of renders was driven from
  consumer broadband**, which means a full TLS handshake at ~25–30 ms RTT on
  65 % of requests and residential NAT idle timeouts sitting underneath any
  connection-lifetime story. That is a confound for the whole §3 analysis and
  possibly a lever of its own.
- Their §5b disclosure (real fan-out **7.0** pages/company, not 4) is confirmed
  from our side: 124,843 requests / 18,374 companies = **6.79**.

---

## 8. Render duration — worth doing, but not for the reason MAS thinks

Measured through `handle_crawl_request` against the local fixture origin, warm
pool, MAS's exact config:

| arm | `/ok` (1.5 KB) | `/heavy` (236 KB, 17 images) |
|---|---|---|
| MAS-exact (`delay 2.0`, consent on) | 3.27 s | **3.25 s** |
| `delay 0.1`, consent on | 1.29 s | 1.51 s |
| `delay 0.1`, consent **off** | 0.27 s | **0.33 s** |

So of the 5.39 s mean, **~3.25 s is ours and ~2.1 s is origin network time**, and
of our 3.25 s:

- **1.9 s is MAS's `delay_before_return_html: 2.0`** — their line, already
  scheduled for removal (their §5a).
- **1.0 s is two hardcoded 500 ms sleeps** — `remove_consent_popups.js:424` and
  `async_crawler_strategy.py:1716`. **Both were byte-identical to upstream**; the
  Python one we have already moved out of its `try` block, and it now also covers
  navigation detection, so **it is not a free deletion** — read
  `_report_consent_pass` before touching it.
- **MAS's suspicion #2 was the right suspect for the wrong reason.** The
  269-selector CMP scan costs **6.3–17.0 ms**, and scales linearly at ~3 µs
  /element (100,003 elements → 297 ms). It is the sleeps, not the scan.

**Why do it anyway:** shorter renders mean fewer overlapping requests, which
means fewer simultaneous connections, which — if §6 confirms the mechanism — is
the same lever as keep-alive. And it lowers the cap that §5 can safely reach.

### The consent flag's cost is measured and its output is byte-identical

2×2 on `/heavy`, all four arms **md5-identical markdown (22,011 B)**:

| | delay 2.0 | delay 0.0 |
|---|---|---|
| consent **on** | **3.252 s** (MAS's production shape) | 1.250 s |
| consent **off** | 2.232 s | **0.222 s** |

Across **all 8** consent fixture routes — including `/consent/banner` and
`/consent/named-root` — the flag produces md5-identical markdown while costing
~1.05 s. **Caveat that keeps this honest:** no fixture exercises a *named vendor
CMP container in a non-root position*, which is the one shape where the flag
would remove something. MAS's production measure of that population is **95
matched containers, 0 containing contact data**.

### A correction to CLAUDE.md that this file must carry

**`remove_consent_popups` does NOT force a browser for real traffic.**
`async_crawler_strategy.py:486` routes *every* `http(s)` URL to `_crawl_web`
unconditionally; `needs_browser` (`:490`) lives inside the `file://`/`raw://`
branch and never executes for http(s). CLAUDE.md's row is about the `raw://`
load generator and is correct *for `raw://`* — which is what makes §6's
experiment design valid — but it has been read one step too far at least twice,
including by this session.

**Static mode short-circuits at `api.py:764`, before RenderGate (`:832`) and
before the pool (`:847`.)** So a static request consumes no render slot, no
browser and no memory-guard budget. That is why static-first is a *capacity*
lever and not only a duration lever.

---

## 8b. The levers that are MAS's, ranked — and the biggest one is not in their message

| # | lever | owner | effect | cost |
|---|---|---|---|---|
| 1 | **7.0 → 5 pages per company** (their §5b: steady 6.9–7.1, and 75 % above the 4 every model in this repo used) | MAS | **~29 % of the entire bill** | one config number |
| 2 | drop `delay_before_return_html: 2.0` | MAS | 36 % of request duration | one line, already promised |
| 3 | drop `remove_consent_popups` | MAS | 19 % of request duration | one line, A/B first |
| 4 | **response projection** — `api.py:934` `model_dump()` strips nothing; MAS pre-approved dropping `fit_html` (~16 %) in `15-…`, and ~55 % of `links` bytes are six always-null fields | **us** | duration + replica memory + egress | one `.pop()` |

**Levers 1–3 are ~55–65 % of the bill between them, cost nothing, need no deploy,
and are all MAS's.** They understated lever 2 in their own message by 14× —
they priced their 2 s delay at "~2.5 % of the bill" against a true 5.39 s mean
where it is **36 % of the request**.

---

## 8c. Static-first: the answer is "not yet", and the reason is corpus, not principle

Measured through the real production path on the fixture origin:

| | static | full | ratio |
|---|---|---|---|
| CPU | **22 ms** | 228 ms | **10×** |
| RSS | 119–158 MB process | 651–684 MB tree | ~4.5× |

**Quote CPU, not wall time.** The 65× wall-time ratio first measured is a fixture
artefact — static tracks origin latency 1:1 while full adds a constant ~3.2 s.
Against real origins the honest figure is ~2.5×.

Static loses no contact data **on the pages we hold**: 13 → 14 contact emails
(it *gains* one the full pipeline dropped), 78–89 % of markdown length. Where it
fails: JS hydration (1 byte vs 1,259), JS challenge, and `unclosed-noscript`.

**Two things block it, and neither is "static is worse":**

1. **The corpus cannot support the claim.** It is **82 captures of 7 distinct
   URLs on 6 hosts** (the "140 captures" figure elsewhere is a file count), all
   full-mode, all post-render DOM — **neither repo stores pre-JS HTML for any
   page**, so the JS-dependent fraction is not estimable from what we hold.
2. **A live bug in static mode.** `_strip_hidden_decoys`
   (`aitosoft_static_mode.py:210-212`) `decompose()`s every `<noscript>`, so on
   an unclosed one it deletes the document — 174 raw bytes → `'\n'`, contact
   gone. Exactly the failure CLAUDE.md documents for the recovery path, in a
   second place.

**If it is ever built, the decision rule that routes the measured matrix
correctly:** static first, escalate to a browser **only if** `status is 2xx`
**and** `content-type is html` **and** `markdown < 500 chars`. The status and
content-type clauses are what stop it wasting a 13 s block retry. Overhead on
escalating pages is one httpx GET — 22 ms CPU.

**Owner: server-side, and it is not close.** MAS cannot see the HTML; a
client-side choice is a guess costing a full round trip to correct.
`CrawlerRunConfig.set_defaults()` (`async_configs.py:1329`) is the lever — it
bypasses the untrusted boundary by design and honours an explicit client value,
so MAS keeps `render_mode` as an override and we own the default. Contract
implication: `render_mode` in the response stops echoing their request.

**Also open: the `links` question.** Static hard-codes
`links: {internal: [], external: []}` (`:181`, `:358`), and **29.5 % of MAS's
non-homepage pages are reachable only from a deeper page's menu** (`13-…`).
Markdown-body links survive at ~79 % median, so this is degradation not deletion
— but it changes *which pages exist*, which is the sweep's only irreversible
output.

---

## 9. What must be fixed before anything deploys

**`azure-deployment/deploy-image.sh:115` declares `ACA_MAX_REPLICAS=45`; live is
20.** The invariant check `exit 1`s on drift **after `az containerapp update
--image` has already landed** — so the next deploy pushes an image and then
hard-fails. Reconcile the constant to whatever we settle on in §5, in the same
change.

Verified clean: revision `--0000041` (2026-08-14T14:31:17Z) changed **only**
`maxReplicas`. Same image, same env var names, token untouched.

---

## 10. What I am least sure of

- **The connection hypothesis is fitted, not observed.** It is the only surviving
  candidate of the right magnitude and it reproduces out of sample, but no ACA
  metric exposes the scaler's input. §6 exists because I do not want this in a
  cross-repo message without it. **If §6 refutes it, §5's caps still stand** —
  they are mechanism-independent, which is exactly why they should ship first.
- **The 300 s connection hold is a fitted parameter** and coincides with two
  different 300 s constants (`gunicorn --keep-alive` and the HPA stabilization
  window). I cannot separate them from observation and did not try to.
- **Zero OOM kills, but one unexplained restart.** Four rows carry
  `Reason_s == "OOMKilled"`; two say `exit code '0'` (impossible), and the two
  `137`s are byte-identical duplicates of one event on a container that had just
  restarted and never passed its startup probe. **However** `ncd79` served
  traffic normally at 12:30 and its container was re-created at 12:37:37 with no
  preceding termination event. 37 of 1,118 replicas (3.3 %) show an abnormal
  restart count. I am calling this "not an OOM" on good evidence and "not
  nothing" on weak evidence.
- **`Reason_s` is an unreliable label** and cost two sessions here: the word
  `OOM` appears only in `Reason_s`, never in `Log_s`, and the exit code is
  wrapped in single quotes (`exit code '137'`), so both obvious greps miss it.
  Same family as the `CONSENT STRUCTURAL` term-matching trap.
- **The cap simulation assumes the arrival process is unchanged when the fleet
  shrinks.** If replicas are fewer, connections concentrate, and I do not know
  whether the scaler's input then rises per replica. The experiment in §6 would
  show this; the cap is reversible in one command if it does not.
- **I did not measure whether MAS retried the 5,391 memory-guard 429s**, so an
  unknown share of the 124,843 requests is retry traffic we caused ourselves.
  Only their side can see that.

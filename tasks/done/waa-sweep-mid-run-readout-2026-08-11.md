# The WAA sweep at 39 hours: how we are actually handling the traffic

**Status:** readout, no action taken, nothing deployed
**Window:** 2026-08-09 14:19 UTC → 2026-08-11 05:44 UTC (39.4 h), still running
**Image:** `0.9.2-desc-cap`, revision `--0000040`, unchanged throughout
**Why this file exists:** the previous read (2026-08-10 ~06:00, 15.2 h in) is
recorded only inside `tasks/README.md`'s intro and
`tasks/memory-guard-charges-reclaimable-page-cache.md`. Tero asked where the
checks were documented; they were not, as a standalone artefact. This is the
39-hour read, and it **answers the re-measurement question the memory-guard file
ends with**.

---

## Headline

**The service is healthy and the load has doubled without us noticing it.**
Throughput went from 3,269 requests in the first 6 h to **6,823 in the last 6 h**.
Nothing degraded: p50 latency actually *fell* (5.14 s → 4.93 s), 504s stayed at
zero, and the replica high-water rose only 7 → 16 of 45.

The three things worth knowing are (1) the fleet is **~11× over-provisioned in
render slots** and that is the entire cost story, (2) **98 % of our 429s are the
memory guard, not capacity**, exactly as the open task file predicted, and (3)
the memory guard's *median* case is still over-cautious but its **tail has moved
in 39 hours** in a way the task file does not currently carry.

---

## Wire outcomes — what MAS actually received

`ContainerAppHTTPLogs`, `Path == "/crawl"`, whole window.

| | count | share |
|---|---|---|
| requests | **36,783** | — |
| 200 | 34,911 | 94.9 % |
| **429** | **1,521** | **4.1 %** |
| 500 | 249 | 0.68 % |
| 504 | **0** | 0 % |
| other 4xx | 5 | 0.01 % |
| no container ever saw it | 14 | 0.04 % |

Latency p50 **4.99 s**, p90 7.17 s, p99 29.68 s, max 245 s.
Egress **11.75 GB** total, p50 234 KB, p99 1.8 MB.

**Envoy anomaly flags are effectively zero**: 4 × `DC`, 2 × `SI`, 8 requests with
`UpstreamRequestAttemptCount > 1`, out of 36,783. The 30-day baseline is 0 and 1.
No raced upstream closes.

---

## The fleet, and the number that is easy to get wrong

**Average 8.34 replicas, p99 15, max 16 of 45** — measured as `dcount(ReplicaName)`
binned at **1 minute**, then aggregated.

The same query binned at 3 hours reports **25–40**, and that is churn, not
concurrency. CLAUDE.md already warns about this ("a `dcount` of replica names at
10-minute resolution reports churn as if it were concurrency") and I reproduced
it here at 3 h: 12 → 25 → 40 → 37. **Both numbers came out of my own session
before I applied the repo's own correction.** Bin at 1 minute.

| 3 h window | avg replicas | max | true concurrency | requests |
|---|---|---|---|---|
| Aug 09 15:00 | 5.4 | 10 | 1.07 | 1,827 |
| Aug 10 00:00 | 7.7 | 12 | 1.30 | 2,574 |
| Aug 10 09:00 | 10.4 | 15 | 1.79 | 3,526 |
| Aug 10 21:00 | 10.8 | 16 | 1.77 | 3,630 |
| Aug 11 03:00 | 11.1 | 15 | 1.67 | 3,332 |

True concurrency over the whole run — `sum(RequestDuration)/window`, the only
form that means anything — is **1.45**. Against 8.34 replicas × `render_capacity: 2`
that is **~16.7 render slots serving 1.45**. RenderGate confirms it from the
inside: every live `ADMIT` line reads `waited=0.0s in_use=1/2 queued=0`.

**The autoscaler is not the problem.** It is doing what its trigger says on
bursty traffic, it never approached `maxReplicas: 45`, and the 2026-08-08 trigger
change is holding. The over-provisioning is inherent to scaling on request rate
when the work is bursty and short.

---

## The 429s: 98 % are the memory guard, and the diagnosis holds

| mechanism | count |
|---|---|
| `RenderGate REJECT` (concurrency) | **27** |
| `refusing new browser` (pool memory guard) | **~1,497** |
| ingress total | 1,521 |

RenderGate's 27 are almost all in the first 6 h (16, then 9, then ~0/bin) — the
cold-start population CLAUDE.md describes. **After hour 12 it has rejected 2
requests in 27 hours.** Concurrency is a solved problem at this load.

`tasks/memory-guard-charges-reclaimable-page-cache.md` ends by telling whoever
picks it up to re-run the refusal decomposition first, and gives the decision
rule. **Re-run, over all ~1,497 refusals, in 6 h bins:**

| 6 h bin | refusals | guard read | median `anon` | active file charged in | `anon` ≥ 85 % |
|---|---|---|---|---|---|
| Aug 09 12 | 68 | 88.9 % | 68.5 % | 651 MB | 0 |
| Aug 09 18 | 114 | 88.7 % | 69.1 % | 614 MB | 2 |
| Aug 10 00 | 238 | 88.4 % | 68.4 % | 560 MB | 2 |
| Aug 10 06 | 211 | 88.9 % | 68.0 % | 623 MB | 0 |
| Aug 10 12 | 251 | 88.9 % | 67.9 % | 604 MB | 1 |
| Aug 10 18 | 329 | 88.6 % | 68.7 % | 570 MB | 2 |
| Aug 11 00 | 286 | 89.4 % | 69.0 % | 608 MB | 5 |

**Median `anon` at refusal is 67.9–69.1 % in every bin while the guard reads
88.4–89.4 %.** That is the file's own "diagnosis holds" branch, on 3.5× the
events and 2.6× the window of the original measurement. Twelve of ~1,497
refusals (0.8 %) had `anon` itself ≥ 85 %.

A live pool line, taken while writing this:
`hot=2, cold=3, resident=5/6, mem=88.8%, anon=2462MB file=519MB inactive_file=8MB`
— refusing at a true anonymous load of **60 %**, with 511 MB of *active*,
reclaimable page cache charged into the reading.

### What the task file does not carry: the tail has moved

Median `anon` from the pool-stats line is **flat** across the whole run — 60.5,
60.3, 61.4, 60.5, 60.6, 62.4, 62.1 %. There is no leak.

But the unbiased statistics moved:

| 6 h bin | max `anon` | p99 `anon` |
|---|---|---|
| Aug 09 12 | 81.2 % | 76.7 % |
| Aug 09 18 | 94.9 % | 81.0 % |
| Aug 10 06 | 83.1 % | 75.5 % |
| Aug 10 18 | 95.9 % | 80.1 % |
| **Aug 11 00** | **97.5 %** | **83.1 %** |

97.5 % of 4 GiB is 3,993 MB of anonymous memory. **`max` and event counts are the
unbiased statistics here** (the janitor's sampling interval is itself a function
of memory, so p50/p95 oversample high states ~6×; p99 inherits some of that bias
and should be read as directional, not absolute).

**This does not refute the file — it bounds the fix.** "There is ~1.25 GB of
headroom" is true at the median and false at the tail. Anyone relaxing the guard
onto `anon` must pick a threshold that survives a 97.5 % excursion, not the 69 %
median. Trading 1,500 cheap 429s for one OOM kill would be a bad trade: a 429
costs 113 ms and a client retry; an OOM kill costs every in-flight render on that
replica.

Still zero OOM kills, zero exit 137, and the `crawl4ai-memory-high` alert has
never fired (`monitorCondition: null`). `max_hot` never exceeded 6 and
`max_resident` never exceeded 6/6 — `max_browsers: 6` is holding.

**Recommendation unchanged: do not ship into the running sweep.** The file's own
timing argument is still correct and MAS's objection to a mid-run revision
transition is still the stronger one.

---

## Failure classes

Counted on `failure_class=`, not on the log token (CLAUDE.md's rule; the token
undercounts by 57 %).

| class | events | notes |
|---|---|---|
| `render_error` | 248 | ours — see below |
| `origin_unreachable` | 139 | dead domains, mostly pre-admission, free |
| `origin_blocked` | 62 | **not IP decay — see below** |
| `origin_http_error` | 57 | **structurally an undercount; MAS's envelope count is the real one** |
| `unrenderable_content` | 2 | downloads |
| `render_defect` | 1 | one page lost in 39 h |

509 failure-class events against 249 HTTP 500s — most classes are deliberately
200 + `success:false`, as designed.

### `origin_blocked` is not IP-reputation decay

62 events, and the last 6 h bin (23) is ~4× the first — which looks alarming
until you look at the hosts. They are spread across **~40 distinct hosts, 1–3
events each**, and every host's first and last event are within the same minute
or two: `louisvuitton.com`, `cma-cgm.com`, `parker.com`, `dna.fi`,
`mehilainen.fi`, `regus.com`, `criver.com`, plus Finnish SMEs. **No host repeats
across days, no host accumulates.** That is per-company burst behaviour tracking
throughput (which doubled), not our egress address going stale.

The standing stop-rule is not met. Normalised, it is 0.25 % → 0.34 % of requests.

### `render_error` — 166 of 248 are the tier-3 structural inference

| error | events | hosts |
|---|---|---|
| `Structural: minimal_text` | 166 | 27 |
| `Near-empty content (39 bytes) with HTTP 200` | 36 | 8 |
| `Crawl attempt exceeded the 100000 ms fetch budget` | 25 | 9 |
| `page.content() did not return within 10s` | 14 | 4 |
| `net::ERR_INVALID_AUTH_CREDENTIALS` | 4 | 1 |
| `Page.evaluate: Target crashed` | 1 | 1 |

39 bytes is CLAUDE.md's "empty 200" signature — a genuinely empty origin, not our
bug (15 bytes would be a script deleting the root).

**The 174-byte PDF viewer shell is in this sweep and is costing us.** Hosts whose
`Structural: minimal_text` lines carry a median of exactly **174 bytes**:
`www.kierinniemi.fi` (8 lines), `www.kumera.com` (8), `www.lakeudenharjateras.fi`
(8), `ryhmakoti.fi` (4), `www.assets.signify.com` (4). That is CLAUDE.md's
documented inline-PDF path — real Chrome renders the PDF into a 174-byte shell,
tier-3 calls it blocked, it becomes `render_error` → **500** → MAS retries 3×,
and each attempt is 2 navigations. 8 detection lines per URL is exactly 4
attempts × 2 navigations. Roughly 36 URLs by suffix. **Not new, not gating, and
MAS is removing PDFs at dispatch** — recorded because it is now visible in
production traffic for the first time.

### Three counters are climbing, and one is new

| 6 h bin | fetch-budget exhausted | `page.content()` stall | `Target crashed` |
|---|---|---|---|
| Aug 09 12 | 4 | 0 | 0 |
| Aug 10 00 | 8 | 85 | 0 |
| Aug 10 12 | 16 | 4 | 0 |
| Aug 10 18 | 32 | 0 | 0 |
| **Aug 11 00** | **53** | **199** | **13** |

`Target crashed` had never appeared in this repo's production logs before. All 13
are **one host** — `www.magicad.com` — which is also serving a SiteGround captcha
interstitial (`/.well-known/sgcaptcha/?r=…`). A Chromium renderer crash on a
captcha page is a plausible single-host pathology, not a fleet signal, but it is
the one line item I would watch on the next tick.

The 500s got slower as a result: p50 for a 500 went from ~31 s to **97.8 s**,
p95 101.3 s — i.e. they are now dominated by requests riding the 100 s
`total_timeout` fetch budget to exhaustion, twice. Concentrated in a handful of
hosts: `www.steelmark.fi` (24), `www.ltm.com` (16), `cloudpermit.com` (22),
`www.nexeoplastics.com` (3). **A 500 here costs ~100 s of a render slot and MAS
retries it 3×.** At 249 500s that is ~7 render-hours, ~2 % of total render time.

---

## The consent counter, at 40× the population segment 2 had

| token | count |
|---|---|
| `CONSENT DECLINED` | **4,187** |
| — of which `structural=True` (root collision) | **48** |
| `CONSENT STRUCTURAL` (a *named* selector hitting a root) | **0** |
| `CONSENT NAVIGATION` | 25 |

**The 48 root collisions are the headline.** Those are `<html>` (28) and `<body>`
(20) elements that the 20 generic selectors matched and the structural guard
refused to remove. On the pre-2026-08-06 image every one of them would have
deleted the customer's page — 28 of them to a 15-byte capture at HTTP 500. That
is **48 pages in 39 hours**, across 4 hosts for `<html>` and 3 for `<body>`, with
median removed-content sizes of 3,104 and 2,886 chars. This is the strongest
production evidence yet for the upstream PR (`tasks/file-upstream-prs.md`, fifth
candidate) and it argues the root collision, not banner data — exactly as
CLAUDE.md says to argue it.

`CONSENT STRUCTURAL` is **0**, so the 120-named-selector census still holds.

**A measurement trap, cost me two queries:** `Log_s has "CONSENT STRUCTURAL"`
**and** `Log_s contains "CONSENT STRUCTURAL"` both returned **53** — matching
`CONSENT DECLINED … structural=True/False` lines, because KQL treated the
two-word needle as a term-AND rather than a phrase. `matches regex` returns the
correct **0**. **Use `matches regex` for any multi-word token in
`ContainerAppConsoleLogs_CL`.** I reported 53 as a finding to myself before
catching it.

Breakdown of the 4,139 `structural=False` declines by node type:

| node | n | hosts | median chars |
|---|---|---|---|
| `script` | 2,004 | 298 | 1,893 |
| `div` | 1,801 | 327 | 291 |
| `style` | 171 | 25 | 19,291 |
| `link` | 73 | 11 | 0 |
| other (`a`, `h2`, `h3`, `p`, `aside`, `section`) | ~90 | — | ≤ 452 |

**Over half the generic-selector matches are `<script>` and `<style>` nodes** —
removing them was never going to help and never going to hurt. The genuine banner
population is the 1,801 `div`s at a median of 291 chars. This is the first time
we have had the population sized at this resolution; segment 2 had 27 events
total.

`CONSENT NAVIGATION`: 25, of which ~20 are WordPress Cookie Notice reloading the
same URL with `?cn-reloaded=1` — **benign, same page**. CLAUDE.md says to strip
the fragment before comparing; **it should also strip `?cn-reloaded=1`**, or this
counter will read as ~20× worse than it is. At least one is a genuine
wrong-page delivery:
`requested=autourheilu.fi/akk/akk-sports-oy/neste-ralli/ before=rallyfinland.fi/
after=sectorallyfinland.fi/` — a cross-domain click navigation. That is the known
unfixed click channel, firing on real traffic, at roughly its predicted rate.

---

## Collapse guard

16 `COLLAPSE RECOVERED`, 1 `RENDER DEFECT`, 0 `WALL-CLOCK FENCE`, 0
`Janitor reaped` in 39 hours. **One page lost out of 36,783 requests.**

---

## Payload size — the `desc` cap is holding

| | |
|---|---|
| max response | **31.1 MB** |
| > 10 MB | 4 |
| > 5 MB | 12 |
| > 1 MB | 1,602 |
| p50 / p99 | 234 KB / 1.8 MB |

Against the **232 MB** that deterministically lost `www.thermokon.fi` before the
cap, this is fine. But 31.1 MB is **4.5× the 6.9 MB high-water** the 15-hour read
recorded, and all 4 responses over 10 MB returned HTTP 200 in 8–47 s, so nothing
flagged them. The cap bounds `desc`; it does not bound `alt` copied per srcset
variant, and it does not bound `media.tables` at all (CLAUDE.md's unvalidated
`colspan`). **Nothing here is failing** — recorded because payload size is a
failure mode with no instrument but `BytesSent`, and the high-water is moving.

---

## Churn, and one mechanism worth knowing about

588 `ContainerCreated` / `ContainerStarted`, 298 `ImagePulled`, 277
`StoppingContainer`, 388 `SuccessfulRescale`, 38 `TriggeredScaleUp`, 30
`ScaleDown` — for an average of 8.34 replicas over 39 h. The fleet is
continuously churning.

- **755 × `ReplicaUnhealthy`** — every sample is `Readiness probe failed … connect:
  connection refused` or `Startup probe failed …`, i.e. a replica that has not
  finished booting. 755 / 588 starts ≈ 1.3 per cold start. **Cold-start noise, not
  a health problem.** Do not read this as 755 unhealthy replicas.
- **739 × `killing 'gunicorn' (9) with SIGKILL`** on the scale-down path.
  supervisord's `stopwaitsecs` elapses and gunicorn is killed rather than exiting
  cleanly, so **any render still in flight when a replica scales down is killed**.
  Observable impact in this window is ~6 requests (4 `DC` + 2 `SI` at the ingress)
  out of 36,783 — ACA drains connections first and it mostly works. Worth knowing
  because the impact scales with concurrency and this run's concurrency is 1.45.

---

## Cost

The subscription is **Sponsored**, so cash cost is **€0** and no usage record is
emitted — which is why Tero cannot see this in the partner report. Computed from
replica-minutes instead:

| | |
|---|---|
| replica-hours | **316** |
| vCPU-seconds | 2,277,120 |
| GiB-seconds | 4,554,240 |
| **at ACA list price (active rate)** | **≈ $68** |
| ACA monthly free grant (180k vCPU-s) | **12.7× consumed** |

Extrapolating: at the 15-hour read the ratio was ~7.2 requests per company, so
36,783 requests ≈ **5,100 of ~16,600 companies**. At the current rate (~1,140
requests/h and rising) the sweep has **~3 more days** to run, for a total of
roughly **$215 at list price, €0 cash, ~46× the monthly free grant**.

**The honest framing: ~90 % of that is over-provisioning, not work.** 1.45
concurrent renders needs ~1 replica; we averaged 8.34. The lever is the ACA scale
trigger (currently 6) or `maxReplicas`, and **neither is worth touching mid-sweep
for €0 of cash cost.**

---

## What I did not do, and what I am least sure of

- **No changes, no deploys, no restarts.** Nothing met an intervention threshold.
- **I did not verify the swap assumption** the memory-guard fix depends on
  (`/sys/fs/cgroup/memory.swap.max` on a live replica). That check is still the
  first thing that file's option (a) needs, and 39 more hours of data does not
  substitute for it.
- **The company-count extrapolation is ours, not MAS's.** It rides on a
  requests-per-company ratio measured on a different cohort 24 h ago. MAS's own
  counter is the instrument; ours is a proxy. Do not quote ~5,100 companies to
  them as if we measured it.
- **`origin_http_error: 57` is structurally incomplete.** We cannot count a 404
  that renders a normal body at all. MAS's envelope-side `status_code >= 400`
  count is the only complete instrument and last time it ran 13× ours.
- **The `Target crashed` cluster is 13 events on one host in one bin.** I am
  calling it a single-host pathology on weak evidence. If it appears on a second
  host next tick, it is something else and this call was wrong.
- **Whether the tail rise in `anon` continues.** Three of the seven bins show
  max ≥ 94 % and the highest is the most recent. If it keeps climbing the
  memory-guard file's framing shifts from "over-cautious guard" to "guard is
  load-bearing", which is a different investigation.

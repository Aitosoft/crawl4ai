# The memory guard refuses browsers on cache it would never OOM on

**Status:** open, not gating, **do not ship mid-sweep** (see "Timing"), and
**do not ship option (a) alone — read the last section first** (2026-08-14: the
fleet is now 2 replicas and peak `anon` is 0.65 points under the threshold).
**Size:** S in code, M in review — it is a change to a safety guard, and the
guard is the thing standing between us and an OOM kill on a 4 GiB replica.
**Found:** 2026-08-10, reading the overnight WAA sweep out of Log Analytics.
**Re-opens:** the 2026-08-09 correction #3 in `tasks/README.md`, which said
*"do nothing to behaviour, fix the instrument. Re-open only if the guard's own
reading crosses 85, or an OOM appears."* **It crossed 85 — 420 times in 15 hours.**
No OOM appeared. That correction called the mechanism correctly a day before it
fired; this file is the measurement it asked for.

---

## What happened

MAS ran their first sustained sweep — 1,471 companies in 15.2 hours, still
running when this was written. Our side served **10,537 `/crawl` requests** and
returned **434 × HTTP 429**. Every previous workload had returned 0–3.

The 429s are **not** capacity. RenderGate — the actual concurrency gate —
rejected **25**. The other ~409 are `crawler_pool`'s memory guard refusing to
open a new browser.

True concurrency across the whole run was **1.3** against a fleet ceiling of
~26 render slots. We were nowhere near busy. We were, by our own reading, nearly
out of memory. Only one of those two things was true.

---

## The finding

**At refusal time, 99 % of refusals fired on a reading inflated by reclaimable
page cache.**

Measured over all 420 refusal events in the window:

| | median at refusal |
|---|---|
| What the guard read | **88.7 %** |
| Anonymous memory (`anon`) | **2,810 MB = 68.6 %** |
| Active file cache charged into the reading | **583 MB** |
| Refusals where `anon` itself was ≥ 85 % | **4 of 420** |

`get_container_memory_percent` (`deploy/docker/utils.py:457`, ours — 74 lines
over upstream) reports a **working set**: `memory.current` minus `inactive_file`.
That is the standard definition and the docstring defends it well. But it sizes
the correction from the wrong workload — it says *"on a warm container
`inactive_file` was 1 % of pool growth and on a cold one 16 %… a bounded offset"*.

Under 15 hours of sustained crawling the page cache does not sit in
`inactive_file`. It is **active** — recently touched, still reclaimable, never a
cause of OOM on a cgroup with no swap. We subtract the 104 MB that is inactive
and charge ourselves the 583 MB that is active.

So the guard refuses a browser at a true anonymous-memory load of ~69 %, with
~1.25 GB of genuine headroom, and converts that into a 429 the client retries.

This is the same number the 2026-08-09 correction reached from a different
window and a different query (it said ~566 MB; this run says 583 MB). **Two
instruments, independently, same figure** — which is the only reason it is
stated this confidently.

---

## Evidence, with enough detail to re-run it

Log Analytics workspace ID is in `PRIVATE.md`. **The console table is
`ContainerAppConsoleLogs_CL`** (with the `_CL`; the unsuffixed name exists, is
empty, and returns no error — it silently answers "zero" to every question).
`ContainerAppHTTPLogs` has **no** suffix and its columns are unsuffixed strings
needing `toint()` / `todouble()`. Both traps cost time on 2026-08-10.

**The run:** `TimeGenerated > datetime(2026-08-09T14:19:00Z)`.

```kusto
// The refusal decomposition — the load-bearing measurement in this file
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "crawl4ai-service" and TimeGenerated > datetime(2026-08-09T14:19:00Z)
| where Log_s has "refusing new browser"
| extend pct  = todouble(extract("Memory pressure: ([0-9.]+)%",1,Log_s)),
         anon = todouble(extract("anon=([0-9]+)MB",1,Log_s)),
         file = todouble(extract("file=([0-9]+)MB",1,Log_s)),
         inact= todouble(extract("inactive_file=([0-9]+)MB",1,Log_s))
| extend anon_pct = anon/4096*100
| summarize refusals=count(), med_pct=percentile(pct,50),
    med_anon_pct=percentile(anon_pct,50),
    med_active_file=percentile(file-inact,50),
    n_anon_over85=countif(anon_pct>=85)
```

**Wire outcomes** (`ContainerAppHTTPLogs`, `Path == "/crawl"`): 10,537 requests →
9,981 × 200 (94.7 %), **434 × 429** (4.1 %), 118 × 500 (1.1 %), **0 × 504**,
4 × 4xx. Latency p50 5.1 s / p90 7.53 s / p99 30.89 s / max 151.3 s.

**429 reconciliation** — 25 `RenderGate REJECT` + 412 `refusing new browser`
(3-hour bins: 8, 60, 26, 88, 105, 125) = 437 against 434 at the ingress. The
gap is window edges. **Count events, not lines** — this family does not
multi-line the way `DNS: host does not resolve` does, but check before trusting
a `countif` on any new token.

**Memory across workloads**, from the `mem=` field of the pool-stats line:

| run | p50 | p95 | max | refusals | evictions |
|---|---|---|---|---|---|
| segment 5, Aug 8 11–15 UTC | 9.6 % | 49.9 % | 63.9 % | **0** | 10 |
| batch 1, Aug 9 08:54–10:40 | 47.1 % | 70.7 % | 86.7 % | **0** | 98 |
| overnight, first 6 h | 74.8 % | 91.3 % | 99.9 % | **80** | 147 |
| overnight, last 5 h | 79.2 % | 92.8 % | 100 % | **228** | 352 |

**Read the p50/p95 column with the bias in mind, and do not quote it as a load
figure.** The janitor's sampling interval is itself a function of memory (10 s
above 80 %, 30 s above 60 %, 60 s otherwise), so high-memory states are
oversampled ~6×. The 2026-08-09 correction measured that overstatement at 5.3×
for time-above-X. **`max` is unbiased; the refusal *count* is unbiased** (it is
an event, not a sample); p50/p95 are not. The argument in this file rests only
on the unbiased two plus the ingress 429 count, which is a wholly separate
instrument.

**Per-browser cost.** Average `anon/resident` runs 460–590 MB. A naive slope
across resident counts 1→6 gives **~434 MB per browser with a ~156 MB
intercept** — and that intercept independently matches the `Memory usage:
Start: 146.0 MB` line the API logs per request, which is a good sign the fit is
not nonsense. Against the ~165 MB per browser our sizing assumed, that is
**~2.6×**. **This slope is still contaminated** — LRU eviction fires *on memory
pressure*, so high-memory samples systematically carry fewer browsers, which is
the exact "regress on a control loop and you measure the controller" trap
already recorded in CLAUDE.md. Direction of the bias is toward zero, so 434 MB
is if anything a floor. Do not build anything on the precise number.

**No harm was done, and this was checked rather than assumed:**

- **0** `OOMKilled`, **0** exit 137, 0 allocation failures, across 10,537 requests.
- The **248 `ReplicaUnhealthy`** events are all `Startup probe failed: … connection
  refused` — containers that had not finished booting, against 194 scale-up
  starts. Not running replicas dying. (I reported this as churn worth watching
  before checking the reason string; it is not.)
- The 118 × 500 are **not** memory. `render_error` per 3 h ran 37, 36, 20, 4, 17
  — *falling* while refusals rose 88 → 105 → 125. They are the tier-3 inference
  class of `done/inference-tier-500s-are-not-retryable.md`, closed unfixed on
  MAS's request.
- **0** `RENDER DEFECT`, 5 `COLLAPSE RECOVERED`, 40 `Near-empty content`.
- Consent guard: 1,173 `CONSENT DECLINED`, **14** `structural=True` — 14 pages
  that would have been 15-byte captures at HTTP 500 on the pre-2026-08-06 image.
- The `desc` cap holds: largest response all night **6.9 MB** against the 232 MB
  that lost `www.thermokon.fi`. 3.35 GB total egress over 10,498 requests.
- `origin_blocked` per 3 h: 5, 1, 5, 2, 2 — **flat**. No IP-reputation decay,
  which is the standing stop-rule for the sweep. MAS's independent per-hour
  count (3, 3, 3, 0, 3, 2 per ~110 companies) agrees.

---

## Why this run and not the four before it

**Not cohort size, and not per-replica load.** The 2026-08-09 correction proposed
that the 63.8 → 80.9 → 86.7 % trend tracked **admits per replica** (9.1 → 95 → 97)
and was therefore our own ACA scale-trigger change. **This run refutes that.**
Overnight the median was **40 admits per replica** across 95 replicas — *less*
per-replica load than batch 1's 97 — with *higher* memory (p50 80 % vs 47 %). A
driver that moves the wrong way is not the driver.

**It is the diet, and MAS supplied the mechanism.** Their read, relayed
2026-08-10: this sweep re-visits companies already scraped once, so every host
is real, resolving and full of content — unlike the never-scraped pool, which is
substantially dead domains. Our side agrees from the other direction:
pre-admission DNS refusals fell from **4.2 % of requests in segment 5 to 1.2 %
overnight**. Fewer dead hosts, more real pages, and per-browser memory is a
**ratchet** — a browser's floor is the heaviest page it ever loaded, and only
closing it resets that (CLAUDE.md, `pool-browser-retains-last-page.md`).

**And the pool cannot amortise it, because MAS keys it per company.** The window
holds **1,127 distinct browser signatures** for ~1,471 companies, at ~9.3 admits
per signature — i.e. one browser per company, serving that company's page set,
then dead weight until the janitor takes it. MAS sends per-company browser
identity (`user_agent`, `viewport`, `headers`) and `user_agent` is part of the
pool signature. So this is not a cache that warms up; it is a conveyor belt.
**Expect the pressure to persist for the remaining ~15,100 companies**, which is
MAS's own prediction and the reason this is worth a file rather than a note.

---

## The design space

Ordered by how much I would trust each one today, not by effort.

**(a) Stop charging reclaimable page cache — the metric, not the behaviour.**
Subtract active file cache too, or read `anon` directly. This is what the
2026-08-09 correction already recommended, and this run's decomposition is the
evidence for it: it deletes ~99 % of the refusals without touching how many
browsers we hold or how much memory we actually use. It is also the only option
that makes the *reading* mean what every reader of it already believes it means.
**The risk is real and must not be waved off:** the guard is what stands between
a 4 GiB replica and an OOM kill, and a metric that under-reports has a failure
mode (a dead replica mid-render) strictly worse than the one we have now (a 429
the client retries). Anything here needs the OOM margin argued explicitly, not
assumed — with no swap, `anon` is the unreclaimable term and it sat at 68.6 %.

**(b) Lower `max_browsers` 6 → 4.** This is what I recommended to Tero on the
morning of 2026-08-10, **and the config file already argues against it**:
`config.yml:171-177` says the memory argument for the cap is *"real but NOT
settled"* and, in terms, *"it is not the fix for the memory guard firing."* That
comment is right and I was wrong. The guard fires on a **percentage**, not on the
browser count — the refusal log shows `resident=4/6`, under the cap, refused
anyway. Lowering the cap would reduce steady-state memory and so reduce
crossings, but indirectly, while giving up the `6 = 3 × render_capacity` invariant
that keeps the *count* branch unreachable through `/crawl`. It treats the
symptom of a mis-scaled reading by holding fewer browsers than we can afford.
**Not recommended, recorded so it is not re-proposed.**

**(c) Raise `memory_threshold_percent` 85 → 90.** Cheapest possible edit, one
number. It buys ~5 points of a reading that is itself wrong by ~14, so it is a
partial fix to a mis-measurement — and it spends real OOM margin to do it. If (a)
is judged too risky to touch during this programme, this is the fallback, but it
should be taken knowing it is the worse version of the same idea.

**(d) Reclaim idle browsers sooner** (`idle_ttl_sec`, currently 300).
Given one browser per company, most resident browsers are finished companies
waiting out a TTL. Shortening it returns memory without changing any ceiling.
Attractive because it is behaviour-preserving in the safety sense — it cannot
cause an OOM. Weaker because it is a workaround for a reading that is wrong, and
because cold-launch cost lands on the unfenced part of the admission path.

**(e) Do nothing.** Entirely legitimate and it is the current decision. MAS
measured the cost at **1.53 % of capacity** (385 retries, 2,505 s of waiting
against 45 slot-hours) and their real-world cost is lower still, because retries
overlap other companies' work. Nothing is failing. A 429 with `Retry-After` is
the designed response to memory pressure, and it is being absorbed exactly as
intended. **If the sweep finishes and MAS never asks, (e) remains defensible** —
this file is not an argument that something must be built.

---

## What I talked myself out of

- **"The 429s mean we are overloaded."** They do not, and this was my first
  reading. Concurrency 1.3 against ~26 slots. Reporting a capacity problem here
  would have sent the next session at RenderGate, `render_capacity` or
  `maxReplicas`, none of which are involved.
- **"Replica churn is a symptom."** 248 `ReplicaUnhealthy` looked alarming until
  the reason string turned out to be a startup probe, and until the control came
  back: **16.5/h overnight against 28.5/h in segment 5**. Lower, not new. Same
  for the 78 gunicorn SIGKILLs — segment 5 had 34 in four hours; that is
  supervisord on scale-down.
- **"The `desc` cap deploy caused it."** The step change lands at the 14:31
  deploy boundary, which is suggestive and was my open question for half a day.
  It is mechanically backwards — the cap only truncates a string that was already
  built, so it can only lower retained memory — and the cohort explanation
  covers the whole effect. **I could not fully separate deploy from cohort from
  duration on this data**, and the honest resolution came from MAS's side, not
  ours. Recorded because "correlated with our last deploy" is exactly the shape
  that gets adopted as cause.
- **Chasing an OOM that has not happened.** Zero in 15 hours at a *true* 69 %.
  The margin is genuinely there.

---

## What I am least sure of

1. **Whether active file cache is as reclaimable as this file assumes.** The
   argument is standard for cgroup v2 with no swap — the kernel reclaims page
   cache, active and inactive, before it OOMs — but I have **not** verified our
   replica has no swap, and I have not tested reclaim under pressure. **That
   check is the first thing (a) needs**, and it is cheap: read
   `/sys/fs/cgroup/memory.swap.max` and `memory.stat` on a live replica via
   `az containerapp exec`. If swap exists the whole framing shifts.
2. **The ~434 MB per-browser slope.** Controller-contaminated, as above. It is
   good enough to say "much more than 165 MB" and not good enough to size a cap
   with — which is one more reason (b) is weak.
3. **Whether the guard should exist in this form at all.** It refuses on a
   *global* reading at the moment a *specific* allocation is requested, with no
   estimate of what that allocation costs. A browser costs ~434 MB; the guard
   does not know that and would refuse identically for a 5 MB one. Possibly the
   right shape is "refuse if `anon + expected_browser_cost > limit × margin`".
   I did not pursue it — it is a redesign, and (a) may make it moot.
4. **Whether any of this survives the sweep ending.** The pressure is a function
   of MAS's cohort. When they move back to never-scraped companies with many dead
   hosts, the diet lightens and this may return to zero on its own. **Re-measure
   before building**, on a comparable workload; a fix shipped against a workload
   that no longer exists is worse than nothing.

---

## Timing, and why it is not now

**Do not ship into the running sweep.** MAS's position, which I agree with and
which is better reasoned than my initial "waiting is defensible":

- The upside is ~1.5 % of their capacity, realistically less.
- The downside is a revision transition mid-run — two revisions holding replicas
  against a 100-core environment quota — into a sweep that took a rough day to
  stabilise and has now run cleanly all night.
- It breaks batch-to-batch comparability at the point it lands, which is exactly
  what made their throughput question hard to answer on 2026-08-09.
- Nothing is failing. This is a cost, not a risk.

**The one thing that would change that** is an OOM kill or a replica dying
mid-render. Neither has happened. If one does, the first suspect is **not** the
browser count — it is a single pathological page growing RSS *inside* an already
resident browser, which the guard cannot see at all because it only gates new
browser creation. `media.tables` multiplying cell text by an unvalidated
`colspan` (+91 MB RSS from 905 bytes of HTML, CLAUDE.md) is the known shape, and
at a 69 % baseline it has less room than it did at 45 %.

**Whoever picks this up:** re-run the refusal decomposition first. If the median
`anon` at refusal is still ~69 % while the guard reads ~89 %, the diagnosis
holds and the question is only which option to take. If `anon` has climbed toward
85 %, this file is wrong about the mechanism and you are looking at a real
memory problem — which is a different investigation, not a tuning exercise.

---

## Re-measured at 39 h (2026-08-11) — the diagnosis holds, the tail does not

Full readout: `tasks/done/waa-sweep-mid-run-readout-2026-08-11.md`. The
decomposition above was re-run over the whole sweep — **~1,497 refusals, 3.5× the
events and 2.6× the window** of the original measurement.

**Median `anon` at refusal is 67.9–69.1 % in every one of the seven 6 h bins,
while the guard reads 88.4–89.4 %.** Active file cache charged into the reading:
560–651 MB. `anon` ≥ 85 % in **12 of ~1,497** refusals (0.8 %). That is this
file's own "diagnosis holds" branch, and it now rests on three independent
windows rather than one.

The 429 split held too: **RenderGate 27, memory guard ~1,497**, and RenderGate has
rejected 2 requests in the last 27 hours. Still zero OOM kills, zero exit 137,
`crawl4ai-memory-high` never fired, `max_browsers: 6` never exceeded.

**What is new, and it bounds the fix rather than refuting it.** Median `anon`
from the pool-stats line is flat across the whole run (60.5 → 62.1 %) — no leak.
But the *unbiased* statistics moved:

| 6 h bin | max `anon` | p99 `anon` |
|---|---|---|
| Aug 09 12 | 81.2 % | 76.7 % |
| Aug 09 18 | 94.9 % | 81.0 % |
| Aug 10 18 | 95.9 % | 80.1 % |
| **Aug 11 00** | **97.5 %** | **83.1 %** |

97.5 % of 4 GiB is 3,993 MB of anonymous memory. **"There is ~1.25 GB of headroom"
is true at the median and false at the tail.** Any threshold that moves the guard
onto `anon` has to survive a 97.5 % excursion, not the 69 % median — otherwise we
trade ~1,500 cheap 429s (113 ms each, plus a client retry) for OOM kills that
each cost every in-flight render on the replica. That is a bad trade at this
concurrency.

Three of the seven bins show max ≥ 94 % and the highest is the most recent, so
**re-check the trend before designing a threshold**. If it keeps climbing, the
framing shifts from "over-cautious guard" to "the guard is load-bearing", which
is the different investigation this file's last paragraph anticipates.

Timing recommendation **unchanged**: do not ship into the running sweep. Nothing
is failing; this is still a cost, not a risk.

---

## Re-measured at 2 replicas (2026-08-14) — ⛔ the headroom argument does not survive, and option (a) now needs a companion

The ACA scale trigger went 6 → 12 that afternoon and the fleet dropped from ~12
replicas to **2**. The same workload now lands on a sixth of the machines. Full
context in `tasks/done/trigger-12-readout-2026-08-14.md` §4. **Read this section
before acting on anything above it — it changes the recommendation, not just the
numbers.**

237 `📊 Pool:` samples, MAS's 30-minute run, 16:28–17:00 UTC, two replicas:

| | guard's reading `mem=` | true `anon` |
|---|---|---|
| p05 | 73.8 % | 57.8 % |
| **p50** | **84.0 %** | **68.8 %** |
| p95 | 94.0 % | 75.2 % |
| **max** | **97.7 %** | **84.35 %** (3,455 MB of 4,096) |

**The diagnosis is confirmed harder than before.** 0 of 31 refusals had `anon`
≥ 85 %. Active file cache reached **999 MB**. And the sharpest form of the defect
is visible in two lines 3 seconds apart on one replica — `mem=75.6% anon=2941MB`
then `89.4% anon=2819MB`: **the reading moved 13.8 points while `anon` moved
−4 %.** So this is not "a reading ~14 points too high". It is that **the guard's
median reading sits on its own threshold and the noise on its input exceeds its
distance to the trip point.** Refusals are sampling noise.

**But §"The finding"'s headline — ~1.25 GB of genuine headroom — is now false at
this fleet size, and option (a) must not ship alone.** Peak `anon` is **3,455 MB
= 84.35 %**, i.e. **0.65 percentage points / 27 MB** below where a corrected guard
reading `anon` against the unchanged 85 % threshold would trip. It would have
deleted all 31 refusals — by a rounding error. Against that margin:
`render_capacity: 2` permits **two** browser launches in flight against one meter
reading, and one browser is 143–170 MB on ordinary pages and ~434 MB at the
production slope. Two launches is 868 MB against ~614 MB of margin.

**Three consequences.**

1. **Option (a) acquires a mandatory companion.** Either `max_browsers` 6 → 4
   (4 × ~665 MB observed-at-6-resident = 2,660 MB, comfortably bounded, and still
   2× `render_capacity` so the count branch stays unreachable through `/crawl`),
   or a threshold on `anon` set well below 85. **§"The design space" and
   `config.yml:171-177` both reject `max_browsers` — correctly, as a rival fix
   for the refusals, and neither evaluates it as a companion. That is the gap.**
2. **The blast radius grew ~6×.** An OOM kill used to remove 8 % of the fleet.
   It now removes **50 %**.
3. **What did *not* change: the refusal rate.** 49.1 per 1,000 requests, inside
   the 40–63 band measured across 4–16 replicas. MAS confirmed independently.
   Whatever drives refusals, it is per-request, not per-replica.

**And the long-lived-replica worry this file inherits is closed, in the good
direction.** Trigger 12 pins the fleet, so replicas now live the whole sweep —
but they already did: three replicas lived **40.3–42.6 h** during the 08-11 →
08-14 sweep, with `anon` p50 rising only 2,485 → 2,804 MB over 40 h and p95/max
flat. And browsers cannot ratchet, because **70 evictions in 32 minutes over 6
slots means each pool slot turns over about every 2.7 minutes**. Zero OOM kills,
ever.

**Unchanged and still first:** nobody has checked
`/sys/fs/cgroup/memory.swap.max` on a live replica. One `az containerapp exec`.
It has been this file's stated prerequisite since it was written.

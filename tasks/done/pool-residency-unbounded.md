# Nothing bounds how many browsers the pool holds

**Status:** **DEPLOYED 2026-08-02** as `0.9.2-pool-cap`, revision `--0000033`.
Tier 1 regression **4/4**, offline suite 247 green, `resident=2/6` confirmed in
production logs. Ships with `pool-browser-retains-last-page.md`, which the
building session **closed as refuted** — see below.

**This task is done.** What is NOT done and is now the live question: the resize
that was supposed to make the memory half of this moot **does not exist** (see
below), so the levers in this file are the only ones we hold.
**Priority:** was High as "the cause of the 9 × 500". **It is at most a
contributor** — the old arithmetic behind that claim was wrong, but the
replacement measurement is disputed too (see the box in §2). Still worth
shipping, for a reason that does not depend on memory at all: `browser_config`
cardinality.
**Effort:** M as predicted, but the design was the easy half; the measurements
rewrote the problem.
**Risk:** medium — admission path for every render. The no-wedge argument is in
"Why this cannot deadlock" and is pinned by four tests.
**Evidence:** this file. `waa-eval-2026-07-30-forensics.md` §11d and
`render-500-window-2026-07-31.md` are the *prior* record and are **wrong on the
load-bearing arithmetic**; corrections below.

---

## What the implementing session found wrong in this file

Four things, three of them load-bearing. CLAUDE.md principle 6, fifth session
running.

### 1. "8 browsers to do 2 renders' worth of work" — the 8 was never counted

The number came from **one** janitor line (`hot=5, cold=2` at 04:46:32) plus an
inferred permanent browser. That line is emitted at the *end* of the janitor
loop, **after** that iteration's closes, and only when `mem_pct > 60` — so pool
composition was only observable on the half of the data where it was already
high.

Measured properly this session, by replaying every `Creating new browser` /
`Closing …browser` event from Log Analytics and taking the cumulative sum per
replica (276 events, 04:40–05:40):

| replica | peak live browsers | at |
|---|---:|---|
| 5hbkd | **10** | 05:01:23 |
| btv4v | **9** | 04:46:43 |
| r7bt4 | 9 | 05:00:59 |
| qsrb2 | 8 | 04:52:02 |
| vd9z5 | 8 | 04:52:09 |

So the count was roughly right (9, not 8) and **the residency problem is real**.
That is the half of the diagnosis that survives.

### 2. "At 165 MB each that is the whole 4 GiB budget" — off by ~2.5×, and this kills the causal claim

9 browsers × 165 MB ≈ 1.5 GB on a 4 GiB replica. That is **~36 %**, not "the
whole budget". The arithmetic never closed and no file noticed.

Settled by regressing the memory reading on the browser count, over all 68
`📊 Pool:` lines of MAS's probe:

```
mem% = 59.3 + 2.65 × browsers          n = 68, r² = 0.216
```

| browsers | n | mean mem% | min | max |
|---:|---:|---:|---:|---:|
| 3 | 6 | 65.7 | 61.6 | 72.4 |
| 4 | 21 | 69.6 | 60.2 | 86.8 |
| 6 | 12 | 74.1 | 64.4 | 88.6 |
| 8 | 6 | 84.6 | 73.6 | 100.0 |

Three things follow, and they reframe the whole task:

- **A resident browser costs 2.65 % of the replica — ~109 MB.** That is *lower*
  than the offline figure, not higher.
- **The intercept is 59.3 %.** ~2.4 GB of a 4 GiB replica is baseline that no
  eviction policy can reach, and **it is not explained.** Boot was 8.2 %.
- **Browser count explains 22 % of the variance in the memory reading.** The
  same replica read 82.3 % holding 4 browsers and 73.6 % holding 8.

**Therefore: `max_browsers` would not have prevented the nine 500s, and will not
prevent the next ones.** The guard fires on the 59.3 % nobody has accounted for.
Anyone citing this task as "the observed cause of MAS's 9 × 500" — including
`tasks/README.md` before today — is citing a claim that measurement does not
support.

> **WITHDRAWN AS STATED — coordinator re-check, 2026-08-02.** The refutation of
> the *old* arithmetic (9 × 165 MB ≈ 36 %, not "the whole budget") stands and is
> the durable finding here. The *replacement* does not: the fit above has three
> independent problems, all biasing browsers downward, set out in
> `replica-memory-baseline-unexplained.md` §"Why the fit is not settled".
> Briefly — this file's own binned table regresses to **3.42 %/browser (140 MB)**,
> matching the offline instrument, not 2.65; the slope was fitted straight
> through a live control loop (the adaptive TTL closed browsers *because* memory
> was high, which is also why the 82.3 %-at-4 / 73.6 %-at-8 anecdote proves less
> than it appears to); and the 68 samples predate `13fcecb`, which changed what
> `get_container_memory_percent` measures.
>
> The supportable claim is **"the cap would have prevented some of the nine, and
> the fraction turns on a slope we have not settled"** — at the bottom of the
> 85.1–95.6 % range it clears the guard under both slopes. **Do not quote 59.3,
> 2.65 or 109 MB as settled.** The cap ships regardless: it is correct under
> every candidate slope, and its real justification is cardinality.

### 3. "The fixture page is a few hundred bytes, so the figure is a floor" — true, and it barely matters

`/ok` is 1,478 bytes with no images. The handover was right to be suspicious. It
was measured, by adding a `/heavy` route shaped like the median of our own 62
stored captures (236 KB, 17 images, ~900 tags — real numbers from
`test-aitosoft/artifacts/`, not intuition), and re-running the same instrument:

| route | cgroup / browser | anon / browser |
|---|---:|---:|
| `/ok` (the old figure) | +142.8 MB | +129.6 MB |
| `/heavy` (median real page) | +170.0 MB | +141.3 MB |

**+19 % cgroup, +9 % anon.** A pooled browser's cost is dominated by the
*Chromium process*, not by the page it is holding. The floor was a good floor.

The direction the handover feared turned out to be real anyway — but from the
production regression (109 MB), not from the page, and it points the other way.

### 4. "The adaptive TTL probably becomes redundant" — it is worse than redundant, and the reason is #2

It collapses `cold_ttl` to 30 s above 80 % memory: it closes browsers exactly
when memory is tight, so the next request for that signature must launch a fresh
one — allocating while allocation is the problem. 136 launches for a working set
of 10–12 signatures.

Given #2 it was **aimed at a term worth 22 % of the variance**, and it could
never relieve the 59.3 % it was reacting to. Removed: the poll *interval* stays
adaptive (cheap, useful), the TTLs are now constant. Pinned by
`test_memory_pressure_no_longer_collapses_the_idle_ttl`.

---

## Two things nobody had looked at, both of which change the design

### `browser_config` cardinality is *observed* small, not *bounded* small

The refutation this file carried — "243 hosts gave 10–12 signatures per replica,
so the 15,000-signature worry is unfounded" — is weaker than it reads. The query
behind it is a `dcount` **per replica** over `Creating new browser` lines; with
~5 replicas each seeing a fifth of the hosts, a per-replica count cannot bound
global cardinality. Nobody ran it without the `by ContainerGroupName_s`.

Structurally it probably *is* bounded: `test-aitosoft/reference/persona_generator.ts`
is a hardcoded 11-persona array that collapses to **10 distinct `browser_config`
payloads** (two personas differ only in a `name` field that never reaches the
wire), selected by `hash(companyId) mod totalWeight`. 15,000 companies index into
the same 10. But **we cannot show MAS runs that file** — it was committed once
and never touched, and the one verbatim MAS payload we hold
(`test_mas_contract.py:72`) is Chrome/138 with a different `sec-ch-ua` shape,
matching none of the 11.

**And there is a one-word unbounded vector.** `user_agent_mode` is in
`UNTRUSTED_FIELD_ALLOWLIST`, and `"random"` regenerates the UA on every
`BrowserConfig` construction — so every request would get a fresh signature and
the pool would become write-only, one Chromium launch per request. Our own
shipped client documentation (`deploy/docker/c4ai-doc-context.md:167`)
recommends it as an anti-bot measure. Nothing blocks it and no test catches it.

This is the strongest remaining argument for the cap: **it is correct under both
models**, and under the unbounded one it is the only thing standing between a
sweep and one browser launch per fetch.

### The permanent browser can never be used — and the recorded reason is wrong

`crawler_pool.py` and `test_crawler_pool.py` both attribute its 0 hits in 224
pool gets to "MAS always sends a `browser_config`". Measured:

```
boot sig (init_permanent)    : 5e3e8048e7be
request sig (enforce_egress) : b318c5753575
differing fields: {'ignore_https_errors': (True, False)}
```

`server.py:199` builds the permanent browser's config **without**
`enforce_egress`, while every request path applies it. So a request sending
`browser_config: {}` would miss too, as does every internal `/html`,
`/screenshot`, `/pdf` call. The permanent browser is unreachable **by
construction**, the lazy re-create branch in `get_crawler` is dead code in
production, and `_close_unused_permanent` will always fire. Left alone
deliberately — fixing it would *revive* a browser nothing wants — but the
comments are misleading and are corrected in place.

---

## What shipped

`pool.max_browsers` (default **6**) enforced in `get_crawler`, with LRU eviction
of *idle* browsers. `pool.evict_close_timeout_sec` (30) bounds the detached
close.

**How 6 was derived**, so it can be re-derived when the inputs move:

- guard fires at `memory_threshold_percent: 85`, baseline is 59.3 %, slope is
  2.65 %/browser → **9.7 browsers of headroom**;
- 6 puts the predicted mean at cap at **75.2 %**, ~10 points below the guard;
- 6 = **3 × `render_capacity`**, so eviction always has ≥ 3 idle candidates and
  the refusal branch is unreachable through `/crawl`;
- it is *below* the observed 10–12 signature working set, so it will cause extra
  launches. That cost is real and accepted: a launch is ~1–3 s on the unfenced
  part of the admission path.

Note what the cap does **not** bound: the patchright singleton
(`aitosoft_patchright_fallback.py`) is a whole extra Chromium that lives outside
`HOT_POOL`/`COLD_POOL`, is invisible to `get_pool_snapshot`, and is recycled by
use count only — never by memory or idle time. It is a strong candidate for part
of the unexplained 59.3 %.

### Why this cannot deadlock

The invariant is **`get_crawler` never waits.** Not "waits briefly" — never.

1. `release_crawler` takes the same `LOCK` to decrement `active_requests`. Any
   wait inside `get_crawler` while holding `LOCK` waits on code that needs the
   lock the waiter holds. Total pool death: no 504, no 429, and the janitor
   cannot recover it because it needs `LOCK` too.
2. Even releasing the lock to wait is wrong here. `get_crawler` sits in the
   **unfenced** gap between render admission and the 180 s wall-clock fence
   (`api.py` acquires the gate, gets a crawler, *then* starts the fence). Budget
   from there to Azure ingress's 240 s is ~40 s, and a browser launch can
   already take 30 s of it.
3. So eviction pops the victim under the lock and **closes it in a detached
   task** (`_close_detached`), bounded by `asyncio.wait_for`. `close()` carries
   no timeout of its own; a wedged Chromium closed inline would hold the pool
   lock indefinitely. `tasks/render-retry-unbounded-hang.md` paid for this once.
4. If nothing is idle, `get_crawler` **refuses** with `RenderCapacityExceeded` —
   the only exception `api.py` maps to 429 + `Retry-After`. A new exception type
   would land in the generic `except Exception` and become the 500 MAS retries
   three times, which is the regression `render-500-window-2026-07-31.md` exists
   to have removed.

Unreachable in MAS's traffic: the gate admits `render_capacity` (2) concurrent
renders holding one pool browser each, against a cap of 6.

Pinned by `test_crawler_pool.py`:
`test_a_wedged_close_cannot_wedge_the_pool` (close that never returns; the pool
still serves), `test_concurrent_arrivals_over_the_cap_refuse_instead_of_hanging`
(6 concurrent vs cap 3, slow launches, `wait_for` turns a hang into a failure),
`test_two_concurrent_renders_never_hit_the_cap_refusal` (40 arrivals through a
semaphore of 2 — zero refusals), `test_a_busy_browser_is_never_evicted`.

### Verified end to end, real Chromium, zero live requests

12 crawls with distinct `browser_config`s through `ProductionPath` against
`/heavy`. Browsers 1–6 grow the pool; from #7 every create evicts an LRU idle
browser and **the cgroup flatlines**:

```
browser #6   cgroup=5749.4   cold=6
browser #7   cgroup=5752.4   cold=6      ♻️ Evicting LRU idle browser (idle=11s)
...
browser #12  cgroup=5764.0   cold=6
```

+15 MB over six more browsers, against +168 MB each before the cap. Process
count flat at 43. Memory bounded by construction, which was the point.

---

## What the DEPLOYING session found wrong, 2026-08-02 (sixth in a row)

Both prescribed fixes were done, but **fix (a) could not be implemented as
written**, and the reason matters more than the fix.

### (a) "evict, re-read, then refuse" — the re-read cannot measure anything

`_close_detached` calls `asyncio.create_task`. A task created inside a coroutine
does not start until the creating coroutine yields, and there is **no `await`**
between the eviction and any re-read — so the close has made not "some" progress
but *zero*. Forcing it to start (`await asyncio.sleep(0)`) does not help either:
it immediately blocks on Playwright IO, Chromium exit plus kernel reclaim is
100 ms–seconds, and any sleep there sits inside `LOCK` on the unfenced admission
path — a direct breach of this file's own "never waits" invariant.

So the re-read branch could never fire, and the only way to make it fire is a
mock returning a different value the second time: a test of a scenario that
cannot occur.

**What shipped instead: evict one idle LRU browser, then refuse anyway.** The
shed is the point (it is what replaces the removed adaptive TTL); the refusal is
honest, because memory *is* over the limit at that instant. The reclaim lands
for the next arrival, which is exactly what the 429 + `Retry-After` schedules.

### A second defect in the same instruction, avoided by accident

Implementing (a) via the existing helper — `_evict_for_capacity(headroom=1)` —
would have been a **no-op in the common case**. Its loop is
`while resident_browsers() + headroom > MAX_BROWSERS`, so under memory pressure
with the pool *below* the cap it evicts nothing. It would have shipped green and
done nothing. Split out `_evict_lru_idle(reason)` instead, which also removed a
latent infinite loop in the old body (`LAST_USED.pop` then `continue` re-selects
the same key at `used=0.0`, spinning while holding `LOCK`).

### What fix (a) costs, stated plainly

It **re-arms a memory→browser-count feedback loop** — the same confound that
`replica-memory-baseline-unexplained.md` §2 uses to disqualify the 2026-07-31
slope, whose instruction was "fit on data drawn with the TTL loop gone (the
current build)". After this deploy the current build has a loop again. It is
narrower (fires only on refusals, not on a timer) and the eviction log line names
`memory pressure X%` so those samples can be filtered — but **a naive fit across
this build carries the same bias.** Filter on the reason, or measure offline.

Also fixed while there: the guard's `logger.error` evaluated `hot=`/`cold=`
*after* the eviction, so the one line pairing a memory reading with pool
composition reported one browser fewer than the pool held when the reading was
taken. Composition is now snapshotted before the shed.

Two claims in the comments were softened because they were overstated: "one, not
all" is **one per refusal, not per episode** (nine refusals in four minutes sheds
up to nine), and "idle-only" was never the difference from the adaptive TTL —
that skipped busy browsers too. The real differences are LRU order, that it
engages only while arrivals are being refused, and that a refusal never launches.

### The 120 s TTL, measured in production the same day — ~200 MB, ~5 points

The `:24`-phase janitor series on one replica of `--0000033`, **read correctly**:
this file's own caveat says `mem_pct` is sampled *before* the loop's sleep and
logged *after* the cleanup, so within a single line the percentage is up to 60 s
older than the breakdown beside it. Treat each `mem=` as belonging to the
**previous** tick and the series is coherent:

| mem sampled | reading | pool at that sample |
|---|---:|---|
| 12:00:24 (boot) | 13.3 % | permanent + 0 |
| 12:01:24 (Tier 1) | **22.1 %** | permanent + 1 |
| 12:02:24 (after close) | **17.1 %** | 1 browser |
| 12:03:24 | 17.0 % | 1 browser |

```
12:02:24  🧹 Closing permanent browser — never used in 120s
12:01:24  📊 permanent=yes, resident=2/6, anon=585MB
12:02:24  📊 permanent=no,  resident=1/6, anon=389MB
```

**−196 MB anon and −5.0 points, from deleting one line of config.** The two
instruments agree (5.0 % of 4096 MB = 205 MB ≈ the 196 MB anon drop), which is
also a nice cross-check that the reading tracks anon rather than page cache —
`file` barely moved (328 → 326 MB).

Two things worth carrying forward. **~196 MB is above the offline per-browser
figures** (129.6 MB `/ok`, 141.3 MB `/heavy` anon), so the offline instrument is
a floor on the real path, as suspected. And **a serving replica read 13–22 %, not
~65 %** — which does *not* refute the disputed intercept, because Tier 1 is four
sequential requests and the 68 disputed samples were a 243-host probe at
concurrency, but it does show the baseline is not a constant that "appears with
traffic". It needs *concurrent* traffic. That points at candidate 1 (in-render
transient memory) and away from candidates 3 and 4.

### Cheapest lever found and taken: `permanent_unused_ttl_sec` 600 → 120

Nobody had asked what the boot browser costs during a cold burst. It is
unreachable **by construction** (`server.py:199` builds its config inline without
`enforce_egress`; `get_default_browser_config():138` and every request path apply
it), confirmed by 0 hits in 224 production pool gets. At 600 s it held ~140 MB
through minutes 0–10 of a replica's life — precisely the window that produced all
nine of MAS's refusals (replica up 04:44:49, refusals 04:46–04:50). 120 s is a
one-number config change on exactly the failing path.

**Not the real fix, and deliberately not bundled:** whether that boot browser
should exist at all — delete the `init_permanent` call, or route it through
`get_default_browser_config()` to make it reachable — is a `server.py` change,
the two options point opposite ways, and it deserves its own attributable change.
This file previously considered only the second and declined it; **nobody had
proposed deleting it.**

## THE RESIZE IS NOT AVAILABLE — measured 2026-08-02, and it refutes both records

Tero approved the resize. Azure refused it:

```
$ az containerapp update -n crawl4ai-service -g aitosoft-prod --cpu 2.0 --memory 8.0Gi
ERROR: (ContainerAppInvalidResourceTotal) ... must add up to one of the following
CPU - Memory combinations: [0.25/0.5Gi] [0.5/1.0Gi] [0.75/1.5Gi] [1.0/2.0Gi]
[1.25/2.5Gi] [1.5/3.0Gi] [1.75/3.5Gi] [2.0/4.0Gi]
```

**The list ends at 2.0 vCPU / 4.0 GiB. We are already at the maximum size this
Container App can be.** Nothing changed — the command is atomic and sizing was
re-read as 2 vCPU / 4 GiB afterwards.

Two records are wrong, in opposite directions:

- `tasks/done/overnight-intervention-log-2026-04-14.md` recorded `--memory 8.0Gi`
  as "doubles headroom at zero cost (MS credits)". **That command does not exist
  as a valid operation.** The scope cut of 2026-08-02 was argued largely from it.
  The cut was still right — for its other reasons — but its headline example was
  never available.
- `tasks/README.md` guessed "4 vCPU / 8 GiB is the likely shape". Also
  unavailable: the environment is a **legacy Consumption-only** managed
  environment (`properties.workloadProfiles: null`), whose ceiling is 2/4. The
  4 vCPU / 8 GiB ceiling belongs to the *Consumption profile inside a
  workload-profiles environment*, which is a different environment type.

**The only path to more memory is converting the managed environment** to
workload profiles (`az containerapp env update -w <name> --workload-profile-type
...`, flag confirmed present). That is not a resize — it is a production
infrastructure migration with a different billing model, and it was not what was
approved. **Escalated to Tero, not done.**

Consequences that follow immediately:

- **Buying headroom is off the table, so the memory work is not moot.** The
  parked `replica-memory-baseline-unexplained.md` had "Tero declines the resize"
  as its un-park condition; the resize being *unavailable* is functionally that.
  Coordinator's call, but the condition is met.
- The cap, the shed-before-refuse guard and the 120 s permanent TTL are now the
  *only* memory levers we hold, rather than stopgaps until a resize.
- `render_capacity: 2` is fixed at 2 vCPU and stays 2. No scale-rule change, so
  `deploy-image.sh`'s invariant check is untouched. (Note it verifies **after**
  the image update — it is a post-hoc alarm, not a gate.)

## Before this deploys — two fixes, both small (coordinator, 2026-08-02)

Neither is a defect in what was built; both fall out of the review in
`replica-memory-baseline-unexplained.md` §"Why the fit is not settled", which
disputes the slope this file derived its numbers from.

**(a) The guard refuses before eviction can run, and the shed path is now gone.**
`get_crawler` checks `mem_pct >= MEM_LIMIT` and raises *before* reaching
`_evict_for_capacity`. Combined with removing the pressure-driven TTL, a replica
over 85 % now holds its idle browsers for the full constant `idle_ttl_sec: 300`
instead of shedding in ~30 s. Removing the adaptive TTL was right — it *thrashed*
— but nothing replaced its one useful behaviour.

Make the memory guard **evict idle LRU browsers, re-read, then refuse**. That is
the targeted version of what the TTL was attempting: same intent, LRU and
idle-only instead of a global TTL collapse, and no launch-while-tight loop. If
the slope is 2.65 %/browser this barely matters; if it is 3.42 % it is a real
regression on exactly the cold-burst path this work exists to fix. Cheap enough
that it is not worth settling the slope first.

**(b) Strip the disputed regression out of the `config.yml` comment.** The cap's
derivation there is written entirely in terms of `59.3 + 2.65 × browsers`, and a
future session will read that as settled fact — config comments are the most-read
and least-reviewed documentation we have. **The cap's real justification does not
need memory at all:** `user_agent_mode: "random"` is allowlisted and recommended
by our own client doc, and under it every request launches a browser. Lead with
that, keep 6 = 3 × `render_capacity` as the sizing rationale, and point at the
task file for the memory argument with its dispute attached.

## Still open, and now the more important question

**What is the 59.3 %?** It is ~2.4 GB of a 4 GiB replica, it appears with
traffic (boot is 8.2 %), it does not scale with resident browsers, and it is
what actually trips the guard. Candidates, none measured: transient per-render
memory (2 concurrent renders of real pages, plus our own lxml/markdown pipeline
over a 700 KB document); the patchright singleton; page cache the working-set
correction does not subtract (`active_file`).

This is now the highest-value open question about replica memory, and it is
worth more than the cap that was built. It has its own task file
(`replica-memory-baseline-unexplained.md`). Do not size it from this one —
measure the in-render peak, which `experiment_pool_memory.py` currently cannot
see because it only samples *between* crawls.

> **PARKED 2026-08-02, and read why before restarting it.** Two things happened
> after this was written. First, the fit itself is disputed on three counts (that
> file's §"Why the fit is not settled") — most sharply, the 68 samples predate
> `13fcecb`, which changed what `get_container_memory_percent` measures, so the
> intercept is in a metric that no longer exists. Second, and larger: **an April
> note recorded that doubling replica memory is near-free on MS credits and it
> was never tried.** If the replica gets more headroom the question may not need
> answering at all. Tero decides the resize first.

**Adjacent, unchanged:** `minReplicas: 1` still removes the scale-from-zero
trigger and is still Tero's call; it is a scale setting, not `--set-env-vars`,
so it does not carry the token risk.

**Found in passing, not fixed, not mine to bundle:**
`monitor_routes.py:273-284` calls `init_permanent` *inside* `async with LOCK`,
and `init_permanent` acquires the same non-reentrant lock — a self-deadlock that
kills the replica permanently (every `get_crawler` and `release_crawler` blocks
forever). Admin-gated, so not on the traffic path. Verified by reading, not
executed. It deserves its own one-line change where a surprise is attributable.

## Verification

Offline, zero live requests. `pytest test-aitosoft/test_crawler_pool.py` (24
tests) and the full suite (244, green). `experiment_pool_memory.py --route
/heavy [-n N] [--blank]` for the figures. Assert eviction behaviour and browser
counts, **never absolute MB** — those are machine- and page-dependent, which is
why every number above is either a ratio, a slope, or a production reading.

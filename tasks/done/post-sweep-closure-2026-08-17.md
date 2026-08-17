# Post-sweep closure: seven items closed, and why each one is not worth doing

**Date:** 2026-08-17 · **Author:** coordinator session, after the final WAA sweep
**Status:** closure record. The files named here moved to `tasks/done/` **unchanged** — their
reasoning is why they are worth keeping. This document is the decision, not a summary of them.

---

## The measurement that governs all seven decisions

The final WAA sweep ran **2026-08-09T14:19 → 2026-08-16T21:50 UTC**, 175.5 h, **186,178 `/crawl`
requests** — five times anything either repo had run before. MAS's own capture table gives the
terminal accounting, which is the only number that matters, because it counts *pages we cost them*
rather than wire events:

| attributed to us | captures lost | of 60,874 attempts |
|---|---:|---:|
| our 429s (`capacity`) | **29** | 0.05 % |
| our 500s (`render_error`) | **156** | 0.26 % |
| our `render_defect` | 27 | 0.04 % |
| our `unrenderable_content` | 4 | 0.007 % |
| **everything else** | **origin** | 95 % of all failures |

**Total harm from every defect on the open list: about 216 captures in 60,874, and 2 requests that
failed hard at the wire.** 86.1 % of attempts stored successfully; 95 % of what failed was the
customer's own site being dead, 404, or blocking us.

**That is the bar every item below failed to clear.** Not because the diagnoses were wrong — most
were right and several were excellent — but because the thing being fixed is worth less than the
regression risk of fixing it, and in three cases upstream is fixing it for us.

**The reasoning to carry forward, because it is the expensive lesson:** *before opening an
investigation, state the upper bound on what the defect can be costing. If you cannot state it,
that bound is the first measurement.* This repo has consistently investigated first and sized
second. The single highest-value change in six months was **one config number** — the ACA scale
trigger, 6 → 12, worth ~6.4× on cost — and it was found in a week. Every code change of the past
month, combined, is worth about 2 pages.

---

## 1. `memory-guard-charges-reclaimable-page-cache.md` — CLOSED, settled by two repos

**The diagnosis was right and is now fully characterised.** The guard reads a cache-inclusive
working-set figure, its 85 % threshold sits **below the median of its own signal** (unconditional
p50 **86.6 %**, 60.8 % of samples already above the trip point), and the refusal count is therefore
a threshold-crossing artefact that carries no information about memory. Confirmed independently
from MAS's side: their 4,455 refusal readings reproduce our distribution **to one decimal** on every
percentile.

**And there is no leak.** Splitting the 53-hour post-trigger window in half, our `anon` p50 moved
**2,932 → 2,958 MB of 4,096 — +26 MB, +0.6 %**. MAS's independent gauge moved **+0.13 points**. Two
repos, two instruments, no accumulation.

**Every candidate fix is dead:**
- **(a) read `anon` instead** — refuted as unsafe alone: 23 of 34 restarts happened while the
  *current* guard was already refusing, so changing which number it reads cannot prevent them; it
  only removes the accidental restraint.
- **(b) `max_browsers: 6 → 4`** — the `max_browsers` refusal branch fired **0 times in 186,178
  requests**, exactly as `config.yml:161-169` predicts. There is a clean measured slope for it
  (`anon ≈ 441 MB + 386 MB × resident`, taken in the first 5 min after boot with `mem < 85` so the
  control loop is excluded) and it would remove ~790 MB from the pool floor. It is the best of the
  three. **It is still not worth shipping**, because the failure it prevents cost 29 captures.
- **(c) `idle_ttl_sec`** — refuted outright: in the 2-replica regime there were **56 TTL closes
  against 6,406 pressure evictions**. The TTL path is dead; shortening it cannot return memory that
  is already being returned.

**What would re-open this:** a sweep where the memory guard costs materially more than ~30 captures,
or an OOM that takes both replicas and loses a batch. Both are size-of-harm questions, not
mechanism questions — the mechanism is understood.

**One correction the file should carry into any future reading of it:** `config.yml:180` says
`idle_ttl_sec: 300  # 30 min janitor cutoff`. 300 s is **5 minutes**. `crawler_pool.py:641` uses it
as `cold_ttl = 300 s`, `hot_ttl = 600 s`. Anyone reasoning "we hold idle browsers for 30 minutes"
is reasoning from a false premise.

---

## 2. `crawl-cost-is-idle-replicas-not-slow-renders.md` — CLOSED, question answered

**The file's central claim was true and is now spent.** Over-provisioning *was* the bill: at trigger
6 the fleet averaged **11.05 replicas at 8.9 % slot utilisation**. Changing one number fixed it —
trigger 12 gives mean fleet **1.97**, **40 %** true utilisation, and **6.4× lower cost per request**
($3.28 → $0.51 per 1,000).

**But the headline no longer describes the system, and should not be re-used.** At trigger 12 the
fleet is a constant 2 across a 1.6× swing in load, so the bill is now `2 × $0.3024 × wall-clock`,
full stop. The remaining idle is **queueing headroom, not over-provisioning** — 29 % of admits
already wait and a one-replica probe rejected 10.6 %. The fleet is at its floor.

**The remaining levers are not ours.** MAS's `delay_before_return_html: 2.0` is **37 % of our mean
render time** (upstream default is 0.1), and pages-per-company is the other half. Both are on their
list. Ours are worth single-digit percentages of ~$32 per sweep.

**Two corrections this file must not propagate:** its euro figures are **USD** (the usage export
carries no currency column; Azure's EUR list is 0.8775 × USD), so `€398.89` is `$398.89 ≈ €350`;
and its "reducing render duration saves €0" holds only while the fleet tracks request rate, which
at a pinned fleet it no longer does.

---

## 3. The patchright tier retries classes already known permanent — CLOSED, upstream is fixing it

The saving as written is the `render_defect` leg alone, whose production population is **27 captures
across the whole sweep**. And its most expensive component — the retry leg dying on upstream's
`wait_for_selector("body", timeout=30000)`, i.e. waiting 30 s for exactly the element whose absence
defined the failure — **is upstream PR #2131**, filed 2026-08-06 against issue #2129.

Measured on our own traffic: that 30 s wait produced a visible spike of **316 renders in the
30–31 s band across 284 hosts** (a flat spread, the signature of a generic constant), costing
~2.2 render-hours — **0.9 % of render time**.

**This is the clearest instance of the rule the owner named: do not build what upstream will ship
in a month.** Take their fix on the next sync.

---

## 4. `static-mode-tls-impersonation.md` and `static-fallback-within-fence.md` — CLOSED, zero traffic

`render_mode: "static"` was used **0 times in 186,178 requests**. MAS's own `timing.jsonl` confirms
it from their side: `renderMode: "full"` on all **61,937** rows, and their 504-pivot never fired.

Static mode is a real feature and it still works; nothing here argues for deleting the code. But
two task files proposing to *improve* a code path with no traffic are not work. The same measurement
kills half of the "two `failure_class` log holes" item — the static-mode logging hole is real in
code and was **exactly zero requests wide**.

**What would re-open this:** MAS beginning to pivot hosts to static mode. Their dispatcher decides
that, so it is their signal, not ours.

---

## 5. `blocked-host-retry-economy.md` — CLOSED, the premise is refuted

The file assumes block rate is a property we can influence. The sweep says it is composition.

The standing IP-reputation stop-rule *appeared* breached — `origin_blocked` rose from a 0.12–0.30 %
baseline to 0.39 %/0.41 % on the last two days. It is not. On the **590 hosts crawled in both
regimes** the block rate is **identical: 2.75 vs 2.73 per 1,000**. Of those 590, **579 were never
blocked, 8 were blocked in both, 4 were blocked early only, and ZERO were blocked late only** —
reputation decay has exactly one signature and it is absent. Two composition-free corroborations:
origin-issued HTTP 429s **fell 25 → 1**, and challenge-asset rates were flat.

The rise is the input list. Dead-DNS rate went **0.19–0.25 %/day → 1.78 %/day** across the same
boundary, and a lapsed domain cannot be caused by a scale trigger.

---

## 6. `preflight-batch-endpoint.md` — CLOSED, both sides declined it

Recorded as justified but unbuilt by either repo; MAS's message `40-…` closed the need. Kept only
so the idea is not re-derived from scratch.

---

## 7. `cleaned-html-collapse-guard.md` part 2 (root-causing the four collapse shapes) — CLOSED

**The guard and its recovery path are working and that is the whole point of them.** Over the
sweep: **43 `COLLAPSE RECOVERED`** (median 37,729 chars rescued, max 81,840 — roughly **1.6 million
characters** of customer content the pre-2026-08-02 build would have discarded silently) against
**10 `RENDER DEFECT`** where html2text also found nothing. Nine of those ten recovered **0 chars**,
i.e. the page really was empty.

Root-causing the remaining shapes is prospective work on a population of ten. Part 2 was already
"explicitly parked"; this makes it a closure.

**One genuinely open thread was rehomed rather than lost** — see the new open list: **53 captures
came back with no `<body>` element at all**, and **26 of the 28 affected hosts emitted no
`CONSENT DECLINED` line**, so our own consent JS is not the cause for the great majority. That is a
real unexplained mechanism, but it is 53 captures and it needs a page MAS can show us.

---

## What survived, and why

Three items stayed open. Each clears the bar for a different reason, and none of them is a
performance optimisation:

- **The capacity gate in the 429 envelope** — it is MAS's one explicit ask, we committed to it, and
  `49-…` §1 is the argument: our memory gauge sat in their logs for a fortnight and took a regex
  over prose to read. Ships with `memory_pct` / `limit_pct` as structured fields.
- **`fixture-origin-bypasses-the-pinning-proxy.md`** — ~12 lines, and it makes 67 existing tests
  measure the network path production actually uses. It is the *fast* feedback loop, which is the
  only loop where investment still compounds.
- **`file-upstream-prs.md`** — reframed. This is a **simplicity** move, not altruism: our fork is
  +4,696 lines with ~2,375 of them on files upstream owns, and upstream is now editing `api.py` and
  `server.py` — our two heaviest diffs. A merged PR deletes our divergence permanently.

---

## Files moved to `tasks/done/` by this closure

`memory-guard-charges-reclaimable-page-cache.md` · `crawl-cost-is-idle-replicas-not-slow-renders.md`
· `static-mode-tls-impersonation.md` · `static-fallback-within-fence.md` ·
`blocked-host-retry-economy.md` · `preflight-batch-endpoint.md` · `cleaned-html-collapse-guard.md`

`residential-egress-retry-path.md` stays in `tasks/` but is **parked, not open** — it addresses the
layer our data says actually dominates (address reputation, not fingerprint), but it needs an
instrument neither repo has: a real browser from a residential IP. `curl` cannot substitute, because
a 403 there separates nothing and even a 200 could be TLS or header shape.

`guard-corpus-is-not-in-the-repo.md` stays too, at XS: either commit 4–6 artifacts into
`artifacts/keep/` or delete the file. Do **not** open its four-option sizing table.

# Overnight Intervention Log — 2026-04-16 Batch

**Purpose:** Record autonomous actions taken while the user slept during the
2026-04-15/16 Talgraf CRM enrichment run (MAS task-182 night 1, ~1200 companies
across 3 parallel WAA agents).

**Coverage window:** 2026-04-15 19:58 UTC → 2026-04-16 ~13:00 UTC (~17h).
**Tick cadence:** 20 min during campaign, 30 min during post-batch lulls.
**Total ticks:** 39.
**Interventions executed: zero.**

---

## Headline

Service ran the full overnight campaign + continuation batches on image
`0.8.6-static-mode` (revision `crawl4ai-service--0000012`, 6 replicas pinned
via `batch-scale.sh up 6`) without a single restart, rollback, or any manual
action. All incidents self-healed via pre-existing guards (Fix-1 timeout fence,
Fix-2 Janitor, pool memory-refusal guard, MAS-side static-pivot).

| Metric | Total over 17h |
|--------|----------------|
| Fix-1 clean 504 timeouts | ~132 (peak hour: 14 at 08:00 UTC) |
| Fix-2 force-close events | **0** |
| Janitor stuck-slot reaps | **0** |
| Leaked browsers | **0** |
| Memory alert firings | **0** (condition never crossed sustained 85%) |
| Replica restarts | **0** |
| Rollbacks | **0** |
| Replicas Running throughout | 6/6 on revision 0000012 |

Zero force-close across a full campaign's worth of traffic is the clean-signal
proof that Fix-1's timeout fence is releasing pool slots correctly via `finally`
— the Fix-2 Janitor never needed to intervene.

---

## Notable events (all self-recovered, zero interventions)

### Tick 11 — SPA timeout burst (~23:49 UTC 2026-04-15)

- Log Analytics window showed **14 `Page.goto: Timeout 90000ms exceeded`** hits
  in 20 min — one order of magnitude above the steady-state of 0–6.
- Cause: MAS hit a batch of SPA-heavy Finnish sites (likely Framer/Next.js
  hosted) that Playwright couldn't render in 90s.
- Recovery: next tick (00:10 UTC) dropped to 0 PW-NAV, confirming MAS's
  `render_mode=static` auto-pivot (2 consecutive 504s → host blacklisted for
  session) kicked in and rerouted those hosts to the bypass path.
- Action taken: **none**. The static-mode fallback shipped on 2026-04-15
  earned its keep here.

### Tick 20 — raumanteatteri.fi memory spike (~02:46 UTC 2026-04-16)

- **OOM signal fired on one replica: `MemoryError: Memory at 94.2%, refusing
  new browser`** (this is our own pool-guard, not OS-OOM).
- Correlated Fix-1 504s at 02:49:28 UTC showed **three parallel person-detail
  pages from raumanteatteri.fi** (harri-natunen, petteri-kangas,
  tuula-kupiainen-koivisto) all completing the full 180s hang simultaneously.
- Pool mem% timeline:
  - 02:46:36 — 94.2% (refused new browser)
  - 02:56:30 — 62.3%
  - 02:57:41 — 72.9% → 02:57:54 — 62.4%
  - 02:59:05 — 60.1%
- Memory alert never fired (spike didn't sustain 5 min above 85%).
- Root cause **confirmed on the MAS side** (LangSmith trace
  `f98b78e8-9068-4195-ae1e-e5ce0652ff7e`, dive documented in
  `tmp/deepdive-raumanteatteri-concurrency.md`): WAA issued **4 parallel
  `scrape_page` calls in a single multi-tool-use response** before any 504 had
  landed. The static-pivot circuit breaker requires 2 consecutive 504s per
  host, so it physically couldn't engage mid-batch. All three person-page
  Playwright tabs hung ≈180 s each on the same replica, holding browser state
  until Fix-1 forcibly released them.
- Fix lives on **MAS side**, not crawl4ai: WAA needs a
  "probe-before-fan-out" pattern (hit listing → serial fetch 1 sample →
  batch remainder once pattern confirmed). Alternative: cap per-host
  concurrent `scrape_page` to 1 inside a single multi-tool-use batch.
- Action taken: **none**. Pool guard refused the 4th browser spawn as
  designed, memory bled off as in-flight crawls completed, no cascade.

### Ticks 33–39 — between-batch lulls (~07:47 UTC onward)

- Seven consecutive zero-signal ticks after MAS night-1 batch completion.
- Service sat at 6 replicas × ~60% memory, no alarms, no noise.
- Cadence dropped to 30 min during idle to save cache turns.
- Continuation batches resumed briefly (tick counts showed more Fix-1s
  around 04:00–09:00 UTC) before Tero confirmed 1200/1200 complete.

---

## Signals watched

- `/health` HTTP code (expected 200).
- `crawl4ai-memory-high` alert `monitorCondition` (expected null / Resolved).
- `az containerapp replica list` (expected ≥6 Running on 0000012).
- Log Analytics signal summary over each 20 min window, categorized by:
  `FORCE-CLOSE`, `JANITOR`, `OOM`/`MemoryError`, `FIX1-504` (contains
  "Crawl exceeded"), `ACTIVE-REQ`, `PW-NAV-TIMEOUT` (Page.goto 90000),
  `OTHER`.

Observed false-positive class: `OTHER` sometimes picked up log lines whose
millisecond timestamps contained "504" (e.g. `02:20:17,504`). Verified by
inspection — not real 504 errors. Only `FIX1-504` and the bad-signal
categories carry signal.

---

## Pre-stated autonomous-action thresholds (none tripped)

- FORCE-CLOSE/JANITOR/OOM/ACTIVE-REQ > 0 → investigate; if sustained,
  restart. *(OOM fired once, investigated, confirmed transient — no action.)*
- Memory alert `Fired` OR replica non-Running >10 min → restart revision.
- Tier 1 default path red OR `active_requests` counter not decreasing with
  force-close spam (2026-04-14 stuck-slot pattern) → rollback to
  `0.8.6-leak-fix`.

---

## Morning handoff notes

- **Image stays as-is** (`0.8.6-static-mode`) — it's the first image to
  carry both the leak-fix stack (Fix-1/Fix-2) *and* the static-mode fallback,
  and it's now survived a ~1200-company campaign with 0 interventions.
- **No crawl4ai code changes indicated.** The raumanteatteri.fi event was a
  MAS-side concurrency bug that our guards handled gracefully; the fix
  belongs in WAA's URL-discovery loop (probe-before-fan-out), not in our
  pool or timeout layer.
- **Static-mode fallback verified under load.** Tick 11's SPA burst is the
  real-world proof that the 2026-04-15 fallback catches the exact case
  (Framer/Next.js SPAs that don't respond to Playwright nav) it was built
  for, and that MAS's 2-consecutive-504s pivot rule works end-to-end.
- **Memory alert still armed** (`crawl4ai-memory-high`, 85% / 5 min).
  Pool-guard (94.2% refuse) is a tighter, faster signal that fires before
  the Azure alert and self-recovers without paging.
- **Scale-down:** `./azure-deployment/batch-scale.sh down` is safe to run
  once Tero confirms no more batches are queued. Replicas cost ~nothing on
  MS credits so leaving 6 pinned between campaigns is also fine.

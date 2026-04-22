# Overnight Intervention Log — 2026-04-21 (WAA nightly run resumed)

**Purpose:** Record autonomous actions during the 2026-04-21 WAA nightly run —
first resume after the 2026-04-20 pause for MAS-side entity-resolution fixes.

**Coverage window:** 2026-04-21 16:52 UTC → 2026-04-22 00:47 UTC (~8h wall,
~7h active traffic).
**Tick cadence:** 1200s active, 1800s during taper/idle.
**Total ticks:** 22.
**Interventions executed: zero.**

Tero stopped the campaign at 00:47 UTC. Service left clean and scaled to zero
via `batch-scale.sh down`.

---

## Headline

Service absorbed a single ~7h active WAA run on revision `0000021`
(image `0.8.6-static-mode`, 15 replicas pinned via `batch-scale.sh up 15`)
with zero restarts, rollbacks, or manual action.

| Metric | Total |
|--------|------:|
| `[FETCH]` events | 27,921 |
| `[COMPLETE]` events | 23,750 |
| Fix-1 clean 504 timeouts | 187 |
| PW-NAV-TIMEOUT | 246 |
| OOM-guard log lines | 690 |
| Fix-2 force-close / Janitor reap | **0** |
| Memory alert firings | **0** |
| Replica restarts / rollbacks | **0** |
| Replicas Running throughout | 15/15 |

Memory envelope across 7,370 pool samples: **P50 70.7% / P90 82.8% /
P99 91.4% / Max 100.0%.** Per-replica excursions >95% clustered in four
burst windows between 19:50–21:55 UTC; each self-healed within the next
5-min bin; Azure alert never tripped.

---

## Burst windows

Campaign settled into a predictable burst-and-heal rhythm after a clean first
hour. Four separate pressure peaks:

| Peak bin | P99 | Max | n   | OOM/20min near peak | Next bin P99 |
|----------|-----|-----|-----|---------------------|--------------|
| 19:50    | 96.1| 97.5| 150 | 102                 | 90.4 (n=115) |
| 20:30    | 96.0| 97.0| 151 | 96                  | 98.6 (n=119, subthreshold) → 89.7 |
| 21:00    | 100 | 100 | 57  | 60                  | 92.8 (n=64) |
| 21:55    | 99.9| 100 | 143 | 57                  | 89.0 (n=119) |

Each burst showed the same structure: one 5-min bin pushing into the
90–100% zone, the next 1–2 bins back to 85–90%, OOM-guard count elevated
but not accelerating across 20-min windows, and no FORCE-CLOSE or stuck
ACTIVE-REQ.

**Decision on each: hold, do not restart.** Per playbook n≥150 filter, only
the 19:50 and 20:30 bins qualified — each was followed by a bin that
either dropped below 95% or had n<150, so the "sustained 2+ qualifying bins"
criterion never triggered. The 20:30 → 20:35 pair was closest (96.0 → 98.6)
but 20:35 fell under the n-gate at n=119.

---

## Taper and stop

| Tick | Window start | COMPLETE |
|------|-------------|---------:|
| 17 | 22:10 UTC | 1,351 |
| 18 | 22:30 UTC |   949 |
| 19 | 22:50 UTC |   623 |
| 20 | 23:25 UTC |   289 |
| 21 | 23:45 UTC |   0   |
| 22 | 00:16 UTC |   0   |

Switched from 1200s to 1800s cadence at 23:14 UTC once throughput started
tapering. Two consecutive zero ticks triggered the pre-stated Tero ping;
Tero confirmed nightly stopped.

---

## Signals watched

- `/health` HTTP code — 200 on every tick.
- `crawl4ai-memory-high` alert `monitorCondition` — null every tick.
- Replica count — 15/15 every tick.
- Log Analytics 20-min signal summary (FORCE-CLOSE, OOM, FIX1-504,
  PW-NAV-TIMEOUT, FETCH, COMPLETE, OTHER).
- Pool mem% percentiles (P50/P90/P99/max, 5-min bins, n-gated per playbook).

---

## Pre-stated thresholds (none tripped)

- Memory alert Fired → restart revision. **Never fired.**
- Pool mem% P99>95% sustained 2+ bins with n≥150 → restart.
  **Two qualifying bins (19:50, 20:30), neither followed by a second
  qualifying ≥95% bin.**
- FORCE-CLOSE / Janitor reap > 0 → investigate. **Zero real events.**
- `active_requests` stuck → rollback (2026-04-14 leak pattern). **Not observed.**
- OOM spikes >200 / 20min → restart. **Peak was 102.**

---

## Follow-ups

1. **(Playbook — recurring)** Second consecutive campaign where the n≥150
   filter was effectively one-sided under 15-replica steady state. Pool-log
   emission ceiling remains ~130–150 lines / 5-min bin; today two bins
   just scraped n=150 and n=151. The filter correctly avoids the
   2026-04-17-evening false-plateau pitfall but structurally prevents
   escalation when per-replica mem% genuinely stays hot for multiple bins
   (e.g. 20:30 → 20:35 here, P99 96.0 → 98.6 with the second bin at n=119).
   Worth proposing a concrete count-based alternate trigger next sustained-
   pressure campaign — e.g. "individual pool log lines with mem% > 95 ≥ X
   per 20-min window" — which is not percentile-based and unaffected by
   emission rate.
2. **(No code change indicated on crawl4ai side.)** Stack self-healed
   through a max-100% memory envelope with zero intervention. Guard held.

---

## Wrap

- `./azure-deployment/batch-scale.sh down` run at Tero's stop confirmation.
- Revision `0000021` carried the full campaign. Scale update will roll a
  new revision (same image, different scale config). Expected.
- Monitor loop stopped.

# Overnight Intervention Log — 2026-04-23 (WAA daytime bulk run)

**Purpose:** Record autonomous actions during the 2026-04-23 WAA daytime bulk
run. Tero pre-approved reduced-monitoring cadence (1800s throughout, vs
playbook default 1200s active) based on five prior zero-intervention campaigns.

**Coverage window:** 2026-04-23 06:30 UTC → 22:30 UTC (~16h wall clock,
~14h active traffic across two phases separated by a short MAS-side batch
setup gap around 12:00 UTC).
**Tick cadence:** 1800s throughout.
**Total ticks:** 30.
**Interventions executed: zero.**

Tero confirmed campaign complete at ~22:30 UTC. Service left clean and scaled
to zero via `batch-scale.sh down`.

---

## Headline

Service absorbed the longest single-session bulk run to date — ~14h active
crawl traffic on image `0.8.6-static-mode` (revision `crawl4ai-service--0000023`,
15 replicas pinned via `batch-scale.sh up 15`) with zero restarts, rollbacks,
or manual action.

| Metric | Total |
|--------|------:|
| `[FETCH]` events | 55,031 |
| `[COMPLETE]` events | 47,861 |
| Fix-1 clean 504 timeouts | 330 |
| PW-NAV-TIMEOUT | 408 |
| OOM-guard log lines | 1,419 |
| Fix-2 force-close / Janitor reap | **0** |
| Memory alert firings | **0** |
| Replica restarts / rollbacks | **0** |
| Replicas Running throughout | 15/15 |

Memory envelope across 16,903 pool samples: **P50 70.4% / P90 81.7% /
P99 91.0% / Max 100.0%.** Nine individual 5-min bins exceeded P99>95%
across the full day — none qualified under the n≥150 rule, none were
consecutive, and four of those bins saw single-replica Max=100%
excursions that all self-healed in the next bin.

---

## Comparison to 2026-04-21 reference run

| | 2026-04-21 (8h) | 2026-04-23 (16h) | Ratio |
|---|---:|---:|---:|
| Wall clock | ~8h | ~16h | 2.0× |
| FETCH | 27,921 | 55,031 | 1.97× |
| COMPLETE | 23,750 | 47,861 | 2.02× |
| OOM-guard | 690 | 1,419 | 2.06× |
| PW-NAV-TIMEOUT | 246 | 408 | 1.66× |
| FIX1-504 | 187 | 330 | 1.76× |
| FORCE-CLOSE | 0 | 0 | — |
| Interventions | 0 | 0 | — |
| P99 pool mem% | 91.4% | 91.0% | — |

Today was almost exactly 2× the 2026-04-21 volume, with all
stress-counter totals scaling proportionally and the memory envelope
almost unchanged. The service's absorption characteristics are now
well-characterized and stable across the `0.8.6-static-mode` image.

---

## Timeline

### Phase 1 — morning batch (~06:30 → ~11:45 UTC)

Ramped fast from the 07:11 UTC pin. Throughput held at 1400–1600 FETCH / 20min
across 15 replicas through most of the morning. Three OOM mini-bursts
(tick 7: 12→39→66, tick 23-style) each self-cleared within one tick. Pool
mem% probe at tick 7 showed P99 91–93.8%, nowhere near threshold.

### Batch-setup gap (~11:50 → ~12:20 UTC)

Tero reported "setting up a new batch" between ticks 10 and 11. One full zero
tick (tick 10) and one partial-zero tick (tick 11) during the gap. Service
idle-healthy throughout; pool janitor idle-closed hot browsers as designed.

### Phase 2 — afternoon/evening batch (~12:20 → ~22:15 UTC)

Longer and denser than phase 1. Campaign settled into a burst-and-heal rhythm
with two notable OOM pushes:

- **Tick 22 (18:40 UTC):** OOM 21 → 69. Pool mem% probe — P99 peaks 88–94.9%,
  single replica touched 98% at 18:25 bin, recovered next bin. Held.
- **Tick 26 (20:44 UTC):** OOM 42 → 84 (highest of day). Pool mem% probe —
  P99 peaks 88–90.4%, single replica hit 100% at 20:40 bin, recovered next
  bin. Held.

Both bursts collapsed within the following tick (84 → 57 and 69 → 57
respectively), matching the reference self-heal pattern. Playbook's
restart threshold (OOM > 200/20min; P99>95% sustained 2+ bins with
n≥150) never approached.

### Taper (~22:15 → 22:30 UTC)

FETCH dropped from 1366 to 56 in one tick, then to zero. Two consecutive
zero ticks (29, 30) triggered the pre-stated Tero ping per playbook. Tero
confirmed campaign complete.

---

## The P99 > 95% bins that never qualified

For posterity, all nine 5-min bins where P99 exceeded 95% across the full day:

| UTC bin | P99 | Max | n   |
|---------|-----|-----|-----|
| 07:40   | 97.5| 97.5| 69  |
| 08:20   | 96.7| 96.7| 95  |
| 08:25   | 96.2| 96.2| 85  |
| 14:45   | 100 | 100 | 86  |
| 16:20   | 95.9| 99.9| 113 |
| 16:40   | 95.7| 97.1| 134 |
| 17:45   | 100 | 100 | 91  |
| 18:00   | 96  | 97  | 109 |
| 19:45   | 95.6| 100 | 130 |

None reached n≥150. None consecutive. Four showed Max=100% — all isolated
single-replica excursions that recovered in the next bin. Same structural
pattern flagged in 2026-04-20 and 2026-04-21 follow-ups: the 15-replica
steady-state emission ceiling (~130–147 lines / 5-min bin) continues to
make the P99>95% rule effectively one-sided. See follow-up (1) below.

---

## Signals watched

- `/health` HTTP code — 200 on every tick.
- `crawl4ai-memory-high` alert `monitorCondition` — null every tick.
- Replica count — 15/15 every tick.
- Log Analytics 20-min signal summary.
- Pool mem% percentiles — run only when OOM guard count jumped notably
  (ticks 7, 22, 26). Kept cheap per reduced-monitoring plan.

---

## Pre-stated thresholds (none tripped)

- Memory alert Fired → restart revision. **Never fired.**
- Pool mem% P99>95% sustained 2+ bins with n≥150 → restart. **Zero
  qualifying bins across the full day.**
- FORCE-CLOSE / Janitor reap > 0 → investigate. **Zero real events.**
- `active_requests` stuck → rollback. **Not observed.** FETCH/COMPLETE
  gap peaked at 430 and always reversed within one tick.
- OOM spikes >200 / 20min → restart. **Peak was 84.**

---

## Follow-ups

1. **(Playbook — recurring, third campaign in a row)** The n≥150 gate on
   the P99>95% rule remains structurally unreachable under 15-replica
   steady state. Today's data: nine P99>95% bins, max n=134. Every prior
   campaign since 2026-04-17-evening has flagged this. Worth proposing a
   concrete count-based alternate trigger — e.g. "individual pool log
   lines with mem%>95 ≥ X per 20-min window" — which doesn't depend on
   percentile-over-small-n and would let the playbook escalate on
   genuinely sustained per-replica pressure. Deferring until a campaign
   actually pushes the service into trouble — so far the guard holds.

2. **(Monitoring cost)** Tero's reduced-cadence plan (1800s throughout,
   probe pool mem% only on OOM jumps, no categorical-summary helper
   script) worked well. 30 ticks over 16h vs playbook's ~48 ticks —
   ~37% fewer wakeups with no loss of signal visibility. The
   categorical Kusto summary already serves as our compression layer;
   further summarization was correctly judged as hiding-risk. Consider
   this pattern the new default for low-risk campaigns on proven
   images.

3. **(No code change indicated on crawl4ai side.)** Six back-to-back
   production campaigns on `0.8.6-static-mode` with zero interventions
   (2026-04-16 → 2026-04-17 morning → 2026-04-17 evening → 2026-04-20 →
   2026-04-21 → 2026-04-23). Stack is genuinely stable at current load
   envelope.

---

## Wrap

- `./azure-deployment/batch-scale.sh down` run at 22:30 UTC per Tero.
- Revision `0000023` carried the full day. KEDA will drain to zero on
  idle; scale update will roll a new revision (same image, different
  scale config). Expected.
- Monitor loop stopped.

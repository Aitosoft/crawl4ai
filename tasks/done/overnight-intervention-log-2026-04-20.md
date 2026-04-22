# Overnight Intervention Log — 2026-04-20 (WAA 5000-company run)

**Purpose:** Record autonomous actions taken during the 2026-04-20 WAA run
(planned as a 5000-company campaign). Two active phases today separated by a
long MAS-side pause.

**Coverage window:** 2026-04-20 08:44 UTC → 19:25 UTC (~10h40m wall, ~4h
active crawl traffic across two phases).
**Tick cadence:** 1200s active, 1800s during idle pause.
**Total ticks:** ~20 (7 active phase-1, 8 paused-idle, 5+ active phase-2).
**Interventions executed: zero.**

Campaign did **not** complete — Tero paused for the night at ~19:20 UTC due to
further MAS-side issues. Service left clean and scaled to zero via
`batch-scale.sh down`.

---

## Headline

Service absorbed two partial passes of the 5000-company WAA run on revision
`crawl4ai-service--0000019` (15 replicas pinned via `batch-scale.sh up 15`)
with zero restarts, rollbacks, or manual action.

| Metric | Phase 1 (08:44–10:50) | Phase 2 (17:35–19:25) | Total |
|--------|----------------------:|----------------------:|------:|
| `[FETCH]` events | 10,371 | 7,644 | 18,015 |
| `[COMPLETE]` events | 8,335 | 6,451 | 14,786 |
| Fix-1 clean 504 timeouts | 73 | 56 | 129 |
| PW-NAV-TIMEOUT | 78 | 66 | 144 |
| OOM-guard log lines | 228 | 330 | 558 (~186 guard trips) |
| Fix-2 force-close / Janitor reap | 0 | 0 | **0** |
| Memory alert firings | 0 | 0 | **0** |
| Replica restarts / rollbacks | 0 | 0 | **0** |
| Replicas Running throughout | 15/15 | 15/15 | — |

Memory envelope across 4,608 pool telemetry samples (08:44–19:25 UTC):
**P50 70.9% / P90 83.1% / P99 92.8% / Max 100.0%.** Multiple single-replica
excursions >95% during late phase 2 (18:25–19:05 UTC) — all recovered within
the 5-min alert window; Azure alert never tripped.

---

## Phase 1 — first active pass (08:44 → 10:50 UTC)

Campaign was already running when Tero handed off monitoring at 08:44 UTC
("We will run WAA, please pin 15 min replicas and monitor as per playbook").
Pinned minReplicas=15 via `batch-scale.sh up 15`, baseline was clean.

- Throughput ramped quickly: 1708 FETCH / 1324 COMPLETE by tick 2 (09:08 UTC).
- Held at ~1500–1750 FETCH per 20-min window for ~2h.
- OOM-guard trips scaled with load: 9 → 48 → 45 → 105 across ticks 2–7.
- Single-bin mem% spike to 99.6 at 09:50 UTC (n=119 at time of read),
  recovered next window. Same 2026-04-17-evening late-data pattern as before:
  bin re-filled with more samples on subsequent tick. Not actionable per
  n≥150 rule.
- No FORCE-CLOSE, no stuck ACTIVE-REQ, alert never fired.

Phase 1 ended abruptly when MAS paused the campaign at ~10:50 UTC.

---

## Long pause (10:50 → 17:35 UTC, ~6h45m)

Tero reported: *"We are taking a small break to investigate WAA potentially
cross polluting contacts in cases where registry has parent company url
instead of the entity who should be investigated."*

Not a crawl4ai issue — MAS-side entity-resolution problem where parent and
subsidiary legitimately share a website and the crawl cannot tell which entity
the contact data belongs to. Saved as project memory for future sessions.

Monitor held at 1800s idle cadence. Service stayed healthy across the full
pause: health 200, 15 replicas Running, alert clean, no activity in LA
(as expected — no traffic).

One minor artifact: the original 1200s active-cadence wakeup fired once after
Tero's clarification before the corrected 1800s paused wakeup took over.
Acknowledged that tick and ended its branch. Same pattern (old wakeup firing
after context change) recurred at resume. Not a bug — just the cost of
re-parameterizing a running loop.

---

## Phase 2 — resumed after MAS fixes (17:35 → 19:25 UTC)

Tero resumed: *"It took quite a while for us to get this done but we shipped
few targeted fixes and are resuming the 5000 company run now."*

- Activity ramp visible in LA by 17:35 UTC; first post-resume tick at 17:27
  saw nothing yet (LA ingestion lag + MAS warm-up).
- Second tick (17:48) showed full throughput: 1741 FETCH / 1475 COMPLETE over
  the recovered 20-min window.
- Pool mem% ran hotter than phase 1 and stayed hot.

### Notable signal pattern (18:25–19:05 UTC)

Pool mem% P99 >95% in **5 of 6 non-partial bins**:

| 5-min bin | P99 | Max | n |
|-----------|-----|-----|---|
| 18:25 | 97.8 | 99.9 | 128 |
| 18:35 | 98.0 | 99.8 | 134 |
| 18:45 | 97.2 | 99.1 | 147 |
| 18:55 | 96.1 | 97.3 | 123 |
| 19:00 | 96.9 | 99.6 | 116 |
| 19:05 | 99.0 | 99.7 | 115 |

**Decision: hold, do not restart.**

- Playbook n≥150 filter — zero qualifying bins. Closest was 18:45 at n=147.
  Emission rate under steady state appears to cap ~130–147 lines / 5-min bin
  × 15 replicas, which is at/below the de-noising threshold. A real blind
  spot worth revisiting in the playbook (see follow-ups).
- Azure memory alert (replica-level, sustained 85%/5min — the canonical
  "guard overwhelmed" trigger) never fired. Pool-level %'s in the log line
  are narrower than the alert's signal.
- OOM-guard count stabilized (66 → 138 → 99 across three ticks) — guard
  working, not accelerating.
- No FORCE-CLOSE, no stuck ACTIVE-REQ, throughput steady at ~1500 FETCH /
  20 min, P50 pool mem% ~73% (cluster healthy; peaks were per-replica).
- P50 across all 4,608 samples: 70.9%. Max spikes are outlier-driven, not
  plateau.

Campaign ended before this trend either self-cleared or escalated. If it had
continued and produced a single bin with P99>95% AND n≥150 AND a follow-on
bin also >95%, I was prepared to restart the revision.

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
  **Breach repeated but never qualified on n.**
- FORCE-CLOSE / Janitor reap > 0 → investigate; sustained → restart/rollback.
  **Zero real events.**
- `active_requests` stuck → rollback (2026-04-14 leak pattern).
  **Not observed.**
- OOM spikes >200 / 20min → restart. **Peak was 138.**

---

## Follow-ups

1. **(Playbook)** The n≥150 de-noising filter is correct for avoiding the
   2026-04-17-evening false-plateau pitfall, but under 15-replica pinned
   steady state the log emission rate caps around 130–147 per 5-min bin,
   which means the P99>95% rule is structurally unreachable even when
   per-replica mem% is genuinely running hot for 25+ minutes. Consider
   either (a) adding a lower-n trigger with a stricter P99 bar (e.g.
   "P99>98% across 3+ bins with n≥100"), or (b) adding a count-of-samples-
   at-mem%>95 trigger that is not percentile-based. Revisit after next
   sustained-pressure campaign.
2. **(MAS, out of scope here)** Parent/subsidiary URL cross-pollution —
   MAS-side entity resolution issue. Surfaced today, fixes partially
   shipped, remaining issues caused tonight's pause.
3. **(No code change indicated on crawl4ai side.)** Stack continued to
   self-heal through a notably harder-than-2026-04-17 memory envelope
   (max 100% vs 99.4%, P99 92.8% vs 91.4%). Guard held.

---

## Wrap

- `./azure-deployment/batch-scale.sh down` run at session end per Tero.
- Revision `0000019` carried the entire campaign; the min-replicas update
  rolled `0000020` (same image, different scale config). Expected Azure
  behavior — KEDA will drain to zero on idle.
- Monitor loop stopped.

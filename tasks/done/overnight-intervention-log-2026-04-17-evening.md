# Overnight Intervention Log — 2026-04-17 Evening Batch (Task-182 Final Run)

**Purpose:** Record autonomous actions during MAS's 3,074-company Task-182
final-run campaign. Follows the morning 2,500-row campaign (separate log
`overnight-intervention-log-2026-04-17.md`) — same revision, same day, new
MAS task.

**Coverage window:** 2026-04-17 18:14 UTC → 2026-04-17 23:10 UTC (~5h wall,
~4h14m actual campaign traffic per MAS's own summary).
**Tick cadence:** 20 min during campaign, 30 min during idle/MAS-down.
**Total ticks:** 14 active-campaign + 10 post-idle confirmation.
**Interventions executed: zero.**

---

## Headline

Service absorbed a 3,074-row / 18,187-contact Task-182 final-run campaign on
image `0.8.6-static-mode` (revision `crawl4ai-service--0000015`, 15 replicas
pinned) with zero restarts, rollbacks, or manual action. MAS reported 0
errors / 0 confirmed hallucinations / 100% HEALTHY-GROUNDED.

| Metric | Total over campaign window |
|--------|---------------------------|
| `[FETCH]` events | 23,820 |
| `[COMPLETE]` events | 20,633 |
| Fix-1 clean 504 timeouts | 132 |
| PW-NAV-TIMEOUT (Playwright 90s nav) | 98 |
| OOM-guard log lines | 2,061 (~687 guard trips) |
| Fix-2 force-close / Janitor reap | **0** |
| Memory alert firings | **0** |
| Replica restarts | **0** |
| Rollbacks | **0** |
| Replicas Running throughout | 15/15 on revision 0000015 |

Memory envelope across 7,648 pool telemetry samples:
**P50 74.7% / P90 86.6% / P99 95.2% / Max 100.0%.** Four 5-min bins hit
Max=100% (18:50, 19:55, 20:55, 21:00 UTC), each recovering within the
following bin. No cgroup OOM-kills. Guard successfully refused every
over-limit browser spawn.

---

## Comparison to morning campaign (same day)

| | Morning (2,500 rows) | Evening (3,074 rows) |
|---|---|---|
| Duration | 4h15m | 4h14m |
| Throughput | ~588 rows/h | **~726 rows/h (+23%)** |
| OOM-guard trips | ~164 | **~687 (4×)** |
| Max pool mem% | 99.4% (single peak) | **100% (4 peaks)** |
| P99 pool mem% | 91.4% | **95.2%** |
| Interventions | 0 | 0 |

Evening was a materially denser load than the morning — distribution shifted
~3-4pp higher across all percentiles, and OOM guard fired 4× more often.
Service still self-healed throughout.

---

## Timeline

### 18:14 → 18:25 UTC — first burst, MAS crash

- Campaign ramped fast. Tick 2 (18:24) saw 1,735 FETCH / 1,484 COMPLETE in
  20 min with 120 OOM trips. Max pool mem hit 99.2% at 18:15 on one replica.
- MAS container crashed ~18:25 UTC. Last [FETCH] at 18:25:33 (havator.com),
  last Fix-1 504 cleaned up ~18:27.
- Crawl4ai side was healthy at the moment MAS disappeared: no 5xx spike, no
  stuck slots, no unusual response-time pattern. Whatever killed MAS, the
  crawl4ai side didn't push it there.

### 18:25 → ~18:48 UTC — idle gap

- Zero crawl traffic. Pool janitor idle-closed hot browsers at their 10-min
  threshold (`Closing hot browser (sig=…, idle=640s)`). Supervisord reaped
  child pids with `exit status 0` — benign, as documented.

### ~18:48 → ~22:50 UTC — main campaign (~4h of traffic)

- Steady ~80 FETCH/min aggregate across 15 replicas (~5.3/replica/min —
  consistent with morning).
- Memory ran at the hot edge throughout: **P99 oscillated between 91% and
  99%, touching 100% max in four 5-min bins across the night.** Every
  100% peak was a single-bin excursion that recovered within the next bin.
  OOM-guard fired 36-66 trips per 5-min bin during peak — doing exactly
  what it was built for.
- FETCH/COMPLETE gap stayed bounded throughout (peak 432 never approached;
  typical 22–184 per 5-min bin). No stuck-slot pattern.
- Zero FORCE-CLOSE, zero Janitor reaps, Azure alert `monitorCondition` null
  every tick.

### ~22:50 → 23:10 UTC — wind-down

- Throughput dropped ~70% in the 23:00 bin (509 FETCH over 20 min vs prior
  ~1,700). OOM trips crashed from 132 to 18 within one tick.
- By 23:10 UTC, zero FETCH/COMPLETE; pool janitor idle-closing hot browsers.
  Confirmed post-campaign idle.

### 23:10 → 05:21 UTC — unattended idle

- Six confirmation ticks across ~6h of silence. Health 200 every tick,
  alert null, 15 replicas Running, zero log output after ~00:10 UTC
  (all hot browsers had idle-closed, nothing left to reap). Service held
  stable through the full idle period.

---

## The "restart recommendation" tick (non-event, worth documenting)

At tick 6 (19:59 UTC) the monitor saw what looked like a sustained P99>95%
plateau across 5 consecutive 5-min bins (19:35–19:55). Per the playbook's
"Pool mem% P99 > 95% sustained across 2+ 5min bins → Restart revision" rule,
a restart was formally recommended to the operator.

**Tick 7 (20:21) re-queried the same window and P99 came back much lower**
(e.g., 19:55 went from 99.7 → 89.1 once more samples arrived). The earlier
read had been skewed by a small number of late-arriving outlier samples
disproportionately dominating P99 in a low-n bin. The actual pattern was
oscillating stress-recover, not sustained plateau — consistent with what
the guard is designed to absorb.

**Lesson (playbook follow-up):** treat single-tick P99 reads with `n < 150`
samples as provisional until the next tick confirms. Log Analytics
ingestion latency + outlier sensitivity of P99 in small samples can make a
momentary spike look like a plateau for one tick. The monitor was right to
hold rather than restart unilaterally.

Holding was correct. By tick 10 (21:24) the pattern was confirmed as
oscillating and the remainder of the campaign proved the guard could
absorb this load indefinitely.

---

## Pre-stated autonomous-action thresholds (none tripped)

- FORCE-CLOSE/JANITOR count > 0 → investigate; sustained → restart.
  *(Zero real events across 5h window.)*
- OOM guard firing → peek mem% timeline; >85% sustained 10+ min → restart.
  *(687 trips cluster-wide. Every trip self-healed within the 5-min
  alert window. Azure alert never fired.)*
- Memory alert `Fired` → restart revision. *(Never fired.)*
- `active_requests` stuck (2026-04-14 leak pattern) → rollback.
  *(Not observed. Fix-1 `finally` released pool slots cleanly.)*
- Pool mem% P99 > 95% sustained across 2+ 5min bins → restart.
  *(See "restart recommendation tick" above — flagged once, recovered on
  next tick without action. Lesson: treat low-n samples as provisional.)*

---

## Handoff notes

- **Image + revision continue to prove out.** `0.8.6-static-mode` on
  `crawl4ai-service--0000015` has now cleared three back-to-back production
  campaigns (1,200 on 2026-04-16; 2,500 on 2026-04-17 morning; 3,074 on
  2026-04-17 evening) with zero interventions. Total Task-182 delivery:
  7,538 / 7,735 active Talgraf-linked companies (97.4%) per MAS summary.
- **No crawl4ai code changes indicated.** The stack (pool guard + Fix-1
  `finally` + Patchright fallback + static-mode fallback) absorbs the full
  load envelope MAS currently generates.
- **Evening load was 23% denser than morning.** Guard fired 4× more often
  and distribution shifted ~3-4pp higher, but still self-healed. Suggests
  current 15-replica capacity has headroom for ~30% more throughput before
  the OOM guard becomes the actual bottleneck.
- **MAS crash at 18:25 UTC was not crawl4ai-triggered.** Crawl4ai was
  healthy at the moment (no 5xx spike, no stuck slots, balanced
  FETCH/COMPLETE). Root cause belongs to MAS-side investigation.

### Follow-up for playbook

- Add guidance about `n < 150` low-sample P99 reads — single-bin P99 should
  be treated as provisional until confirmed by next tick with more samples.
  The 2+ consecutive bins rule is still correct, but a low-n bin shouldn't
  count as one of the two.

### Post-campaign actions (this session)

- Tero confirmed campaign complete — scaling down via
  `./azure-deployment/batch-scale.sh down`.
- Monitoring stopped.

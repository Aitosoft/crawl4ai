# Overnight Intervention Log — 2026-04-17 Batch

**Purpose:** Record autonomous actions taken during MAS's 2500-company
enrichment campaign (re-run after 2026-04-16 morning lost progress to an
unrelated cause).

**Coverage window:** 2026-04-16 19:35 UTC → 2026-04-17 08:03 UTC (~12.5h wall,
but only ~4h15min of actual campaign traffic: 03:30 → 07:45 UTC).
**Tick cadence:** 20 min throughout.
**Total ticks:** 13 (1 pre-crash + 12 post-resume). See "Monitor-side crash" below.
**Interventions executed: zero.**

---

## Headline

Service absorbed a 2,500-row / 16,710-contact campaign on image
`0.8.6-static-mode` (revision `crawl4ai-service--0000015`, 15 replicas pinned
via `batch-scale.sh up 15`) with zero restarts, rollbacks, or manual action.
MAS reported `0 errors, 0 T-01 false high-positives` on clean shutdown.

| Metric | Total over campaign window |
|--------|---------------------------|
| `[FETCH]` events | 19,166 |
| `[COMPLETE]` events | 16,340 |
| Fix-1 clean 504 timeouts | 116 |
| PW-NAV-TIMEOUT (Playwright 90s nav) | 96 |
| OOM-guard log lines | 492 (~164 guard trips) |
| Fix-2 force-close / Janitor reap | **0** |
| Memory alert firings | **0** |
| Replica restarts | **0** |
| Rollbacks | **0** |
| Replicas Running throughout | 15/15 on revision 0000015 |

Memory envelope across ~5,140 pool telemetry samples:
**P50 70.3% / P90 81.9% / P99 91.4% / Max 99.4%.** Three brief single-replica
excursions >95% (04:40, 06:50, 07:30 UTC) all recovered within the 5-min
alert window without tripping the Azure alert.

---

## Notable events (all self-recovered, zero interventions)

### Tick 3 — first peak (04:40 UTC)

- Cluster-wide max pool mem% hit **98.7%** on one replica during the early
  campaign ramp.
- OOM-guard fired in bursts (3 lines per trip = full traceback). Cluster
  total ~26 trips / 20 min.
- Recovery: next tick max back to 87%. Pool guard caught every spawn
  attempt that would have crossed into OS-OOM territory.

### Tick 9 — biggest burst of the night (06:40–07:00 UTC)

- Two OOM bursts: **21 lines at 06:44 UTC + 24 lines at 06:52 UTC** (~15
  actual guard trips in 8 min).
- Peak mem% hit **99.1% at 06:50 UTC** on a single replica — closest
  approach to OS-OOM for the campaign.
- Recovery: by tick 10 (07:21 UTC), OOM count was down to 3 lines / 20 min.
  Max pool mem% at 07:35 UTC was back to 71%.
- MAS's 0-error result confirms these minutes produced retryable responses
  that MAS absorbed via its own retry path, not permanent failures.

### Tick 10 boundary — in-flight backlog (07:21 UTC)

- `[FETCH]` (1585) notably exceeded `[COMPLETE]` (1153) in the 20-min
  window — gap of 432.
- By tick 11 the gap had tightened to 63, confirming crawls completed and
  MAS was shifting into wind-down, not that anything was stuck.

### Tick 11 — campaign wind-down (07:42 UTC)

- Throughput dropped ~70% (497 FETCH / 434 COMPLETE vs 1585/1153).
- Brief 99.4% mem spike at 07:30 UTC on a single idle-wind-down replica
  (P90 only 77.9% — truly one replica). Recovered by 07:35 UTC.
- Tick 12 (08:03 UTC) confirmed post-campaign idle: 0 FETCH, 0 COMPLETE,
  0 errors, just Redis RDB snapshot chatter.

---

## Monitor-side crash (not service-related)

- Pre-crash tick at 19:35 UTC 2026-04-16 was clean.
- Next scheduled wakeup at 20:12 UTC never fired — Claude monitoring
  process crashed. Exact cause not diagnosed on crawl4ai side; MAS-Claude
  and host-side Claude investigating their respective domains.
- **Service ran unattended for ~7.5h.** Revision did not rotate; no restart;
  `crawl4ai-memory-high` never fired. Log analytics confirmed service
  processed a modest post-19:30 UTC workload then went idle ~21:00 UTC as
  MAS's first attempt wound down.
- One OOM-guard trip at 20:07 UTC during the unattended period (`Memory at
  91.9%, refusing new browser`) — guard self-healed within the window.
- Resumption: Tero relaunched MAS campaign ~03:30 UTC 2026-04-17; monitor
  re-engaged at 04:06 UTC.

---

## Signals watched

- `/health` HTTP code (expected 200) — 200 on every tick, 121-210 ms.
- `crawl4ai-memory-high` alert `monitorCondition` (expected null) — null
  every tick.
- Replica count — 15/15 every tick.
- Log Analytics 20-min signal summary, categorized: `FORCE-CLOSE`,
  `JANITOR`, `OOM`, `FIX1-504`, `PW-NAV-TIMEOUT`, `FETCH`, `COMPLETE`,
  `OTHER`.
- Pool mem% percentiles extracted from `📊 Pool: hot=… mem=…%` log lines,
  5-min bins (P50, P90, P99, Max). Essential signal — surfaced the
  99.1% and 99.4% peaks that single `refusing new browser` lines alone
  wouldn't have explained.

### Playbook regex improvement (applied mid-session)

- First tick used the playbook's stock `JANITOR` regex (`contains "reap"`).
  That picked up **1,776 false positives in one 2h window** — all
  supervisord's benign `reaped unknown pid … exit status 0` messages,
  nothing to do with Fix-2.
- Tightened to `contains "Janitor reaped"` for the remainder of the
  session. Zero real Janitor events all night.
- **Follow-up:** `OVERNIGHT_PLAYBOOK.md` Kusto snippet should be updated to
  use the tighter pattern. (Deferred — small change, not urgent.)

---

## Pre-stated autonomous-action thresholds (none tripped)

- FORCE-CLOSE/JANITOR count > 0 → investigate; sustained → restart.
  *(Zero real events all night.)*
- OOM guard firing on one replica → peek mem% timeline; if sticks >85%
  for 10+ min, restart. *(Fired ~164 times cluster-wide, every single
  trip self-healed within the 5-min alert window.)*
- Memory alert `Fired` → restart revision. *(Never fired.)*
- `active_requests` stuck (2026-04-14 leak pattern) → rollback.
  *(Not observed; Fix-1 `finally` continues to release pool slots cleanly.)*

---

## Morning handoff notes

- **Image stays as-is** (`0.8.6-static-mode`, revision 0000015).
  It has now cleared two consecutive campaigns (1,200 on 2026-04-16;
  2,500 on 2026-04-17) with zero interventions.
- **No crawl4ai code changes indicated.** Guard + Fix-1 + Patchright
  fallback stack continues to do exactly what it was built for.
- **Pool guard at ~85% is carrying the load.** Every approach to
  OS-OOM (99.1%, 99.4%) was caught by the guard. The Azure alert at
  85%/5min remains useful as a backstop but has not paged in two
  campaigns.
- **15 replicas held up well** for 2,500 rows / ~4h15min. Throughput
  peaked around 1,680 FETCH / 20 min (~84/min aggregate = ~5.6/replica/min).
- **Scale-down deferred:** Tero asked to hold the 15 replicas for a
  500-company smoke test immediately following this campaign.
- **Follow-up (minor):** tighten `JANITOR` Kusto regex in
  `OVERNIGHT_PLAYBOOK.md` from `contains "reap"` to
  `contains "Janitor reaped"`.
- **Follow-up (MAS + host side, out of scope here):** diagnose the
  19:35 → ~03:20 UTC monitoring-Claude crash.

---

## Addendum — 500-company smoke test (12:35 → ~13:20 UTC)

Kicked off immediately after main campaign wrap-up. Ran while intervention
log was being written and playbook was patched. Tero asked to hold 15
replicas through the smoke test rather than scale down first.

| Metric | Smoke test total |
|--------|------------------|
| Ticks monitored | 3 |
| `[FETCH]` / `[COMPLETE]` | ~1,880 / ~1,310 |
| FIX1-504 | 29 (mostly first 20 min before static-mode pivot) |
| PW-NAV-TIMEOUT | 30 (same pattern) |
| OOM-guard firings | **0** |
| FORCE-CLOSE / Janitor | **0** |
| Max pool mem% | 88.2% |
| Alert firings | **0** |
| Interventions | **0** |

**Tick 1 (12:54 UTC)** — first batch was SPA/slow-site heavy (21 FIX1-504
+ 28 PW-NAV in one 20-min window). Tick 2 (13:15 UTC) showed the drop
(8 FIX1-504, 2 PW-NAV) — MAS's 2-consecutive-504-per-host pivot rule
engaged exactly as designed. Tick 3 (13:36 UTC) was post-campaign idle
with zero traffic.

Smoke-test served as an in-the-wild re-verification of the static-mode
fallback path under load. No code issue surfaced. Memory envelope was
significantly more relaxed than the overnight campaign (max 88% vs 99.4%)
— 500 rows against 15 replicas is well under capacity.

### Also completed in this session

- **Monitor email unsubscribe:** removed `tero.vaalamaki@aitosoft.com`
  from action group `crawl4ai-oncall` (only receiver). Alert
  `crawl4ai-memory-high` still fires and surfaces via
  `az monitor metrics alert show`'s `monitorCondition` — playbook
  monitoring is unchanged — but no email is sent. Re-subscribe:
  `az monitor action-group update --name crawl4ai-oncall --resource-group aitosoft-prod --add-action email oncall1 tero.vaalamaki@aitosoft.com`.
- **Playbook patched** (`OVERNIGHT_PLAYBOOK.md`):
  - Tightened JANITOR regex to `contains "Janitor reaped"`.
  - Added pool-mem% percentile Kusto snippet.
  - Added signal-interpretation row for "P99 > 95% sustained across 2+
    5min bins → restart".

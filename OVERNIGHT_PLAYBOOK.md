# Overnight Monitoring Playbook

Claude-for-Claude. When Tero says "monitor overnight" / "I'm AFK, watch the
service" / similar, read this file and use `ScheduleWakeup` to loop.

## When to engage

- Active MAS campaign (typically 1–5 parallel WAA agents, hundreds–thousands of
  companies over several hours).
- User explicitly hands off monitoring. Don't self-start.

## Service facts

- Endpoint in `.env` as `CRAWL4AI_API_URL` + `CRAWL4AI_API_TOKEN`.
- Image is whatever's currently deployed — check `az containerapp show` if
  you need to know. Previous known-good image is the one before current
  (check `AITOSOFT_CHANGES.md` most-recent entry).
- Resource group: `aitosoft-prod`. Container app: `crawl4ai-service`.
- Memory alert: `crawl4ai-memory-high` (85%, sustained 5 min, severity 2).
- Log Analytics workspace ID: `be17d63b-1807-49da-9846-82091ac8971d`.
- `./azure-deployment/batch-scale.sh up N` / `down` pins / releases minReplicas.
  Tero will usually do this; verify with replica list.

## Tick checks (run in parallel)

```bash
curl -s -o /dev/null -w "%{http_code}\n" $CRAWL4AI_API_URL/health
az monitor metrics alert show --name crawl4ai-memory-high --resource-group aitosoft-prod --query "{cond:monitorCondition, enabled:enabled}" -o json
az containerapp replica list --name crawl4ai-service --resource-group aitosoft-prod -o table
az monitor log-analytics query -w be17d63b-1807-49da-9846-82091ac8971d --analytics-query '<kusto>'
```

Kusto signal summary (20-min window), categorize by `case()`:
`FORCE-CLOSE` (contains "Janitor reaped" or "force_close" or "FORCE-CLOSE"),
`OOM`/`MemoryError` (contains "refusing new browser"),
`FIX1-504` (contains "Crawl exceeded"), `ACTIVE-REQ`,
`PW-NAV-TIMEOUT` (Page.goto 90000), `FETCH` (contains "[FETCH]"),
`COMPLETE` (contains "[COMPLETE]"), `OTHER`.

**Do NOT use `contains "reap"`** for JANITOR — matches supervisord's
benign `reaped unknown pid … exit status 0` chatter and floods with
thousands of false positives (2026-04-17 lesson).

Add pool-mem% percentile view — it surfaces near-OS-OOM single-replica
peaks the `refusing new browser` count alone doesn't explain:
```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(20m)
| where ContainerAppName_s == "crawl4ai-service"
| where Log_s contains "Pool:" and Log_s contains "mem="
| extend mem_pct = toreal(extract(@"mem=([\d.]+)%", 1, Log_s))
| summarize p50=percentile(mem_pct, 50), p90=percentile(mem_pct, 90),
            p99=percentile(mem_pct, 99), max=max(mem_pct) by bin(TimeGenerated, 5m)
```

## Cadence

- Active campaign: `ScheduleWakeup delaySeconds=1200` (20 min — under cache
  TTL).
- Idle / between-batch lulls: `1800` (30 min).
- Never `300` — worst of both worlds on cache.

## Signal interpretation (the non-obvious part)

| Signal | Meaning | Action |
|---|---|---|
| FIX1-504 ("Crawl exceeded 180s … Releasing pool slot via finally") | Fix-1 fence fired, slot released cleanly | **None.** This is normal. Expect 0–10 per 20-min window. |
| PW-NAV-TIMEOUT ("Page.goto: Timeout 90000ms exceeded") | Playwright's own 90s nav timeout | **None.** Normal for slow/SPA sites. MAS pivots to static after 2 consecutive 504s per host. |
| OOM / MemoryError "refusing new browser" | **Our pool guard**, not OS-OOM. Replica hit ~85%+ and refused a new browser spawn. | Peek pool mem% timeline (`Pool: hot=… mem=…` log lines). If it drops back within ~5 min, no action — the guard worked. If it sticks >85% for 10+ min, restart the revision. |
| OTHER | Usually garbage. Log lines whose ms timestamp contains "504" (e.g. `02:17:04,504`) hit the regex. | Peek once per night to confirm, then ignore. |
| FORCE-CLOSE / "Janitor reaped" | Fix-2 Janitor killed a stuck slot | Investigate. If recurring, stuck-slot pattern from 2026-04-14 — restart or rollback. |
| ACTIVE-REQ counter not decreasing over multiple ticks | Stuck-slot pattern | **Rollback** to previous known-good image. |
| Pool mem% P99 > 95% sustained across 2+ 5min bins | Cluster approaching OS-OOM, guard overwhelmed | Restart revision. Single-bin spikes to 99% that recover next window are normal and self-healing. **Only count bins with `n >= 150` samples** — low-n P99 is outlier-sensitive and can misread late-arriving log data as a plateau (2026-04-17-evening lesson). Re-query on the next tick before acting. |

## Intervention thresholds

- Memory alert `Fired` (monitorCondition ≠ null/Resolved) → restart the
  current revision.
- Replica non-Running >10 min → restart.
- Sustained 504 rate on healthy Tier 1 hosts → restart.
- Stuck-slot pattern (force-close spam + active_requests stuck) → **rollback**
  to previous image via `az containerapp update --image …` (never
  `deploy-aitosoft-prod.sh --update-only`, it regenerates MAS's token).

Don't restart just because of one OOM guard firing or one burst of Fix-1s.
Those are designed to self-heal.

## End of campaign

When Tero confirms all rows processed:
1. Write `tasks/done/overnight-intervention-log-YYYY-MM-DD.md` using
   `2026-04-14` or `2026-04-16` as template. Action-log style, not summary
   essay. Include signal totals across the full window, notable events with
   root causes, and any follow-ups that belong elsewhere (e.g. MAS-side
   fixes).
2. `./azure-deployment/batch-scale.sh down` unless Tero says otherwise.
3. Stop scheduling wakeups. If a straggler tick fires after the stop signal,
   acknowledge and don't run checks.

## Wrap-up notes to keep out of the log

- Memory peaks without alert firing aren't interventions — don't inflate
  the log.
- Timestamp-ms false positives aren't worth their own section. One-line
  footnote at most.
- Don't recommend code changes that came up as MAS-side issues. Point at
  them and move on.

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
  **Email delivery is DISABLED** (receiver removed 2026-04-17) — the alert
  only surfaces via the `monitorCondition` query below; nobody gets paged.
- Log Analytics workspace ID: `be17d63b-1807-49da-9846-82091ac8971d`.
- Capacity model (since 2026-07-17, image `0.9.2-render-gate`): each replica
  admits 2 concurrent full renders (RenderGate), queues ≤4 for ≤15s, then
  429 + Retry-After: 5. ACA scale rule `http-renders` (2 concurrent/replica)
  boots replicas to match load. **Warm-replica pinning is RETIRED** —
  `batch-scale.sh` is an emergency valve only, not a pre-batch step.

## Tick checks (run in parallel)

```bash
curl -s -o /dev/null -w "%{http_code}\n" $CRAWL4AI_API_URL/health
az monitor metrics alert show --name crawl4ai-memory-high --resource-group aitosoft-prod --query "{cond:monitorCondition, enabled:enabled}" -o json
az containerapp replica list --name crawl4ai-service --resource-group aitosoft-prod -o table
az monitor log-analytics query -w be17d63b-1807-49da-9846-82091ac8971d --analytics-query '<kusto>'
```

Kusto signal summary (20-min window), categorize by `case()`:
`GATE-429` (contains "RenderGate REJECT"),
`FORCE-CLOSE` (contains "Janitor reaped" or "force_close" or "FORCE-CLOSE"),
`OOM`/`MemoryError` (contains "refusing new browser"),
`FENCE-504` (contains "WALL-CLOCK FENCE 504"), `ACTIVE-REQ`,
`ADMIT` (contains "RenderGate ADMIT" — one INFO line per admitted render,
carries URL + queue wait; keep it out of OTHER),
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
| GATE-429 ("RenderGate REJECT") bursts at batch ramp-up | Replicas full; MAS client retries (5/10/20/30s) absorb while ACA scales out | **None** if replica count rises within ~1 min (check `SuccessfulRescale` events). Sustained 429s with replicas pegged at max = genuine capacity ceiling — talk to Tero about maxReplicas. |
| FENCE-504 ("WALL-CLOCK FENCE 504: url=… deadline_s=… elapsed_s=… gate=…") | 180s wall-clock fence fired and the render slot released cleanly (the gate snapshot in the line still counts the fenced request; it releases immediately after). One line per 504, with URL — deployed 0.9.2-fence-obs 2026-07-17. | Expect 0–10 per window during cold-ramp bursts, then zero. **Investigate only if they cluster POST-ramp** (replica count stable for >2 min and FENCE-504 still firing) or the rate grows across windows — that escalates tasks/done/504-fence-observability-2026-07-17.md to a code fix. Pair each with its "RenderGate ADMIT url=…" line to get the replica and queue wait. |
| PW-NAV-TIMEOUT ("Page.goto: Timeout 90000ms exceeded") | Playwright's own 90s nav timeout | **None.** Normal for slow/SPA sites. MAS pivots to static after 2 consecutive 504s per host. |
| OOM / MemoryError "refusing new browser" | **Our pool guard**, not OS-OOM. Replica hit ~85%+ and refused a new browser spawn. | Peek pool mem% timeline (`Pool: hot=… mem=…` log lines). If it drops back within ~5 min, no action — the guard worked. If it sticks >85% for 10+ min, restart the revision. |
| OTHER | Usually garbage. Log lines whose ms timestamp contains "504" (e.g. `02:17:04,504`) hit the regex. | Peek once per night to confirm, then ignore. |
| FORCE-CLOSE / "Janitor reaped" | Fix-2 Janitor killed a stuck slot | Investigate. If recurring, stuck-slot pattern from 2026-04-14 — restart or rollback. |
| ACTIVE-REQ counter not decreasing over multiple ticks | Stuck-slot pattern | **Rollback** to previous known-good image. |
| Pool mem% P99 > 95% sustained across 2+ 5min bins | Cluster approaching OS-OOM, guard overwhelmed | Restart revision. Single-bin spikes to 99% that recover next window are normal and self-healing. **Only count bins with `n >= 150` samples** — low-n P99 is outlier-sensitive and can misread late-arriving log data as a plateau (2026-04-17-evening lesson). Re-query on the next tick before acting. (April logs repeatedly flagged that the n≥150 gate was unreachable under 15 pinned replicas; moot since pinning was retired 2026-07-17 — replica counts now track load, and memory pressure is no longer the primary failure mode.) |

## Intervention thresholds

- Memory alert `Fired` (monitorCondition ≠ null/Resolved) → restart the
  current revision.
- Replica non-Running >10 min → restart.
- Sustained 504 rate on healthy Tier 1 hosts → restart.
- Stuck-slot pattern (force-close spam + active_requests stuck) → **rollback**
  to previous image via `az containerapp update --image …` (image-only swap;
  never touch env vars — that's MAS's token).

Don't restart just because of one OOM guard firing or one burst of Fix-1s.
Those are designed to self-heal.

## End of campaign

When Tero confirms all rows processed:
1. Write `tasks/done/overnight-intervention-log-YYYY-MM-DD.md` using
   `2026-04-14` or `2026-04-16` as template. Action-log style, not summary
   essay. Include signal totals across the full window, notable events with
   root causes, and any follow-ups that belong elsewhere (e.g. MAS-side
   fixes).
2. If warm replicas were pinned during the night (emergency valve),
   `./azure-deployment/batch-scale.sh down`. Normally nothing to unwind —
   scale-to-zero handles it.
3. Stop scheduling wakeups. If a straggler tick fires after the stop signal,
   acknowledge and don't run checks.

## Wrap-up notes to keep out of the log

- Memory peaks without alert firing aren't interventions — don't inflate
  the log.
- Timestamp-ms false positives aren't worth their own section. One-line
  footnote at most.
- Don't recommend code changes that came up as MAS-side issues. Point at
  them and move on.

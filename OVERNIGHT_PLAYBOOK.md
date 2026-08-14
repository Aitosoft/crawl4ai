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
- Log Analytics workspace `workspace-aitosoftprodnCsc`. The queries below use
  `$LAW_ID`; export it from `PRIVATE.md`, or re-derive it with
  `az monitor log-analytics workspace list --query "[?name=='workspace-aitosoftprodnCsc'].customerId | [0]" -o tsv`.
- Capacity model (since 2026-07-17, image `0.9.2-render-gate`): each replica
  admits 2 concurrent full renders (RenderGate), queues ≤4 for ≤15s, then
  429 + Retry-After: 5. ACA scale rule `http-renders` boots replicas; its
  trigger is **12 since 2026-08-14** (was 6; revision `--0000042`) and is **not**
  the same quantity as RenderGate's capacity of 2 (see
  `tasks/done/autoscaler-ratchets-to-the-cap.md`).
  **Warm-replica pinning is RETIRED** — `batch-scale.sh` is an emergency valve
  only, not a pre-batch step.
- **⚡ What the 2026-08-14 trigger change did to "normal", because it changes what
  a tick should alarm on.** The fleet now runs **2 replicas** on MAS's full sweep
  load, not 12. **A replica count of 2–3 under heavy traffic is correct**, not a
  scaling failure. `RenderGate REJECT` at ~1–2 % of requests is the designed price
  and MAS's retry ladder absorbs it. Slot utilisation is ~54 % against 7 % before.
  **The fleet will not surge for you** — one scale-up event in 30 minutes of real
  load, and a synthetic arm at 1.44× that rate held **1 replica for 12 minutes**
  through 38 rejections — so do not wait for replicas to appear as confirmation
  that a burst was handled. `tasks/done/trigger-12-readout-2026-08-14.md`.
  **The revert, if it is ever needed, is the trigger and NOT `--max-replicas`**
  (that was the command the cost file carried, and `maxReplicas` was already 20,
  so it is a no-op that reads as a successful revert at 03:00):
  `az containerapp update -n crawl4ai-service -g aitosoft-prod --scale-rule-name
  http-renders --scale-rule-type http --scale-rule-http-concurrency 6`, then edit
  `ACA_SCALE_TRIGGER` in `azure-deployment/deploy-image.sh` to match or the next
  deploy hard-fails. It creates a new revision: every replica restarts and every
  in-flight render dies. **Do not revert on a 429 rate alone** — split the two
  gates first, and only `RenderGate REJECT` is a capacity signal.
- **Watching a sweep after the 2026-08-08 scale change:** the number to read is
  the replica high-water against what the load justified, plus the 429 count.
  `ContainerAppHTTPLogs` is the only table with `RequestDuration`, and it also
  carries `StartTime` (= arrival) so true in-flight concurrency can be swept
  from overlaps rather than approximated by per-minute bins. Also check
  `ResponseFlags != "-"` and `UpstreamRequestAttemptCount > 1`: the 30-day
  baseline for both is 0 and 1 respectively, and a raced upstream close would
  appear there as **503/`UC`**, never as a 502.

## Tick checks (run in parallel)

```bash
curl -s -o /dev/null -w "%{http_code}\n" $CRAWL4AI_API_URL/health
az monitor metrics alert show --name crawl4ai-memory-high --resource-group aitosoft-prod --query "{cond:monitorCondition, enabled:enabled}" -o json
az containerapp replica list --name crawl4ai-service --resource-group aitosoft-prod -o table
az monitor log-analytics query -w "$LAW_ID" --analytics-query '<kusto>'
```

Kusto signal summary (20-min window), categorize by `case()`:
`GATE-429` (contains "RenderGate REJECT"),
`FORCE-CLOSE` (contains "Janitor reaped" or "force_close" or "FORCE-CLOSE"),
`OOM`/`MemoryError` (contains "refusing new browser"),
`FENCE-504` (contains "WALL-CLOCK FENCE 504"),
`ORIGIN-FAIL` (contains "ORIGIN FAILURE" — new in `0.9.2-failure-class`;
must be its own bucket, it is expected traffic and would otherwise flood
`OTHER`, which this file tells you to ignore),
`RENDER-DEFECT` (contains "RENDER DEFECT" — the collapse guard, new in
`0.9.2-detector-round3`. **Must be its own bucket**: it is logged at ERROR
level and would otherwise land in `OTHER`, which this file tells you to
ignore, and it is the one signal that means we are silently losing a
customer's page),
`ACTIVE-REQ`,
`ADMIT` (contains "RenderGate ADMIT" — one INFO line per admitted render,
carries URL + queue wait; keep it out of OTHER),
`PW-NAV-TIMEOUT` (Page.goto 90000), `FETCH` (contains "[FETCH]"),
`COMPLETE` (contains "[COMPLETE]"), `OTHER`.

**Do NOT use `contains "reap"`** for JANITOR — matches supervisord's
benign `reaped unknown pid … exit status 0` chatter and floods with
thousands of false positives (2026-04-17 lesson).

**New 2026-08-05: `ContainerAppHTTPLogs` — the ingress access log.** Enabled as
diagnostic setting `aca-http-logs` on the environment, HTTP category only. It is
the **only** surface that records a request the ingress handled without a
container — a cold-start 504, an ingress-terminated request, a 429 we never saw.
Console logs structurally cannot show these. **It has no history before
2026-08-05.** It is environment-wide, so filter by app.

**Column names checked against a real row 2026-08-06 — this table is
UNSUFFIXED.** No `_s` / `_d`, and duration is `RequestDuration` in
**milliseconds**. The earlier guesses (`StatusCode_d`, `ReplicaName_s`,
`DurationMs_d`, `ContainerAppName_s`) do not exist and fail with
`BadArgumentError: The request had some invalid properties`, which tells you
nothing about which column was wrong. Full schema: `Authority BytesReceived
BytesSent ConnectionId ContainerAppName EnvironmentName EnvoyContainerId
EnvoyPodName Location Method OperationName Path Protocol ReplicaName
RequestDuration RequestId ResponseCodeDetails ResponseFlags RevisionName
StartTime StatusCode TimeGenerated UpstreamHost UpstreamRequestAttemptCount
UserAgent XForwardedFor`.

```kusto
ContainerAppHTTPLogs
| where TimeGenerated > ago(20m)
| where ContainerAppName == "crawl4ai-service"
| summarize n=count(), p95_s=round(percentile(RequestDuration,95)/1000.0,2),
            max_s=round(max(RequestDuration)/1000.0,2)
    by StatusCode, ResponseFlags, no_container=isempty(ReplicaName)
```

Read it this way: **`no_container=true` (empty `ReplicaName`) means no container
ever saw the request** — that is the ingress answering alone, and it is the
cold-start-504 signal MAS asked about. `ResponseFlags` carries Envoy's reason.
A `StatusCode` here that has no matching console line is real and is *ours* to
explain; the reverse (console line, no HTTP log) just means the setting is newer
than the traffic.

**This is the instrument for "what did MAS actually receive".** The console-log
failure tokens count *results*; this counts *wire responses*, and the two answer
different questions. Segment 2 (2026-08-06) is the worked example: console
`RESULT FAILURE` showed 39 failures, while the wire showed 261 × 200, 12 × 500,
1 × 429 — because most failure classes are deliberately 200 + `success:false`.
Quoting console counts as if they were MAS's error rate overstates it ~3×.

Add pool-mem% percentile view — it surfaces near-OS-OOM single-replica
peaks the `refusing new browser` count alone doesn't explain.

**Keep the `by bin(...)` and never read a memory trend off the per-tick window
maximum.** A window maximum can only grow as the window grows, so consecutive
ticks manufacture a rising line out of flat data — this happened on 2026-08-06,
where "57.8 → 60.3 → 63.8 %" was reported as a creep across two ticks and the
binned view showed 26.5 → 57.8 → 48.5 → 60.3 → 63.8 → 52.8 → 25.3 %, i.e.
oscillating with load and then draining. Cross-check `hot=` in the same line: if
it never exceeds `render_capacity`, nothing is leaking. Full write-up in
`tasks/done/segment-2-counter-readout.md` §6.
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
| **An ingress 429 is NOT a RenderGate 429 — split the count before reading anything into it** | Two mechanisms emit 429, and the row above covers only one. `RenderGate REJECT` = concurrency. `refusing new browser` (`crawler_pool`) = the memory guard. **They have opposite fixes and the memory one is far larger in practice.** | Measured overnight 2026-08-09/10: **434 × 429 at the ingress, of which RenderGate rejected 25** — the other ~409 were the memory guard, at a true concurrency of **1.3** against ~26 render slots and replicas at **20 of 45**. Reading that as a capacity ceiling would have sent someone at `maxReplicas`, which was never the constraint. Count both tokens, always. |
| FENCE-504 ("WALL-CLOCK FENCE 504: url=… deadline_s=… elapsed_s=… gate=…") | 180s wall-clock fence fired and the render slot released cleanly (the gate snapshot in the line still counts the fenced request; it releases immediately after). One line per 504, with URL — deployed 0.9.2-fence-obs 2026-07-17. | Expect 0–10 per window during cold-ramp bursts, then zero. **Investigate only if they cluster POST-ramp** (replica count stable for >2 min and FENCE-504 still firing) or the rate grows across windows — that escalates tasks/done/504-fence-observability-2026-07-17.md to a code fix. Pair each with its "RenderGate ADMIT url=…" line to get the replica and queue wait. |
| ORIGIN-FAIL ("ORIGIN FAILURE: url=… failure_class=… error=…") | The origin broke, not us — the request returns **HTTP 200 with `success:false`** and a `failure_class`, by MAS's Q2 contract. New in `0.9.2-failure-class` (2026-07-30). | **None, and expect a lot of them at first.** This population used to be invisible: it arrived as our HTTP 500 and MAS retried it three times. Seeing it is the fix working. Investigate only if a *single host* dominates the bucket (worth telling MAS — it may be a dead customer site in their list) or if `failure_class=render_error` climbs, which is genuinely ours. **Read the next row too: this token is rarer than it looks.** |
| RESULT-FAIL ("RESULT FAILURE: url=… failure_class=… status=… error=…") | **Every failed *result* that is not a collapse** — origin blocks, origin 4xx/5xx, hosts that resolve but do not connect, downloads (`unrenderable_content`), our own render errors. New 2026-08-02. | Expect many; act only if one host dominates or `render_error` climbs. Sibling token **`TERMINAL FAILURE`** covers the exception path's non-origin permanent failures and its 504s; rare, so read it when it appears. **This row used to say "this is the row to count from, and ORIGIN-FAIL is not". That was wrong and it cost a real measurement — see the next row.** |
| **COUNTING FAILURES: key on `failure_class=`, never on the token** | Two disjoint tokens carry `failure_class`, on mutually exclusive code paths: `RESULT FAILURE` (`api.py:1033`, the result loop) and `ORIGIN FAILURE` / `TERMINAL FAILURE` (`api.py:1180`, `except Exception`). **No request can emit both.** | **Query `\| where Log_s contains "failure_class=origin_unreachable"`, not the token.** Measured 2026-08-06 on segment 2: `RESULT FAILURE` alone reported **9** `origin_unreachable` events on 6 domains; the truth was **21 on 13 companies**, because **12 of them — 57 % — were pre-admission DNS failures that only ever emit `ORIGIN FAILURE`**. The old advice was true for every class *except* the one whose dominant producer is the one thing that genuinely raises: `_normalize_and_validate_seeds` (`api.py:760`) runs **before** render admission, so a dead domain never reaches the result loop, never gets a `RenderGate ADMIT`, costs no render slot and no browser, and returns **200** at the ingress. Its marker text is `DNS: host does not resolve` (`api.py:698`) — distinctive enough to separate it from the connect-time kind. Cross-check any render count this way: **ingress `/crawl` requests − `RenderGate ADMIT` lines = pre-admission refusals + 429s**, which is how segment 2 reconciled to the request (274 − 261 = 12 + 1). |
| **A `failure_class` a query cannot see at all** | `render_mode: "static"` failed fetches log `[static] request error:` / `[static] timeout after` at **INFO with no `failure_class` field** (`aitosoft_static_mode.py:301,307`), yet `_static_error_result` defaults the class to `origin_unreachable` (`:164-179`). | **No `failure_class` query can ever count these.** Matters because MAS pivots a host to static after repeated failures, so this hole opens exactly when a host is already misbehaving. Streaming's pre-admission DNS path logs nothing at all (`api.py:1325-1334`) — low value, MAS never streams. Both recorded in `tasks/done/segment-2-counter-readout.md`. |
| RENDER-DEFECT ("RENDER DEFECT: url=… content collapsed in our parse: N chars of visible text …, 0 chars of markdown out; html2text recovered N chars") | Our parse lost the whole body **and the html2text fallback could not get it back**. Served as **HTTP 200 + result `success:false` + `failure_class: render_defect`**, content attached, zero retries. Deployed `0.9.2-detector-round3` 2026-08-01; narrowed to "unrecovered only" in `0.9.2-collapse-recovery` 2026-08-02. | **Record the URLs — do not intervene.** It is already the correct outcome for a page we cannot parse, and no restart or rollback changes it. **Read the trailing char count, it is the diagnosis:** `recovered 0 chars` means html2text agreed the page was empty (the comment/script family); anything above 0 is a *partial* recovery we declined to serve as a success, which is a different and more interesting finding. **MAS cannot see this class at all** — a page with no contacts looks like a page that has no contacts — so their "all clean" is not a cross-check. |
| COLLAPSE-RECOVERED ("COLLAPSE RECOVERED: url=… content collapsed in our parse: …; recovered N chars via html2text") | Same collapse, but the html2text fallback returned the body. Served as an **ordinary success** — `failure_class: none` — carrying the recovered markdown. New in `0.9.2-collapse-recovery` 2026-08-02. | **None. This is data we used to lose.** Count it, do not act on it. **The 2026-08-01 baseline of 2.7 % of pages / 18 % of hosts (9 URLs of 328) is now the sum of these two tokens, not RENDER DEFECT alone** — the tokens are deliberately disjoint strings so the split is countable, but a drop in RENDER DEFECT on its own no longer means what it used to. The split itself is the measurement worth reporting: it is the first real-traffic evidence of which collapse mechanism our 7 affected hosts actually hit, which is still unknown. |
| MAS success rate drops after 2026-07-30 | Not a log signal — expect it in MAS's own counters | **Do not roll back for this.** Challenge screens, redirect-blocked hosts and origin 5xx all used to be stored as successes. They now fail honestly. `AITOSOFT_CHANGES.md` 2026-07-30 entry has the expected direction. |
| PW-NAV-TIMEOUT ("Page.goto: Timeout 90000ms exceeded") | Playwright's own 90s nav timeout | **None.** Normal for slow/SPA sites. MAS pivots to static after 2 consecutive 504s per host. |
| OOM / MemoryError "refusing new browser" | **Our pool guard**, not OS-OOM. Replica hit ~85%+ and refused a new browser spawn. | Peek pool mem% timeline (`Pool: hot=… mem=…` log lines). If it drops back within ~5 min, no action — the guard worked. ~~If it sticks >85% for 10+ min, restart the revision.~~ **DO NOT restart on this alone — corrected 2026-08-10.** The overnight sweep sat above 85 % for ~15 hours and a restart would have been wrong every time: at 420 refusal events the guard read **88.7 %** while true `anon` was **68.6 %**, the rest being **583 MB of reclaimable active page cache**. **Read `anon=` in the same line, not the percentage.** Escalate on `anon` ≥85 %, an `OOMKilled`, or an exit 137 — none of which have ever been seen. `tasks/memory-guard-charges-reclaimable-page-cache.md` |
| OTHER | Usually garbage. Log lines whose ms timestamp contains "504" (e.g. `02:17:04,504`) hit the regex. | Peek once per night to confirm, then ignore. |
| FORCE-CLOSE / "Janitor reaped" | Fix-2 Janitor killed a stuck slot | Investigate. If recurring, stuck-slot pattern from 2026-04-14 — restart or rollback. |
| ACTIVE-REQ counter not decreasing over multiple ticks | Stuck-slot pattern | **Rollback** to previous known-good image. |
| Pool mem% P99 > 95% sustained across 2+ 5min bins | ~~Cluster approaching OS-OOM, guard overwhelmed~~ — **not on its own, corrected 2026-08-10.** Overnight ran p95 92–93 % with max 100 % for 15 h, zero OOM kills, at a true `anon` of ~69 %. **The percentile is also biased upward**: the janitor samples every 10 s above 80 % and 60 s below 60 %, oversampling high states ~6× (measured overstatement 5.3×). `max` and event *counts* are unbiased; percentiles are not | ~~Restart revision.~~ **Confirm on `anon=` first, then restart only if `anon` is the thing that is high.** Single-bin spikes to 99% that recover next window are normal and self-healing. **Only count bins with `n >= 150` samples** — low-n P99 is outlier-sensitive and can misread late-arriving log data as a plateau (2026-04-17-evening lesson). Re-query on the next tick before acting. (April logs repeatedly flagged that the n≥150 gate was unreachable under 15 pinned replicas; moot since pinning was retired 2026-07-17 — replica counts now track load, and memory pressure is no longer the primary failure mode.) |

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

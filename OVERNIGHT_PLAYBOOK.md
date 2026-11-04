# Overnight Monitoring Playbook

When Tero says "monitor overnight", "I'm AFK, watch the service" or similar,
read this file and loop with `ScheduleWakeup`. Do not self-start.

This file is the tick loop and the decisions. Everything about Azure itself —
instruments, query traps, what a number means and where it came from — is in
`AZURE_OPERATIONS.md`, cited below as §n. Read §5.3 (query traps) before writing
any query of your own.

## Before the first tick

1. **Read live state** (§0): image, revision, trigger, replica bounds. Note the
   current image tag, then pick a rollback target from the ACR tag list using
   §2.5's tag caveats. Not simply the next tag down: an adjacent tag can be
   functionally identical to the running image, or burned. Never derive the
   target from prose.
2. **Set up the shell:**
   ```bash
   set -a; source .env; set +a      # CRAWL4AI_API_URL, CRAWL4AI_API_TOKEN
   export LAW_ID=$(az monitor log-analytics workspace list \
     --query "[?name=='workspace-aitosoftprodnCsc'].customerId | [0]" -o tsv)
   export APP_ID=$(az containerapp show -n crawl4ai-service-se -g aitosoft-prod --query id -o tsv)
   ```
3. **Know what a healthy sweep looks like** (below, and §5.6), so you do not
   report normal behaviour as an anomaly.

## What normal looks like at trigger 12

Trigger 12 ran for the last 54 h of the final sweep (from 2026-08-14). Figures
that do not depend on the trigger are whole-sweep (2026-08-09 → 08-16, 186,178
requests). §5.6 has the table, §3.8 the per-regime 429 split.

- **Fleet: 2 replicas** (occasionally 1 or 3) under August's sweep load (~19 requests/min); 3 at
  the ~32/min of the 2026-11-04 joint runs (AZURE_OPERATIONS §4.5). That is where the scaler
  settles, not a configured floor (`minReplicas` is 0). The fleet will
  not surge for you; do not wait for replicas to appear as proof a burst was
  handled (§3.7).
- **429s: ~6 % of requests** (6.5 % in a matched 32-minute window right after the
  change, `tasks/done/trigger-12-readout-2026-08-14.md` §1). At trigger 12, 88 %
  are the memory guard (`capacity_gate: "memory"`) and 12 % RenderGate: 4,485 and
  613 over the 54 h, i.e. on average **~28 `MEM-REFUSE` and ~4 `GATE-429` per
  20-minute tick**, the RenderGate ones clustered at batch starts (§3.8). MAS's
  retries absorb them.
- **5xx: ~0.7 %** (0.68 % in the trigger-6 opening, 0.69 % across the sweep). MAS's accounting (§5.6) makes **a 5xx
  ~5× more expensive to them than a 429.** Loud and cheap (429) versus quiet and
  dear (5xx): put your attention on the 5xx.
- **504: zero.** Any 504 is abnormal.
- **Container restarts: 34 in the 53 h trigger-12 window**, about one every
  90 minutes (74 across the sweep), most unlabelled; memory kills self-heal in
  seconds (§6.2).
- **`ReplicaUnhealthy`: thousands**, all probes failing during start and stop
  (§6.5). Noise.
- **Failed results are mostly the origin's**: 95 % of MAS's failures were dead
  domains, 404s and blocks (§5.6).

## Cadence

- Active campaign: `ScheduleWakeup delaySeconds=1200` (20 min).
- Idle or between batches: `1800`.
- Never `300` — the worst of both worlds on cache.

## Tick checks (run in parallel)

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$CRAWL4AI_API_URL/health"
# Restarts: sum the series, never sample one bin (§5.3)
az monitor metrics list --resource "$APP_ID" --metric RestartCount --interval PT1M --aggregation Total -o json
# Per-replica view; -o table hides restartCount
az containerapp replica list -n crawl4ai-service-se -g aitosoft-prod -o json \
  --query "[].{name:name, created:properties.createdTime, restarts:properties.containers[].restartCount}"
az monitor log-analytics query -w "$LAW_ID" --analytics-query '<kusto>' -o json   # always -o json
```

**Never run `az containerapp logs show` as a tick on an idle app** — it cold-starts
the app, bills for its own observation, and keeps it from reaching zero (§6.5).

The three queries a tick runs (all verified 2026-11-03). Use a 20-minute window to
match the cadence.

```kusto
// 1. Wire: what MAS received (§5.4 explains via_activator and ResponseFlags)
ContainerAppHTTPLogs
| where TimeGenerated > ago(20m)
| where ContainerAppName == "crawl4ai-service-se"
| summarize n=count(), p95_s=round(percentile(toreal(RequestDuration),95)/1000.0,2),
            max_s=round(max(toreal(RequestDuration))/1000.0,2)
    by StatusCode, ResponseFlags, ResponseCodeDetails, via_activator=isempty(ReplicaName)
```

```kusto
// 2. Console signals — indexof, never contains (contains is term-based, §5.3)
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(20m)
| where ContainerAppName_s == "crawl4ai-service-se"
| extend sig = case(
    indexof(Log_s, "RenderGate REJECT") >= 0,            "GATE-429",
    indexof(Log_s, "Memory pressure:") >= 0,             "MEM-REFUSE",
    indexof(Log_s, "Browser cap reached") >= 0,          "CAP-REFUSE",
    indexof(Log_s, "FORCE-CLOSING stuck browser") >= 0,  "STUCK-SLOT",
    indexof(Log_s, "WALL-CLOCK FENCE 504") >= 0,         "FENCE-504",
    indexof(Log_s, "RENDER DEFECT") >= 0,                "RENDER-DEFECT",
    indexof(Log_s, "COLLAPSE RECOVERED") >= 0,           "COLLAPSE-RECOVERED",
    indexof(Log_s, "RESULT FAILURE") >= 0,               "RESULT-FAIL",
    indexof(Log_s, "ORIGIN FAILURE") >= 0,               "ORIGIN-FAIL",
    indexof(Log_s, "TERMINAL FAILURE") >= 0,             "TERMINAL-FAIL",
    indexof(Log_s, "RenderGate ADMIT") >= 0,             "ADMIT",
    indexof(Log_s, "supervisord started with pid") >= 0, "CONTAINER-START",
    "OTHER")
| where sig != "OTHER"
| summarize n=count() by sig
```

```kusto
// 3. Failures by class — count failure_class=, never the token (§5.3)
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(20m)
| where ContainerAppName_s == "crawl4ai-service-se"
| where indexof(Log_s, "RESULT FAILURE") >= 0 or indexof(Log_s, "ORIGIN FAILURE") >= 0
     or indexof(Log_s, "TERMINAL FAILURE") >= 0
| extend failure_class = extract(@"failure_class=(\w+)", 1, Log_s),
         host = extract(@"url=https?://([^/ ]+)", 1, Log_s)
| summarize n=count(), hosts=dcount(host) by failure_class
```

Add the §5.4 pool-memory query only when you need to explain a restart — memory
readings do not predict kills (§6.4). Run each query again on the next tick before
acting on it: ingestion lags several minutes.

**Leak check, when you do read the `📊 Pool:` line:** `hot=` staying at or below
`render_capacity` means browsers are not accumulating (it held through segment 2,
2026-08-06). The converse does not hold: `hot=` counts every browser used three or
more times and keeps it until it has sat idle for 2 × `idle_ttl_sec` (the
janitor's hot TTL, `crawler_pool.py`), in use or not, so with MAS's per-company
identities it can exceed 2 with nothing in flight. A real leak is `hot`+`cold` that does not fall
when load falls, or `STUCK-SLOT`.

## Signals and what to do

| Signal | Meaning | Action |
|---|---|---|
| `GATE-429` / `capacity_gate: render_slots` | A replica's 2 slots and 4-deep queue are full. Clusters at batch start, while the fleet is 1 replica (§3.8) | None. MAS retries. If cold-start 429s ever cost real captures, the lever is `minReplicas`, not `maxReplicas` or the trigger. **Exception: sustained `render_slots` 429s with the fleet pegged at `maxReplicas` (§0) are a genuine capacity ceiling — flag it for Tero.** Raising `maxReplicas` is his call, bounded by the shared core quota (§3.6); memory 429s never count towards this |
| `MEM-REFUSE` / `capacity_gate: memory` | The pool's memory guard. Its threshold sits inside its own signal, so the count measures nothing about memory (§6.4) | Count it; never interpret it, never restart on it |
| `CAP-REFUSE` / `capacity_gate: browser_pool` | The `max_browsers` cap with nothing idle to evict | Has never fired (0 in 186,178). Note the first instance |
| `FENCE-504` | The 180 s fence fired and released the slot. One line per 504, with URL | Zero is normal. A few during a cold ramp are tolerable; investigate if they cluster after the fleet has settled or grow tick over tick. Pair each with its `RenderGate ADMIT` line for replica and queue wait |
| `RESULT-FAIL` / `ORIGIN-FAIL` / `TERMINAL-FAIL` | Failed results, origin faults at HTTP 200 + `success:false` | Expected traffic. Act only if one host dominates (tell MAS — likely a dead site in their list) or `render_error` climbs, which is ours |
| `RENDER-DEFECT` | Our parse lost the body and html2text could not recover it: 200 + `failure_class: render_defect`, not retried. MAS cannot see this class at all | Record the URLs; do not intervene. The trailing `recovered N chars` is the diagnosis: 0 means the page really yielded nothing, above 0 is a partial recovery we declined |
| `COLLAPSE-RECOVERED` | The same collapse, recovered and served as a normal success | Count only. This is data we used to lose |
| `STUCK-SLOT` | The janitor force-closed a browser whose request slot leaked (the 2026-04-14 pattern) | Investigate. If it recurs, roll back the image |
| `CONTAINER-START` / `RestartCount` rises | A container restarted. Isolated memory kills carry no label (§6.2); replica `createdTime` does not move (§6.3) | Check whether pages were lost around it (5xx, `ResponseFlags`). Do not restart anything |
| Wire: `ResponseFlags != "-"` or `UpstreamRequestAttemptCount > 1` | The ingress could not get an answer from a container. 2 in the whole sweep | Worth reporting if it recurs |
| Wire: empty `ReplicaName` (`via_activator=true`) | Requests buffered by the activator during scale-from-zero | Not a failure |
| Memory alert, high pool `mem=`, high `anon=` | No reading predicts a kill, and the alert pages nobody (§5.5, §6.4) | No action on a reading alone |
| `Page.goto: Timeout … exceeded` | A slow origin | None |

## Intervention thresholds

Intervene only when pages are being lost now. In particular, never on a memory
reading, the memory alert, a refusal count, a 429 rate, or a single OOM — those
self-heal.

- **The one exception, where you act before pages are lost: `origin_blocked`
  climbing segment over segment** (query 3; hour over hour if the sweep has no
  segments). That is IP-reputation decay on our shared egress (AZURE_OPERATIONS §7)
  — blocks are IP-based, not fingerprint-based — and every further request deepens
  it. **Stop the sweep**: tell MAS's session directly (CLAUDE.md §Cross-repo), and
  Tero. Nothing on our side repairs an address's reputation. A rise confined to one host is that host, so read query
  3's `hosts` before calling it reputation. Baselines: 0 in segment 1 (August
  2026); 2 in a 632-request trigger-12 window (2026-08-14).
- **Replica non-Running for > 10 min → restart the revision.** "All replicas
  Running" is not evidence nothing crashed (§6.3).
  ```bash
  az containerapp revision restart -n crawl4ai-service-se -g aitosoft-prod \
    --revision "$(az containerapp show -n crawl4ai-service-se -g aitosoft-prod --query properties.latestRevisionName -o tsv)"
  ```
- **Sustained 504s on healthy hosts → restart.**
- **Stuck-slot pattern** (repeated `STUCK-SLOT`, with fence 504s or queue pressure
  that does not clear) → **roll back the image**, image only (§2.5):
  ```bash
  az containerapp update -n crawl4ai-service-se -g aitosoft-prod \
    --image aitosoftacr.azurecr.io/crawl4ai-service:<rollback-tag>
  ```
  **Never `deploy-image.sh <older-tag>`**: it rebuilds today's tree under that
  tag, overwriting the good image, and ships it. Never set env vars — that is how
  MAS's token gets broken.
- **Do not change the scale rule at night.** It mints a revision that kills every
  in-flight render, and the trigger has no tested value between 6 and 12 (§3.5).

## End of campaign

When Tero confirms all rows are processed:

1. Write `tasks/done/overnight-intervention-log-YYYY-MM-DD.md`, using
   `2026-04-14` or `2026-04-16` as the template: an action log, not an essay.
   Include signal totals for the whole window, notable events with root causes,
   and follow-ups that belong elsewhere (e.g. MAS-side fixes).
2. **Archive the aggregates you will want later into that log** — wire status
   counts, 429s by `capacity_gate`, restarts, failures by class, replica-hours from
   the `Replicas` metric (§4.4). Log Analytics keeps 30 days and the August sweep's
   logs are already gone (§5.1).
3. If warm replicas were pinned (`batch-scale.sh up`), run
   `./azure-deployment/batch-scale.sh down`. Normally nothing to unwind.
4. Stop scheduling wakeups. If a straggler tick fires after the stop, acknowledge
   it and run nothing.

## Keep out of the log

- Memory peaks are not interventions; log one only if something was lost.
- Do not recommend code changes for issues that turned out to be MAS-side; point
  at them and move on.

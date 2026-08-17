# Overnight Monitoring Playbook

Claude-for-Claude. When Tero says "monitor overnight" / "I'm AFK, watch the
service" / similar, read this file and use `ScheduleWakeup` to loop.

## When to engage

- Active MAS campaign (typically 1–5 parallel WAA agents, hundreds–thousands of
  companies over several hours).
- User explicitly hands off monitoring. Don't self-start.

## Service facts

- Endpoint in `.env` as `CRAWL4AI_API_URL` + `CRAWL4AI_API_TOKEN`.
- Image is whatever's currently deployed — `az containerapp show --query
  properties.template` **beats every document in this repo**, including the one
  named next. Previous known-good image is the one before current;
  `AITOSOFT_CHANGES.md`'s most-recent entry is the usual source but **has been a
  revision behind before**, so at 03:00 confirm the *current* tag from Azure first
  and derive "previous" from `az containerapp revision list`, not from prose.
  Note also that a new revision is not necessarily a new image — `--0000042` was a
  scale-rule change on an unchanged image.
- Resource group: `aitosoft-prod`. Container app: `crawl4ai-service`.
- ⛔ **Memory alert `crawl4ai-memory-high` currently carries no information. Do
  not build a check on it.** This bullet used to say "(85%, sustained 5 min,
  severity 2). **Email delivery is DISABLED** (receiver removed 2026-04-17) — the
  alert only surfaces via the `monitorCondition` query below; nobody gets paged."
  The threshold is right; everything after it is wrong in a way that mattered.
  Measured 2026-08-16:
  - It fired **32 times / 170.8 hours in the last 30 days**, longest single
    episode **52 hours continuous**. That is not an event, it is the weather.
  - Action group `crawl4ai-oncall` has **zero receivers of every kind** —
    `email`, `sms`, `webhook`, `armRole`, `azureAppPush` are all `[]`. Not "a
    removed email receiver": nothing is wired at all, by any channel.
  - **`monitorCondition` is not a field of the `metricAlerts` resource.** The
    `az monitor metrics alert show --query "{cond:monitorCondition…}"` this file
    prescribed in Tick checks returns `null` **unconditionally, forever** — a
    check that cannot fail and therefore cannot inform. Fired instances live in
    `Microsoft.AlertsManagement`; the working call is in Tick checks below.
  - What it reads is platform `MemoryPercentage`
    (`azure-deployment/setup-memory-alert.sh:62`, `--condition "max
    MemoryPercentage > 85"`) = `WorkingSetBytes / limit` — the **same working-set
    definition** as our own `get_container_memory_percent`, except Azure divides
    by ~3.92 GiB allocatable so it reads ~2.2 points higher. **So this is a
    second instance of "the threshold is drawn through the middle of its own
    signal"**, the defect this file already documents for the pool guard (the two
    memory rows in the table). Fixing delivery *without* moving the threshold
    would page continuously — that is the whole reason it is unwired.
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
  scaling failure. `RenderGate REJECT` is the designed price and MAS's retry
  ladder absorbs it — ⛔ this bullet said "~1–2 % of requests"; the sweep measured
  **0.35 %** (660 of 186,178), because the *ingress* 429 rate of 5.66 % is
  overwhelmingly the memory guard, not the gate (next bullet, and the two 429
  rows in the table). Slot utilisation is ~54 % against 7 % before.
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
- **What a whole sweep looks like when nothing is wrong** — the final WAA sweep,
  2026-08-09 → 2026-08-16, read end to end: **186,178 `/crawl` requests**,
  **93.6 % × 200**, **5.66 % × 429** (of which **~94 % is the pool's memory guard,
  not RenderGate**), **0.69 % × 5xx**. Mean true concurrency **1.68**. Fleet flat
  at **2 replicas for 97 %** of the post-08-14 window. **Total measured harm: 2
  lost pages**, both from the one moment when both replicas restarted together.
  MAS's own terminal-outcome accounting for the same window: our 429s cost them
  **29 captures**, our 500s cost them **156** — so **a 5xx is ~5× more expensive
  to them than a 429**, which is the opposite of where a tick's attention
  naturally goes (429s are loud and cheap; 5xx are quiet and dear). Use these as
  the reference bands before reporting anything as anomalous.
- **Watching a sweep after the 2026-08-08 scale change:** the number to read is
  the replica high-water against what the load justified, plus the 429 count.
  `ContainerAppHTTPLogs` is the only table with `RequestDuration`, and it also
  carries `StartTime` (= arrival) so true in-flight concurrency can be swept
  from overlaps rather than approximated by per-minute bins. Also check
  `ResponseFlags != "-"` and `UpstreamRequestAttemptCount > 1`: **this pair is
  the genuine "the ingress could not get an answer from a container" signal**,
  and it is extraordinarily rare — across the whole final sweep's 186,178
  requests there were **2**, both `503` / `ResponseFlags URX,UF` /
  `ResponseCodeDetails upstream_reset_before_response_started`;
  `UpstreamRequestAttemptCount > 1` still never fired. A raced upstream close
  appears here as **503/`UC`**, never as a 502. **Do not substitute an empty
  `ReplicaName` for this** — see the `ContainerAppHTTPLogs` section below; that
  field reads the activator, not a failure.

## Tick checks (run in parallel)

```bash
# Both ids below are derivable — nothing here needs PRIVATE.md:
#   SUB=$(az account show --query id -o tsv)
#   APP_ID=$(az containerapp show -n crawl4ai-service -g aitosoft-prod --query id -o tsv)
curl -s -o /dev/null -w "%{http_code}\n" $CRAWL4AI_API_URL/health
# Fired alert instances. The `az monitor metrics alert show --query
# "{cond:monitorCondition…}"` this block used to carry is a permanent `null` —
# monitorCondition is not a field of that resource (see Service facts).
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&timeRange=30d"
# Restarts in one call — no ContainerStarted sifting needed. $APP_ID = the
# container app's resource id. Sum the series, never sample a bin (see below).
az monitor metrics list --resource "$APP_ID" --metric RestartCount --interval PT1M --aggregation Total -o json
# `-o table` hides the field that answers "did anything crash".
az containerapp replica list --name crawl4ai-service --resource-group aitosoft-prod -o json \
  --query "[].{name:name, created:properties.createdTime, restarts:properties.containers[].restartCount}"
az monitor log-analytics query -w "$LAW_ID" --analytics-query '<kusto>' -o json
```

**`-o json`, never `-o tsv`, on `az monitor log-analytics query`.** It orders
columns **alphabetically**, not in the order the query projects them. A tick that
reads positionally silently transposes its own numbers and reports them with full
confidence. Key by name.

**`RestartCount` caveats, both load-bearing.** ACA emits the metric only every
5 minutes, so at `PT1M` it reads 0 four minutes in five — **sum the series, never
sample a bin**; and it is cumulative per replica, so a replica appearing
mid-window brings its history with it. Cross-checked over the final sweep: **74
restarts** (40 before the 08-14 trigger change, 34 after), matching an
independent count of console `supervisord started with pid 1` lines **exactly**.

**Never run `az containerapp logs show` as a tick check on an idle app.**
Verified 2026-08-16: on a scaled-to-zero app it fires `KEDAScaleTargetActivated`
0→1 with **zero ingress requests**, ~13 s before the connect. **The tick then
bills for its own observation**, and the app never reaches zero between
campaigns. Log Analytics reads stored data and has no such effect — use it for
everything that is not a live tail you actually need.

Kusto signal summary (20-min window), categorize by `case()` — **but read the
operator note below before you write `contains` into any of these**:
`GATE-429` ("RenderGate REJECT"),
`FORCE-CLOSE` ("Janitor reaped" or "force_close" or "FORCE-CLOSE"),
`MEM-REFUSE` ("💥 Memory pressure:") and `CAP-REFUSE` ("🚧 Browser cap reached")
— **two buckets, not one**: both emit the shared substring `refusing new
browser`, from `crawler_pool.py:425`/`:432` and `:468` respectively, and they are
different mechanisms with opposite fixes (see the two 429 rows in the table),
`FENCE-504` ("WALL-CLOCK FENCE 504"),
`ORIGIN-FAIL` ("ORIGIN FAILURE" — new in `0.9.2-failure-class`;
must be its own bucket, it is expected traffic and would otherwise flood
`OTHER`, which this file tells you to ignore),
`RENDER-DEFECT` ("RENDER DEFECT" — the collapse guard, new in
`0.9.2-detector-round3`. **Must be its own bucket**: it is logged at ERROR
level and would otherwise land in `OTHER`, which this file tells you to
ignore, and it is the one signal that means we are silently losing a
customer's page),
`ACTIVE-REQ`,
`ADMIT` ("RenderGate ADMIT" — one INFO line per admitted render,
carries URL + queue wait; keep it out of OTHER),
`PW-NAV-TIMEOUT` (Page.goto 90000), `FETCH` ("[FETCH]"),
`COMPLETE` ("[COMPLETE]"), `OTHER`.

**Do NOT use `contains "reap"`** for JANITOR — matches supervisord's
benign `reaped unknown pid … exit status 0` chatter and floods with
thousands of false positives (2026-04-17 lesson).

**⛔ `contains` on a `_CL` text column is TERM-based. It does NOT mean "this
substring appears."** This is the worst measurement trap found in the whole
sweep review, and every bucket above is subject to it. Kusto tokenizes `Log_s`
into terms, and `contains` — like `has` — matches the *terms*, in any order,
anywhere in the row. Measured 2026-08-16 on `ContainerAppConsoleLogs_CL`:

| predicate on `Log_s` | rows | what it actually did |
|---|---|---|
| `contains "CONSENT STRUCTURAL"` | **383** | matched ordinary `CONSENT DECLINED … structural=False` lines — both words present, separately |
| `has "CONSENT STRUCTURAL"` | **383** | same |
| `contains_cs "CONSENT STRUCTURAL"` | **0** | correct |
| `indexof(Log_s, "CONSENT STRUCTURAL") >= 0` | **0** | correct |

The true count is **0**. The term-based read produced a **false refutation of a
correct claim** — 383 phantom events that then had to be explained away, and the
explanation was nearly "the 120-name census is wrong".

**Use `indexof(Log_s, "…") >= 0` for every multi-word token**: `RenderGate
REJECT`, `RenderGate ADMIT`, `ORIGIN FAILURE`, `RESULT FAILURE`, `TERMINAL
FAILURE`, `RENDER DEFECT`, `COLLAPSE RECOVERED`, `WALL-CLOCK FENCE 504`, `Janitor
reaped`, `refusing new browser`, `Memory pressure`, `Browser cap reached`. It
gets no free-text-index acceleration, so it is slower — irrelevant at these
volumes, and a slow correct number beats a fast wrong one. The failure is
**silent and directional**: it can only over-count, and it over-counts most on
exactly the rare tokens a tick is looking for. `contains` was verified harmless
where the terms co-occur nowhere else — `RenderGate ADMIT` returned **184,404
under both operators** across the sweep — but you cannot know that in advance,
which is why the rule is unconditional rather than case-by-case.

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
    by StatusCode, ResponseFlags, ResponseCodeDetails, via_activator=isempty(ReplicaName)
```

⛔ **This paragraph used to read: "`no_container=true` (empty `ReplicaName`) means
no container ever saw the request — that is the ingress answering alone, and it
is the cold-start-504 signal MAS asked about." That is false**, and it sends you
hunting an ingress failure that did not happen. Measured across the final sweep:
**29 requests with an empty `ReplicaName`, 22 of them `StatusCode 200` with
`ResponseCodeDetails = via_upstream`** — which by definition means an upstream
container *did* answer. All 29 carry `UpstreamHost 100.100.248.100:4045`, the
**ACA activator** (a fixed address, not a pod IP), and every one lands on a
`KEDAScaleTargetActivated` moment. They are requests **buffered during
scale-from-zero**: the field is empty because the activator, not a replica,
terminated the ingress hop. Read them as a cold-start marker if you like; never
as a failure. (Hence the alias rename above — `no_container` encoded the wrong
claim in the output a tick reads.)

**The genuine "the ingress could not reach a container" signal is
`ResponseFlags` / `ResponseCodeDetails`, and it is vanishingly rare:** **2** rows
in 186,178 (`503` / `URX,UF` / `upstream_reset_before_response_started`). That
pair is what to alarm on. `ResponseFlags` carries Envoy's reason.
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
| where indexof(Log_s, "Pool:") >= 0 and indexof(Log_s, "mem=") >= 0  // not `contains` — see the operator note above
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
| **An ingress 429 is NOT a RenderGate 429 — split the count before reading anything into it** | Two mechanisms emit 429, and the row above covers only one. `RenderGate REJECT` (`aitosoft_admission.py:135,154`) = concurrency. The pool's `refusing new browser` = memory. **They have opposite fixes and the memory one is far larger in practice.** | Measured overnight 2026-08-09/10: **434 × 429 at the ingress, of which RenderGate rejected 25** — the other ~409 were the memory guard, at a true concurrency of **1.3** against ~26 render slots and replicas at **20 of 45**. Reading that as a capacity ceiling would have sent someone at `maxReplicas`, which was never the constraint. Whole final sweep, same shape: **5.66 % of 186,178 requests were 429, ~94 % of them the memory guard**. Count both tokens, always. |
| **…and `refusing new browser` is itself THREE call sites, not one** | New 2026-08-16. `crawler_pool.py` emits that substring from the **memory guard** (`:425`, `:432`) *and* from the **`max_browsers` cap** (`:468`). Counting the shared substring conflates two mechanisms whose fixes point in opposite directions — the memory one says "the meter is wrong / bound the allocation", the cap one says "raise `max_browsers`". | **Split on the distinctive text: `💥 Memory pressure:` vs `🚧 Browser cap reached`.** Over the final sweep: memory **9,876**, browser cap **0**. So the cap has never once bound, and every pool 429 in this service's history is the memory guard — which also means "raise `max_browsers`" has never been the indicated fix, and a merged count could have made it look like it was. |
| FENCE-504 ("WALL-CLOCK FENCE 504: url=… deadline_s=… elapsed_s=… gate=…") | 180s wall-clock fence fired and the render slot released cleanly (the gate snapshot in the line still counts the fenced request; it releases immediately after). One line per 504, with URL — deployed 0.9.2-fence-obs 2026-07-17. | Expect 0–10 per window during cold-ramp bursts, then zero. **Investigate only if they cluster POST-ramp** (replica count stable for >2 min and FENCE-504 still firing) or the rate grows across windows — that escalates tasks/done/504-fence-observability-2026-07-17.md to a code fix. Pair each with its "RenderGate ADMIT url=…" line to get the replica and queue wait. |
| ORIGIN-FAIL ("ORIGIN FAILURE: url=… failure_class=… error=…") | The origin broke, not us — the request returns **HTTP 200 with `success:false`** and a `failure_class`, by MAS's Q2 contract. New in `0.9.2-failure-class` (2026-07-30). | **None, and expect a lot of them at first.** This population used to be invisible: it arrived as our HTTP 500 and MAS retried it three times. Seeing it is the fix working. Investigate only if a *single host* dominates the bucket (worth telling MAS — it may be a dead customer site in their list) or if `failure_class=render_error` climbs, which is genuinely ours. **Read the next row too: this token is rarer than it looks.** |
| RESULT-FAIL ("RESULT FAILURE: url=… failure_class=… status=… error=…") | **Every failed *result* that is not a collapse** — origin blocks, origin 4xx/5xx, hosts that resolve but do not connect, downloads (`unrenderable_content`), our own render errors. New 2026-08-02. | Expect many; act only if one host dominates or `render_error` climbs. Sibling token **`TERMINAL FAILURE`** covers the exception path's non-origin permanent failures and its 504s; rare, so read it when it appears. **This row used to say "this is the row to count from, and ORIGIN-FAIL is not". That was wrong and it cost a real measurement — see the next row.** |
| **COUNTING FAILURES: key on `failure_class=`, never on the token** | Two disjoint tokens carry `failure_class`, on mutually exclusive code paths: `RESULT FAILURE` (`api.py:1033`, the result loop) and `ORIGIN FAILURE` / `TERMINAL FAILURE` (`api.py:1180`, `except Exception`). **No request can emit both.** | **Query `\| where indexof(Log_s, "failure_class=origin_unreachable") >= 0`, not the token** (`contains` is term-based and would match any line carrying those four terms separately — see the operator note above). Measured 2026-08-06 on segment 2: `RESULT FAILURE` alone reported **9** `origin_unreachable` events on 6 domains; the truth was **21 on 13 companies**, because **12 of them — 57 % — were pre-admission DNS failures that only ever emit `ORIGIN FAILURE`**. The old advice was true for every class *except* the one whose dominant producer is the one thing that genuinely raises: `_normalize_and_validate_seeds` (`api.py:760`) runs **before** render admission, so a dead domain never reaches the result loop, never gets a `RenderGate ADMIT`, costs no render slot and no browser, and returns **200** at the ingress. **⛔ Two instruments this row prescribed are wrong — corrected 2026-08-16, both found by re-counting the final sweep.** (1) It said the marker text is `DNS: host does not resolve` (`api.py:698`), "distinctive enough to separate it from the connect-time kind". It *is* distinctive — **and it over-counts exactly 4×**, because one dead-domain request emits that string in **four** console lines: `Crawl error: DNS…`, the `raise OriginUnresolvable(…)` traceback frame, the `aitosoft_failure_class.OriginUnresolvable: …` line, and the `ORIGIN FAILURE` line. Sweep: the marker returned **5,252**; each single-emission token returned **1,313**. **The 1:1 instrument is `ORIGIN FAILURE` + `failure_class=origin_unreachable`.** Generalise it: any marker that appears in an *exception message* is repeated by the traceback, so count the log line, not the text. (2) It said `ingress /crawl − RenderGate ADMIT = pre-admission refusals + 429s`. **The memory-guard 429 does not belong in that identity**: `api.py:832` acquires the gate — logging `ADMIT` (`aitosoft_admission.py:173`) — **before** `get_crawler` at `api.py:847`, where the guard refuses, so **a memory 429 has already emitted its ADMIT line**. Correct form: **ingress `/crawl` − `RenderGate ADMIT` = pre-admission dead-DNS + `RenderGate REJECT`**, and nothing else. Sweep: 186,178 − 184,404 = **1,774** vs 1,313 + 660 = **1,973** (0.1 % residual on 186 k). Segment 2's `274 − 261 = 12 + 1` still reconciles only because it contained no memory 429s — which is precisely why the wrong form survived a check. The companion identity **`RenderGate REJECT` + memory refusals = wire 429** holds essentially exactly. |
| **A `failure_class` a query cannot see at all** | `render_mode: "static"` failed fetches log `[static] request error:` / `[static] timeout after` at **INFO with no `failure_class` field** (`aitosoft_static_mode.py:301,307`), yet `_static_error_result` defaults the class to `origin_unreachable` (`:164-179`). | **No `failure_class` query can ever count these.** Matters because MAS pivots a host to static after repeated failures, so this hole opens exactly when a host is already misbehaving. Streaming's pre-admission DNS path logs nothing at all (`api.py:1325-1334`) — low value, MAS never streams. Both recorded in `tasks/done/segment-2-counter-readout.md`. |
| RENDER-DEFECT ("RENDER DEFECT: url=… content collapsed in our parse: N chars of visible text …, 0 chars of markdown out; html2text recovered N chars") | Our parse lost the whole body **and the html2text fallback could not get it back**. Served as **HTTP 200 + result `success:false` + `failure_class: render_defect`**, content attached, zero retries. Deployed `0.9.2-detector-round3` 2026-08-01; narrowed to "unrecovered only" in `0.9.2-collapse-recovery` 2026-08-02. | **Record the URLs — do not intervene.** It is already the correct outcome for a page we cannot parse, and no restart or rollback changes it. **Read the trailing char count, it is the diagnosis:** `recovered 0 chars` means html2text agreed the page was empty (the comment/script family); anything above 0 is a *partial* recovery we declined to serve as a success, which is a different and more interesting finding. **MAS cannot see this class at all** — a page with no contacts looks like a page that has no contacts — so their "all clean" is not a cross-check. |
| COLLAPSE-RECOVERED ("COLLAPSE RECOVERED: url=… content collapsed in our parse: …; recovered N chars via html2text") | Same collapse, but the html2text fallback returned the body. Served as an **ordinary success** — `failure_class: none` — carrying the recovered markdown. New in `0.9.2-collapse-recovery` 2026-08-02. | **None. This is data we used to lose.** Count it, do not act on it. **The 2026-08-01 baseline of 2.7 % of pages / 18 % of hosts (9 URLs of 328) is now the sum of these two tokens, not RENDER DEFECT alone** — the tokens are deliberately disjoint strings so the split is countable, but a drop in RENDER DEFECT on its own no longer means what it used to. The split itself is the measurement worth reporting: it is the first real-traffic evidence of which collapse mechanism our 7 affected hosts actually hit, which is still unknown. |
| MAS success rate drops after 2026-07-30 | Not a log signal — expect it in MAS's own counters | **Do not roll back for this.** Challenge screens, redirect-blocked hosts and origin 5xx all used to be stored as successes. They now fail honestly. `AITOSOFT_CHANGES.md` 2026-07-30 entry has the expected direction. |
| PW-NAV-TIMEOUT ("Page.goto: Timeout 90000ms exceeded") | Playwright's own 90s nav timeout | **None.** Normal for slow/SPA sites. MAS pivots to static after 2 consecutive 504s per host. |
| MEM-REFUSE ("💥 Memory pressure: … refusing new browser") | **Our pool guard**, not OS-OOM. Replica hit ~85%+ and refused a new browser spawn. **Match on `💥 Memory pressure:`, not on `refusing new browser`** — the `max_browsers` cap emits that substring too (see the three-call-sites row). | Peek pool mem% timeline (`Pool: hot=… mem=…` log lines). If it drops back within ~5 min, no action — the guard worked. ~~If it sticks >85% for 10+ min, restart the revision.~~ **DO NOT restart on this alone — corrected 2026-08-10.** The overnight sweep sat above 85 % for ~15 hours and a restart would have been wrong every time: at 420 refusal events the guard read **88.7 %** while true `anon` was **68.6 %**, the rest being **583 MB of reclaimable active page cache**. **Read `anon=` in the same line, not the percentage.** ⛔ **"Escalate on `anon` ≥85 %, an `OOMKilled`, or an exit 137 — none of which have ever been seen" was true until 2026-08-15 04:30, when an `OOMKilled` / exit 137 happened.** It self-recovered in seconds, cost zero pages, and — the part that matters for this row — **it fired at ordinary readings**: `anon` was 2,835–3,445 MB and `mem` 80.5–93.5 % in the 90 s before, i.e. the middle of the all-night band. **So neither number predicts a kill and you cannot escalate on a memory reading at all.** What you *can* do is detect the kill after the fact (see the restart row below) and check whether it cost pages. `tasks/done/memory-guard-charges-reclaimable-page-cache.md` |
| **A container can restart WITHOUT the replica changing** — ⛔ **but the tail of this row said "and `az containerapp replica list` cannot see it", which is false** | Measured 2026-08-14/15: four container restarts (19:33, 21:11, 04:23 ×2 → the 04:30 OOM). The replica object survives, **`createdTime` never changes** (that half holds), and three of the four reported **no reason string at all**. A session reading `-o table` sees two healthy replicas and concludes nothing happened — which is what happened to me twice before I caught it. **What was wrong: `properties.containers[].restartCount` is already on the object the replica list returns**; only the table view hides it. The row sent readers away from the one field that answers the question. | **One call, no log sifting:** `az monitor metrics list --resource <appId> --metric RestartCount --interval PT1M --aggregation Total`. Over the final sweep: **74 restarts** (40 before the 08-14 trigger change, 34 after), matching an independent count of console `supervisord started with pid 1` lines **exactly**. **Sum the series, never sample a bin** — ACA emits it only every 5 minutes, so at PT1M it reads 0 four minutes in five; and it is cumulative per replica. Project `properties.containers[].restartCount` for the per-replica view. The `ContainerAppSystemLogs_CL \| where Reason_s == "ContainerStarted"` sift still works as a cross-check (any start not within ~10 s of a replica creation is a silent restart) and still needs the `SuccessfulRescale` scale-down/up pair ruled out first — ordinary scale churn produces the same line |
| **`ContainerAppSystemLogs_CL.Count_d` is a cumulative per-replica tally, not a per-row occurrence count** | It is the Kubernetes event `count` field: the same event repeating on the same pod re-emits with the running total. So **`count()` under-counts and `sum(Count_d)` over-counts** — and the two look like two instruments disagreeing when they are the same defect seen from both sides | **Count distinct `(ReplicaName_s, TimeGenerated)`.** Worked example from the sweep: `OOMKilled` on **one** replica emitted `Count_d` 1,2 → 3,4 → 5,6 → 7,8 → 9,10 across **five** incidents — two rows per incident, one pod. `count()` says 10, `sum(Count_d)` says 55, the truth is 5 |
| **`Reason_s == "OOMKilled"` is neither sufficient nor complete for "we ran out of memory"** | **Not sufficient:** 2 of the 18 such rows in the sweep carried **exit code 0** — ordinary scale-downs mislabelled during a node event. **Not complete, and this is the bigger half:** ACA labels a kill `OOMKilled` **only when a repeat kill lands inside the kubelet crash-backoff window**. The 7 labelled kills came **1.2–6.8 min** after that replica's previous boot; the 27 unlabelled restarts came a median of **178 min** after, **none under 10** | **Parse the exit code out of `Log_s`; never trust `Reason_s` alone.** And carry the consequence: **an isolated memory kill produces no platform event at all** — it appears only as a restart. So `RestartCount` is the complete instrument and `OOMKilled` is a subset of it, never the reverse. "No `OOMKilled` events tonight" is not "no OOM tonight" |
| **`ReplicaUnhealthy` is not an incident class — it is the loudest meaningless signal in the system** | **3,030 rows** in the sweep, dominated by `Readiness probe failed` / `Startup probe failed` against `http://<podIP>:11235/health` **during container start and stop**, which is exactly when a probe is supposed to fail | **Ignore it unless it persists on a replica that is neither starting nor stopping.** Related correction to this file's lineage: the claim "**0** `/health` requests traverse the ingress" (the refutation of health-probe scale feedback) is right in *substance* — ACA probes hit the pod IP directly and never reach Envoy — but wrong in the absolute: **125 `/health` requests did traverse the ingress in the sweep, all `curl/7.88.1`, all from our own monitoring sessions.** Our ticks are in the access log; the probes are not |
| **The guard's threshold sits inside the bulk of its own signal — the refusal count is not a memory measurement** | Measured over 11 h / ~6,000 pool samples: the reading's p25 is **82 %**, p50 **86.5 %**, p75 **90 %**, against a threshold of **85.0 %**. The guard is above its own trip point **~58 % of the time, every hour, all night**, while true `anon` is flat (p50 ~2,900 MB of 4,096). So ~1,000 refusals/night is a *threshold-crossing count on a signal centred on the threshold*: a ~1-point distributional wobble swings it tens of percent | **Never read a trend into the refusal count, and never size memory pressure from it.** Both our "hourly climb 5.9 → 9.2" and MAS's "68.7, outside the 40–63 band" were this artefact. Count it, do not interpret it |
| OTHER | Usually garbage. Log lines whose ms timestamp contains "504" (e.g. `02:17:04,504`) hit the regex. | Peek once per night to confirm, then ignore. |
| FORCE-CLOSE / "Janitor reaped" | Fix-2 Janitor killed a stuck slot | Investigate. If recurring, stuck-slot pattern from 2026-04-14 — restart or rollback. |
| ACTIVE-REQ counter not decreasing over multiple ticks | Stuck-slot pattern | **Rollback** to previous known-good image. |
| Pool mem% P99 > 95% sustained across 2+ 5min bins | ~~Cluster approaching OS-OOM, guard overwhelmed~~ — **not on its own, corrected 2026-08-10.** Overnight ran p95 92–93 % with max 100 % for 15 h, zero OOM kills, at a true `anon` of ~69 %. (⛔ "zero OOM kills" is true of *that* window only — the service has killed since, 2026-08-15, and the sweep's real restart count is 74. It does not change this row's advice, because no percentile predicted that kill either.) **The percentile is also biased upward**: the janitor samples every 10 s above 80 % and 60 s below 60 %, oversampling high states ~6× (measured overstatement 5.3×). `max` and event *counts* are unbiased; percentiles are not | ~~Restart revision.~~ **Confirm on `anon=` first, then restart only if `anon` is the thing that is high.** Single-bin spikes to 99% that recover next window are normal and self-healing. **Only count bins with `n >= 150` samples** — low-n P99 is outlier-sensitive and can misread late-arriving log data as a plateau (2026-04-17-evening lesson). Re-query on the next tick before acting. (April logs repeatedly flagged that the n≥150 gate was unreachable under 15 pinned replicas; moot since pinning was retired 2026-07-17 — replica counts now track load, and memory pressure is no longer the primary failure mode.) |

## Intervention thresholds

- ⛔ ~~Memory alert `Fired` (monitorCondition ≠ null/Resolved) → restart the
  current revision.~~ **Struck 2026-08-15 — it contradicted the two rows above,
  which say in bold DO NOT restart on memory alone.** Whichever list a tick
  session read first decided the action, which is the worst possible property for
  an intervention table. **This bullet then said "nothing documents which metric
  that alert reads, and it is NOT `get_container_memory_percent`". Settled
  2026-08-16, and the answer makes the check worse, not better:** the alert reads
  platform `MemoryPercentage` (`azure-deployment/setup-memory-alert.sh:62`) =
  `WorkingSetBytes / limit` — the **same working-set definition** as
  `get_container_memory_percent`, just divided by ~3.92 GiB allocatable so it
  reads ~2.2 points higher. It fired **32 times / 170.8 h in 30 days** (longest
  episode 52 h) into an action group with **zero receivers**, and the
  `monitorCondition` field it was queried on **does not exist on that resource**.
  **So the alert carries no information at all today** — neither a page nor a
  readable state. On any memory signal: check `anon=`, check for an actual
  `OOMKilled` / exit 137 **or an unexplained restart** (not the same set — an
  isolated kill is never labelled; see the table), and check whether pages were
  lost. Restart only if pages are being lost *now*.
- Replica non-Running >10 min → restart. **But "all replicas Running" is not
  evidence that nothing crashed** — a container can restart with the replica
  object and its `createdTime` unchanged. Project
  `properties.containers[].restartCount` (the default `-o table` hides it) or read
  the `RestartCount` metric; see the restart row above.
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

- Memory peaks aren't interventions — don't inflate the log. (This used to read
  "peaks *without alert firing*", which no longer discriminates anything: the
  alert is in a fired state ~24 % of every month. A peak is worth logging only
  when something was lost.)
- Timestamp-ms false positives aren't worth their own section. One-line
  footnote at most.
- Don't recommend code changes that came up as MAS-side issues. Point at
  them and move on.

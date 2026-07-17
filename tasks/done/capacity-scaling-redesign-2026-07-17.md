# Capacity / scaling redesign — no warm-replica pinning

**Status:** DONE 2026-07-17 — WAA eval passed, cross-check below closed the loop.
Residual finding (3× ramp-window 504) spun off to tasks/504-fence-observability.md.
**Priority:** High — MAS got a 504 under 4–6 concurrent renders (2026-07-16 incident)
**Requested by:** aitosoft-platform Claude session (relayed memo), owner Tero

## Goal

Scale-to-zero when idle, scale-out driven by real capacity (concurrent renders
per replica), graceful degradation while replicas boot (fast 429s absorbed by
MAS client retries), zero pinned warm replicas. Six asks from MAS:

1. Empirical per-replica render capacity (2 vCPU / 4 GiB) + hard semaphore
2. Fail fast (429) when full; bounded queue OK but 180s fence must start at dequeue
3. Explicit ACA scale rule matched to #1 (replace default 10-concurrent rule)
4. Cold start + readiness: measure, pre-warm, gate readiness on browser-ready
5. Contract check: V13 fields still honored on 0.9.2 (test_mas_contract.py)
6. Incident forensics: queue-wait vs render-stall for kynnos.fi/yritys 504

## Findings so far (2026-07-17)

### Incident forensics (#6) — from Log Analytics
- Single replica served the whole 17:36–17:53 burst (tjtrx, scaled 0→1 at
  17:35:50). http-scaler never scaled out: default rule = 10 concurrent/replica.
- Memory was NOT the cause: app RSS ~220 MB flat, container mem peaked 67%,
  no MemoryError raised.
- Replica launched 7 browsers in 10 min: per-persona sigs (d0f5820b, 8dccca47,
  825395c9, b38a154c) + overflow browsers after "Hot browser at capacity 5/5"
  warnings (17:37:56, 17:43:21, 17:45:13). Up to ~8 Chromium instances on 2 vCPU.
- kynnos.fi/yritys/ produced ZERO log lines (no FETCH/ERROR/ANTIBOT) → it was
  admitted, then starved inside the render path; whole-replica stall visible
  17:39:24→17:42:28 (zero completions), burst of completions right after.
  Verdict: CPU-oversubscription starvation (admission control + real scale
  rule fixes it), not a single hung tab. No memory watchdog needed.
- Retry arithmetic hazard: page_timeout 90s × (1+max_retries=2) = 270s > 180s
  fence. A page that times out under load burns the fence in silent retries
  (upstream retry loop catches timeout exceptions and retries; verbose logging
  muted in server context).

### Cold start (#4) — measured in prod logs
- Image cached on node: scheduled → render-capable ≈ 8–12s
  (container start → "Application startup complete" ≈ 4.3s; browser launch
  is INSIDE lifespan, so serving implies browser-ready already).
- Uncached node: +39.9s image pull (1.79 GB) → ~50s total.
- Probes are null → ACA default TCP probes; "startup probe failed: connection
  refused" seen during boots. HTTP /health readiness gate = browser-ready gate
  for free (lifespan blocks serving until init_permanent done).

### Current admission topology (code)
- gunicorn --workers 1 → per-process gate == per-replica gate. ✓
- GLOBAL_SEM = Semaphore(pool.max_pages=5) monkey-patches arun (server.py) —
  waits silently INSIDE the 180s fence; no 429, no queue bound.
- crawler_pool: MAX_PAGES=5 per browser, but browser COUNT unbounded
  (per-persona sig + _ovf_ overflow) → the real CPU oversubscription vector.
- wait_for(wall_clock_s=180) starts BEFORE semaphore wait → fence eaten by
  queueing, exactly what MAS observed.

## Plan

1. [x] Forensics (#6) — above
2. [x] Benchmark render capacity at 2 pinned CPUs → **render_capacity = 2**
       (N=2 +7% p50 vs N=1; N=3 +13%; N=4 +22%/p95+43%; N=6 +44%/p95 2×,
       2.1 GB Chromium RSS. Prod degrades steeper: personas → multiple
       browsers + launch storms. Bench: scratchpad bench_capacity.py)
3. [x] aitosoft_admission.py RenderGate (capacity 2, queue 4, wait 15s,
       weighted all-or-nothing) + api.py wiring (fence starts AFTER
       admission; 429 + Retry-After: 5) + config.yml knobs
4. [x] Offline tests green: test_admission.py (8) + test_mas_contract.py (7)
5. [x] Local e2e: 10 concurrent → 6×200 (queued ≤14s) + 4×429 in 0.5s w/
       Retry-After; /health instant under load; static mode bypasses gate
6. [x] Tier 1 regression local 4/4 (reports/render-gate-local-regression-tier1.md)
7. [x] ACA applied: `http-renders` rule concurrentRequests=2 (NOTE: `az
       containerapp update --yaml` silently dropped the metadata value —
       had to re-apply with `--scale-rule-http-concurrency 2`; verify with
       `az containerapp show`, not the update response), maxReplicas 30,
       HTTP Startup+Readiness probes on /health, TCP liveness
8. [x] Deployed 2026-07-17 ~03:47 UTC: image `0.9.2-render-gate`, revision
       `crawl4ai-service--0000026`. Prod smoke all green. Prod 8-way burst:
       6×200 (queued 3-5s) + 2×429@0.85s w/ Retry-After; gate logs match;
       **http-scaler scaled 1→2→4 during the burst** (vs never in the
       incident). No ReplicaUnhealthy events (probes good).
9. [x] Memo written: tasks/done/capacity-scaling-memo-to-mas-2026-07-17.md
       (delivered via Tero; MAS ack 3a1bf5b0 — see Remaining below)

## Remaining

- [ ] Watch the first WAA batch on the new admission scheme: expect 429
      bursts at ramp-up (absorbed by client retries), scale-out within
      ~30s, zero 504s from contention. Then move task to done/.
      2026-07-17: eval-request memo sent to MAS (via Tero) — they run WAA
      evals against `0.9.2-pool-cleanup` (rev 0000029) and report outcome
      stats + timeline back. When the report arrives: cross-check
      ContainerAppConsoleLogs_CL / SystemLogs for the eval window (429
      rates, scale-out timing, replica browser counts, any stalls), then
      close this task. If tiny-page minimal_text 500s appear in their
      report, that activates tasks/antibot-minimal-text-false-positive.md
      with real data.
      **Pre-run state verified 2026-07-17 14:29 UTC** (Tero announced the
      batch is about to start): replicas = 0 (cold-ramp precondition holds),
      revision 0000029, image 0.9.2-pool-cleanup, minReplicas 0 /
      maxReplicas 30, http-renders concurrency = 2 (invariant intact).
      Checked via management plane only — no HTTP sent to the endpoint, and
      NONE may be sent (not even /health) until their ramp is underway, or
      the scaled-to-zero start is polluted. Daytime run → no live monitoring
      loop (per playbook: don't self-start; MAS stops mid-run if results
      look bad); after-the-fact Log Analytics cross-check loses nothing —
      console + system logs are retained.
- [x] MAS side landed (their commit 3a1bf5b0, 2026-07-17, ack relayed via
      Tero): 429 retries 5/10/20/30s (65s span); page_timeout 80s ×
      max_retries 1 (160s < 180s fence, ~20s left for patchright tier);
      client hard timeout 210s (our worst case ≈ 200s: 15s queue + browser
      get + 180s fence — 210 is adequate, don't lower it); pinning retired
      from their runbook too.
- [ ] Optional follow-up: image diet (1.79 GB → faster uncached-node pulls).

## First-batch capacity math (their stated shape: ~15 sessions × 3 renders)

~45 concurrent renders ÷ 2 per replica ≈ 23 replicas steady-state — inside
maxReplicas 30. Cold ramp from zero: first replica ~10s (cached node), KEDA
poll (~30s) then fans out; expect full capacity in ~1-3 min. Their 65s retry
span covers cached-node ramp; a 45-at-once cold spike could exhaust a few
requests' retries if many nodes need the 40s image pull — acceptable for
run one, observe before tuning (options if it bites: they stagger session
starts, or raise admission_queue, or image diet).

## WAA eval cross-check (2026-07-17 14:32:42–14:42:39 UTC — closes this task)

MAS ran 100 companies / 808 requests / ~45 peak concurrent renders from a true
cold start. Their report: 748×200, 57×429 (all resolved on ladder), 3×504,
0×400, zero exhaustions, full-render p50 5.5s / p95 15.6s. Our Log Analytics
for the same window confirms everything:

- **429s: exact match.** 57 RenderGate REJECTs server-side = their 57 client
  429s. Split: 45 queue-full + 12 wait-timeout(15s) — the 12 are exactly their
  "~15s plateau" sub-mode. Last REJECT 14:36:01; zero after ramp settled.
- **Render accounting: exact match.** 739 [FETCH]+[COMPLETE] pairs = their
  738 full-render 200s + 1 prefetch. 9 static-mode 200s visible in static logs.
  Zero [ERROR], zero mem-guard ("refusing new browser"), zero force-close /
  janitor reaps, zero at-capacity warnings, 6 benign [ANTIBOT] retries (all
  recovered). Pool mem p95 ≤82%, one 99% single-reading spike (self-healed).
- **Scale-out:** KEDA 0→4→8→16→19→30 between 14:33:06 and 14:34:07 (72s).
  BUT serving ramp ≠ assignment ramp: only 6 replicas served all traffic
  until 14:35:15 — the other 24 waited on node provisioning + 1.79 GB image
  pull; serving waves 14:35:15/14:35:27/14:36:22, last replica serving
  14:37:17. **All 3 of their 504s started inside the 6-replica-saturation
  window (14:33:21–14:35:04); zero after.**
- **Overshoot to 30 (they predicted 23): expected mechanism, benign.** KEDA
  counts concurrent requests at ingress, which during ramp = active renders
  (~45) + gate-queued waiters held ≤15s on their connections + 429-retry
  re-arrivals → >60 concurrent → target capped at 30. Extra capacity ended
  contention by 14:36:01. Not the admission gate "over-driving" KEDA — the
  scaler never sees the gate, just held connections.
- **Scale-in: fine.** First "All metrics below target" 14:49:34 (~7 min after
  last request = KEDA cooldown), 30→16→9→4→2→1 by 14:50:35, then to zero.
  Their "+1 min no scale-in" observation was just the cooldown window.
- **The 3×504s — mechanism pinned as far as logs allow** (rest in
  tasks/504-fence-observability.md): kynnos.fi/yhteystiedot admitted on
  replica 255ps at 14:33:32 after 10.6s queue wait (matches their fire
  14:33:21.3 + 191.0s total), **acquired a browser instantly** (hot pool
  sig=79149154), then produced zero log lines for exactly 180s; next waiter
  admitted on 255ps 14:36:32.7 — the fence released the slot cleanly. 255ps
  completed renders on its other slot throughout → per-render wedge, NOT the
  2026-07-16 replica-wide starvation. teollisuuskatot pair: same signature,
  180.2/181.3s ≈ zero queue wait + full fence. Rate 3/808 = 0.37%,
  ramp-only, contained by MAS's 2-consecutive-504 static pivot.
  **CORRECTION (same day, Session E):** this entry originally called
  silent-retry arithmetic (80s×2 + patchright ≈ fence) the leading
  mechanism. Disproven — the upstream retry loop logs every retry/exception
  via AsyncLogger and `verbose` defaults to True in server context (the
  eval's own [FETCH]/[COMPLETE] lines come from that logger), so a
  goto-timeout retry could not have been silent. Zero log lines for 180s
  therefore means ONE indefinite hang inside crawler_strategy.crawl
  (unbounded-await candidates: page-creation CDP roundtrips on a busy
  Chromium, redirect-chain walk, hooks) — see AITOSOFT_CHANGES.md
  fence-obs entry and tasks/done/504-fence-observability-2026-07-17.md.
  MAS was told the old hypothesis in the 2026-07-17 cross-check relay;
  corrected in the fence-obs FYI relay.
- **Browser churn quantified:** 275 creates / 158 idle-closes fleet-wide in
  11 min for 739 renders (one Chromium launch per ~2.7 renders) — personas
  spread over 30 replicas mean every replica launches its own copy of each
  company persona, uses it ~2-3×, janitor closes it. CPU churn during ramp
  is the plausible aggravator for the wedges. Persona-affinity routing would
  fix it; parked (needs ingress/MAS work, not justified by 0.37%).
- "Using permanent browser": 0 — every MAS request carries a persona config;
  PERMANENT only serves warmup. Anti-bot minimal_text 500s: zero (parked task
  stays parked).

## Learnings

- ACA default HTTP scale rule (rules: null) = 10 concurrent req/replica —
  way past render capacity; must always set an explicit rule.
- Log Analytics console logs: table ContainerAppConsoleLogs_CL, replica col
  is ContainerGroupName_s. System events: ContainerAppSystemLogs_CL.
- az log-analytics quirk: `summarize first=min(...)` then `order by first`
  → BadArgumentError (`first` collides with the aggregate). Rename to t0/t1.
- Fence 504s (api.py "Crawl exceeded the time limit") produce NO console log
  line on 0.9.2 — zero FIX1-504 lines ≠ zero 504s. Locate them via RenderGate
  "admitted after Ns" echoes at slot-release instead (or wait for the
  observability fix).
- KEDA http concurrency counts gate-queued waiters + retry re-arrivals →
  cold-ramp overshoot toward maxReplicas is expected and benign.

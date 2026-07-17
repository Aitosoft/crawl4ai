# Capacity / scaling redesign — no warm-replica pinning

**Status:** In progress (started 2026-07-17)
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
7. [ ] ACA: explicit http scale rule (concurrency=2), maxReplicas 30,
       HTTP startup/readiness probes on /health
8. [ ] Build + deploy image, prod smoke (no extra test-site hits)
9. [ ] Reply memo to MAS (relay via Tero): capacity number, 429 semantics,
       max queue wait, cold-start numbers, backoff sizing advice, contract
       confirmation

## Learnings

- ACA default HTTP scale rule (rules: null) = 10 concurrent req/replica —
  way past render capacity; must always set an explicit rule.
- Log Analytics console logs: table ContainerAppConsoleLogs_CL, replica col
  is ContainerGroupName_s. System events: ContainerAppSystemLogs_CL.

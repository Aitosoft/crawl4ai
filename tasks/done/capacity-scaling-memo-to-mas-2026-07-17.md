# To: aitosoft-platform Claude session (via Tero)
# From: crawl4ai repo Claude session
# Re: Capacity/scaling redesign — DEPLOYED. Answers to your 6 points.
#
# [Record note 2026-07-17: this is a delivered outbound memo, not a task.
#  Sent via Tero 2026-07-17; MAS acknowledged in their commit 3a1bf5b0.
#  Kept here as the cross-repo contract record. Live tracking:
#  tasks/capacity-scaling-redesign.md]

Everything you asked for is designed, implemented, tested, and live as image
`crawl4ai-service:0.9.2-render-gate`. Scale-to-zero kept, warm-replica
pinning retired. Details per your numbering:

## 1. Per-replica render capacity: **2** (hard-enforced)

Benchmarked at 2 pinned CPUs (synthetic SME page, fixed CPU work per render,
your V13-like config): vs single-render latency, 2 concurrent costs +7%,
3 costs +13%, 4 costs +22% (p95 +43%), 6 costs +44% (p95 doubled, 2.1 GB
Chromium RSS). Production degrades *steeper* than the benchmark because your
per-company personas each get their own Chromium instance (launch storms —
see #6), so we set capacity = 2, matching your suggested number.

Enforced by a hard admission gate (`RenderGate`) in the server: max 2
concurrent full renders per replica, period. One gunicorn worker per replica,
so process == replica. Multi-URL batch requests take min(len(urls), 2) slots
— no smuggling.

## 2. Fail-fast semantics (what your client will see)

- Capacity 2 busy + fewer than 4 waiting → request queues for **max 15s**.
- Queue full (4 waiters) OR 15s elapsed → **HTTP 429**, body
  `{"detail": "Replica at render capacity: ..."}`, header **`Retry-After: 5`**.
  Rejections take ~0.5s (measured e2e), never 180s.
- **The 180s fence now starts at DEQUEUE** — we acquire the render slot
  before `asyncio.wait_for(180s)` begins. Max time a request can spend in
  the server: 15s queue + browser acquisition + 180s render ≈ 200s < the
  240s ACA ingress timeout.
- 504 still exists but now means "this specific render genuinely exceeded
  180s", not "the replica was drowning". Keeping it terminal on your side
  remains correct.
- `render_mode: "static"` requests **bypass the gate entirely** (no browser,
  never 429/504 from capacity).

**Please lengthen your 429 backoff.** Your current 1s/2s/4s × 3 spans ~7s;
replica scale-out takes 10–50s (see #4). Recommended: honor `Retry-After`
and use ~5 attempts spanning ≥60s (e.g. 5s/10s/20s/30s/45s with jitter) —
comfortably inside your 300s outer budget.

**Retry arithmetic on your side:** `page_timeout: 90000` × (1 + `max_retries:
2`) = 270s > our 180s fence — a page that times out twice burns the whole
fence and 504s. Under the new admission scheme, timeout-under-contention
should mostly disappear, but if you want the fence never to cut a retry
sequence, use `max_retries: 1` with 90s, or 60s with `max_retries: 2`.

## 3. ACA scale rule: set

`http-renders`, type http, `concurrentRequests: 2` (replaces the default
10/replica that caused the incident). `minReplicas: 0` kept, `maxReplicas`
raised **20 → 30** (your 50–90-render peak ÷ 2/replica). One replica at its
cap + queue shows ~6 in-flight requests at ingress → ACA immediately targets
~3 replicas; bursts scale fast.

## 4. Cold start + readiness: measured, gated

- Node with the image cached: **~8–12s** from replica-scheduled to
  render-capable (container start → app serving ≈ 4.5s; the browser is
  pre-warmed INSIDE app startup, so "serving" already means browser-ready).
- Uncached node: **+40s image pull** (1.79 GB image) → ~50s total.
- Probes were TCP defaults; now explicit **HTTP Startup + Readiness probes on
  /health** — ACA won't route to a replica until the browser pool is live.
  Liveness is TCP-only with generous thresholds (a busy replica is never
  killed).
- Practical consequence for you: during a burst from zero, first replica
  serves in ~10s, extra replicas trickle in over ~10–50s. That's why the
  ≥60s retry span in #2 matters. (Possible future work: image diet to cut
  the 40s pull.)

## 5. Contract check on 0.9.2: ALL CONFIRMED

Verbatim from your V13/prefetch/persona/sync-docs payloads, pinned as an
offline regression suite (`test-aitosoft/test_mas_contract.py`, runs before
every deploy):

- `crawler_config.remove_consent_popups` ✅ honored
- `crawler_config.max_retries` ✅ honored (drives upstream's anti-bot retry
  loop in `async_webcrawler.py`)
- `crawler_config.page_timeout` ✅ honored up to 180s (our trusted-client
  relaxation; upstream alone would clamp to 60s)
- `prefetch: true` ✅ honored (upstream's own allowlist)
- `render_mode: "static"` ✅ works, httpx + html2text, no browser, bypasses
  admission, verified under full render load (0.05s response while both
  render slots were busy)
- every result carries `render_mode: "full" | "static"` ✅ (re-verified e2e
  today on both paths)

## 6. Incident forensics (17:39–17:43 UTC, kynnos.fi/yritys/): render starvation, not queue wait — and NOT memory

From Log Analytics: exactly one replica served the whole burst (scaled 0→1
at 17:35:50; the default 10-concurrent rule never added more). That replica
launched **7 Chromium browser instances in 10 minutes** — each of your
persona `browser_config`s hashes to its own pooled browser, plus overflow
browsers when a browser hit its 5-page cap ("Hot browser at capacity 5/5"
warnings at 17:37:56, 17:43:21, 17:45:13). On 2 vCPU that's heavy
oversubscription plus launch storms.

Your `/yritys/` request produced ZERO log lines (no fetch, no error, no
retry) — it was admitted, then starved: the replica shows a **whole-replica
stall 17:39:24→17:42:28** (zero completions), then a burst of completions
right after. The 180s fence cancelled your request mid-starvation → 504.
Memory was NOT a factor: container peaked at 67%, app RSS flat ~220 MB, no
MemoryError. No evidence of a single hung tab — Playwright's `page_timeout`
+ the 180s fence + a stuck-slot janitor already layer as watchdogs. Verdict:
admission control + a truthful scale rule fixes this class; no additional
per-render watchdog needed.

One side effect you'll like: with the gate at 2, browser launch storms are
bounded too (a launch only happens while holding a render slot).

## Validation done

- 8 offline gate tests + 7 contract tests green; Tier 1 regression 4/4.
- E2E burst (local, 10 concurrent): 6×200 (2 immediate, 4 queued ≤14s),
  4×429 in 0.5s with Retry-After; /health instant under load.
- **Prod (2026-07-17 ~03:49 UTC, revision crawl4ai-service--0000026):**
  smoke green (health / auth 401 / MAS-shaped render 4.0s / static / js_code
  400). 8-way concurrent burst: 6×200 (2 immediate @3.3s, 4 queued @5.4-7.4s)
  + 2×429 @0.85s with Retry-After: 5 — and the new scale rule reacted
  live: **http-scaler scaled 1→2 replicas within seconds, then to 4**,
  where yesterday's incident never scaled at all. HTTP probes green.

## Action items for your side

1. Lengthen 429 backoff to span ≥60s, honoring `Retry-After` (see #2).
2. Optional: revisit `max_retries`/`page_timeout` arithmetic vs the 180s
   fence (see #2).
3. Delete any remaining warm-replica pinning from your runbooks — it's
   retired on our side (batch-scale.sh remains as an emergency valve only).

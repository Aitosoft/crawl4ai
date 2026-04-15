# Scale Audit — 10+ Parallel Agents

**Status:** complete
**Date:** 2026-04-14
**Context:** Microsoft credits push — targeting tens of thousands of companies
in 9 days, 3-6 parallel WAA agents now, 10+ parallel agents future state.

## Goal

Before the credit-funded batch starts, identify scale concerns in
crawl4ai-aitosoft that would break at 10+ concurrent agents × 5-15 sequential
requests each.

## Findings

### Fixed in this session (2026-04-14)

| # | Issue | Fix |
|---|-------|-----|
| 1 | `arun()` hangs past Azure's 240s ingress timeout → FastAPI doesn't cancel on client disconnect → `release_crawler` never fires → `active_requests` leaks | `asyncio.wait_for(_crawl_with_patchright(), timeout=180s)` in `deploy/docker/api.py` |
| 2 | Stuck pool slot (`active_requests > 0` forever) wedges pool; janitor skips such browsers | Janitor force-close when `BUSY_SINCE[id(crawler)] > STUCK_BUSY_TIMEOUT_S=600s` in `deploy/docker/crawler_pool.py` |
| 3 | KEDA http-scaler scales 2→1 mid-batch (seen in 2026-04-14 12:51 incident) | `azure-deployment/batch-scale.sh up N` sets minReplicas during a batch |
| 4 | Patchright singleton has no concurrency cap; parallel-agent load piles pages on one Chromium | Semaphore cap = 5 concurrent + periodic recycle every 100 uses in `deploy/docker/aitosoft_patchright_fallback.py` |

### Known but unfixed (accepted for now)

**`GLOBAL_SEM` in `deploy/docker/server.py:82,126`** — upstream code monkey-patches
`AsyncWebCrawler.arun` with `async with GLOBAL_SEM`. `MAX_PAGES=5` means each
replica caps concurrent arun calls at 5. Not a blocking issue because:
- Fix 1's 180s timeout means a stuck slot self-releases within 180s max
- KEDA scales horizontally: 3 replicas × 5 = 15 concurrent capacity, enough
  for 10+ parallel agents
- Fix 3 keeps minReplicas warm so we don't cold-start under load

If we ever need >5 concurrent per replica, raise `MAX_PAGES` in config.yml
(will also let crawler_pool pack more pages onto each Chromium — scales
memory linearly).

**RateLimiter `storage_uri: "memory://"` in `deploy/docker/config.yml:38`** —
rate limits are per-replica, not shared. At 10 agents with 3 replicas each
permitting 1000/min, effective global cap is 3000/min. Acceptable because our
WAA load is ~100 req/min/agent × 10 = 1000/min, well under 3000/min. If we
scale to 30+ agents, switch to Redis-backed rate limiter.

**RateLimiter instantiated per request in `deploy/docker/api.py:611-617`** — a
new `RateLimiter` is created per `handle_crawl_request` call. This limiter
is passed to `MemoryAdaptiveDispatcher` and applies WITHIN a single
`arun_many` call to pace multi-URL crawls. Each WAA request typically has 1
URL, so the limiter is essentially a no-op. This is fine for our case —
we don't need cross-request rate limiting (WAA already paces its own
sequential calls, and parallel agents hit different domains).

**Webhook delivery via `background_tasks.add_task()`** — fire-and-forget
with 5-retry exponential backoff. At 10 agents × 10 webhooks each = 100
background tasks per batch. Each task has 30s timeout × 5 retries = up to
150s wall time. Memory cost is small (~1 KB per task state). Not a scaling
concern unless webhook URL is unreachable for hours.

**Memory threshold 85% on 4 GiB** — tight under 10-agent load. Each
Chromium is ~200-400 MB; 5 concurrent pages can push a replica to 2-3 GiB.
Observed peak during the 2026-04-14 outage was 3.5 GiB (87%). Fixes 1+2
prevent the leak that caused that peak. For 10+ parallel agents, consider
bumping to 8 GiB per replica OR halving MAX_PAGES to 3.

### Capacity math at scale

| Load | Peak concurrent | KEDA target replicas | Per-replica concurrent | Notes |
|------|-----------------|----------------------|------------------------|-------|
| 1 agent sequential | 1 | 1 | 1 | Fine |
| 6 parallel agents | 6 | 2 | 3 | Fine with Fixes 1-3 |
| 10 parallel agents | 10 | 2-3 | 4-5 | Near GLOBAL_SEM cap per replica; Fix 3 critical |
| 30 parallel agents | 30 | 6-8 | 4-5 | Need redis-backed rate limits, 8 GiB replicas |
| 100+ parallel | 100+ | 20+ (max) | 5 | Hit maxReplicas ceiling; redesign |

## Recommended runbook for $2000 credit push (next 9 days)

1. Deploy image with all four fixes (Fix 1/2/3/4 above).
2. `./azure-deployment/batch-scale.sh up 3` before batch.
3. Soak test: 2-3h mixed load before production batches (see `test-aitosoft/test_soak.py`).
4. Azure alert: memory > 85% for 5 min → notify.
5. Monitor for `🚨 FORCE-CLOSING stuck browser` log lines — any occurrence
   means Fix 1 failed to prevent a leak and we need to investigate.
6. `./azure-deployment/batch-scale.sh down` after batch.

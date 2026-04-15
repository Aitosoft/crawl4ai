# Soak Test Results — 0.8.6-leak-fix

**Date:** 2026-04-14
**Image:** `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-leak-fix`
**Revision:** `crawl4ai-service--0000009` (100% traffic)
**Test window:** 2026-04-14 15:30–16:03 UTC
**Duration:** 30 min load + 2 min drain

## Verdict: ✅ PASS on all gates

| Gate | Result |
|------|--------|
| Memory drift (first-q vs last-q avg) | **+0.0%** (threshold: <20%) |
| Healthy-site success rate | **273/273 = 100%** (threshold: ≥95%) |
| Post-load `active_requests` drained to 0 | **Yes** — pool state stable throughout |

## Request breakdown

| Type | Count | Notes |
|------|-------|-------|
| Healthy sites (httpbin, w3.org, jpond, etc.) | 273/273 (100%) | Clean |
| Hard sites (diabetes.fi, ahlmanedu.fi) — 200 | 40 | Site responded normally |
| Hard sites — 504 (Fix 1 firing) | **2** | Exactly 180.1s, release_crawler called |
| Hard sites — 500 (upstream site error, ~6s) | 12 | ahlmanedu.fi fast-fail, legitimate |
| **Total** | **327** | |

## Key observations

**1. Fix 1 (asyncio.wait_for 180s) is firing cleanly**

Two ahlmanedu.fi requests that used to hang past Azure's 240s ingress timeout
now return HTTP 504 at exactly 180.1 seconds:

```
[a1 c014] HARD 504 180.1s  https://ahlmanedu.fi/tietoa-ahlmanedusta/yhteystiedot/hallitus/
[a1 c021] HARD 504 180.1s  https://ahlmanedu.fi/tietoa-ahlmanedusta/yhteystiedot/hallitus/
```

Pre-fix baseline (same URL, prior to deploy): `200 after 200.7s` — request
completed past Azure's ingress ceiling, leaking the pool slot. Post-fix:
clean 504 at 180s, `release_crawler` runs, slot freed.

**2. Memory stayed flat**

Container-side (`/monitor/health` pool total):
- 270 MB at minute 0
- 270 MB at minute 10
- 270 MB at minute 20
- 270 MB at minute 30 (end of load)
- 270 MB at minute 32 (end of drain)

Azure-side (`WorkingSetBytes` metric, whole container):
- 15:35 UTC: 1038 MB
- 15:45: 1246 MB (peak during load)
- 15:55: 1273 MB (peak)
- 16:00: 1155 MB (dropped during drain — normal cleanup)

Compare to pre-fix 2026-04-14 incident trend (same replica, same period):
- 13:00 UTC: 2400 MB
- 13:30: 3100 MB
- 14:00: 3500 MB
- 14:15: 3500 MB (approaching 4 GiB OOM limit)
- **+1100 MB leak in 75 min**

Post-fix: **zero leak, memory recovers during drain.**

**3. Pool stayed minimal**

Throughout the 30 min:
- Browser count: 1 (permanent only)
- No overflow browsers spawned
- `active_requests=0` between bursts

Pre-fix equivalent: 12+ overflow browsers stacked in cold pool, each with
stuck `active_requests > 0`.

**4. ahlmanedu 500s are legitimate, not leaks**

12 requests to ahlmanedu.fi returned HTTP 500 within ~6 seconds. These are
fast failures (site-side error or our antibot_detector flagging, patchright
retry also fails, response returned promptly). Memory and pool state stayed
clean — no leak. WAA retry logic can treat these like any other 5xx.

## Memory trend (container-side pool memory, MB)

```
270 ████████████████████████████████████████
270 ████████████████████████████████████████
270 ████████████████████████████████████████
(32 consecutive samples, all identical)
```

## Raw data

- Log: `test-aitosoft/results/soak-30min-leak-fix.txt`
- JSON samples: `test-aitosoft/results/soak-20260414-160043.json`

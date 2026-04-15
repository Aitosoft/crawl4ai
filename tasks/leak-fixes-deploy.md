# Deploy Leak Fixes — 0.8.6-leak-fix

**Status:** in progress
**Started:** 2026-04-14 15:15 UTC

## Goal

Ship Fixes 1-4 (asyncio.wait_for timeout, janitor force-close, batch-scale
script, patchright singleton bounds) to production before the $2000 Azure
credit push begins. Validate with Tier 1 regression + soak test.

## Plan

1. ✅ Implement Fix 1, 2, 3, 4 in code
2. ⏳ Build image `0.8.6-leak-fix` in ACR
3. ⏳ Deploy to `crawl4ai-service` (preserving API token env var)
4. ⏳ Tier 1 regression (4 sites must pass 200)
5. ⏳ 30-min soak test with mixed healthy + hard URLs
6. ⏳ Publish soak results: memory trend + zero-leak confirmation
7. ⏳ User runs `./azure-deployment/setup-memory-alert.sh <email>` to wire
   Azure alert
8. ⏳ User runs `./azure-deployment/batch-scale.sh up 3` before next WAA batch

## Verification criteria

Soak test must pass all three gates:
- `memory_drift < 20%` between first quartile and last quartile of samples
- `error_rate >= 95%` on healthy requests
- `post-load active_requests returns to 0` (if exposed via /monitor/browsers)

## Pre-deploy smoke test (2026-04-14 15:22 UTC, current prod)

Ran 2-min soak against `0.8.6-maxpages-fix` to establish baseline:
- 24 requests, 23/23 healthy OK, 1 hard returned 200 after **200.7s** (reproduces the hang pattern from the 14:24 UTC incident — crawl returns eventually but takes >180s).
- Memory drift: 0.0% (too short to judge).
- This is the bug Fix 1 targets: a request that eventually succeeds but exceeds Azure's 240s ingress timeout, meaning Azure has already 504'd to the client while the backend keeps holding the pool slot.

## Post-deploy verification plan

After 0.8.6-leak-fix is live:
1. Re-run the same 2-min smoke test. ahlmanedu.fi URL should return 504 at 180s (not 200 at 200s). That's the Fix 1 signature.
2. Tier 1 regression: `python test-aitosoft/test_regression.py --tier 1 --version leak-fix`. Must be 4/4 PASS.
3. 30-min soak: `python test-aitosoft/test_soak.py --duration-min 30 --parallel 1`. All three gates must pass.
4. If green, mark complete and tell user it's safe to start the credit batch.

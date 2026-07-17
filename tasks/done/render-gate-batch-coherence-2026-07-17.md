# Enforce single-URL /crawl requests (MAS contract decision 2026-07-17)

**Status:** DONE — deployed and live-verified 2026-07-17
**Note:** File name predates the 2026-07-17 rescope (was "render-gate batch
coherence"); the shipped scope is boundary enforcement, not weight coherence.

## Decision (MAS, relayed via Tero 2026-07-17)

> We commit to single-URL /crawl requests long-term — enforce it at the
> boundary (400 on multi-URL) and document it in the contract; no change
> needed on our side.

Their reasoning, recorded for posterity: their client is structurally
single-URL (`src/lib/crawl4ai-client.ts` always sends `urls: [url]` and reads
only `results[0]`, so a multi-URL response would be silently truncated on
their side anyway); WAA is a ReAct loop, so requests are inherently
sequential per agent; their parallelism is multiple agents each sending
single-URL requests, already governed by the 2-renders-per-replica +
429/Retry-After contract. A 400 keeps the assumption visible instead of
silently violable.

## Original problem (closed by enforcement rather than implementation)

`RenderGate.acquire` clamps weight to capacity, so a multi-URL request
admitted at weight ≤2 could render at up to GLOBAL_SEM(5) concurrency —
violating the 2-renders-per-replica invariant. With multi-URL requests
rejected at the boundary, the gap becomes structurally unreachable. The
weight-coherence implementation options considered are in this file's git
history (pre-2026-07-17 rescope) if batching ever returns as a deliberate
contract revision.

## What shipped

1. **Guard in `deploy/docker/api.py` `handle_crawl_request`** (top of the
   try block — before seed validation, the static-mode branch, and render
   admission): `len(urls) > 1` → HTTP 400, detail `"multi-URL requests not
   supported: MAS contract is single-URL per request (AITOSOFT_CHANGES.md,
   2026-07-17)"`. Covers /crawl (full + static) and /crawl/job (reuses the
   handler). /crawl/stream deliberately not guarded (MAS doesn't use it; no
   extra hunk in an upstream file). Monitor records the 400 like the
   existing 429/UntrustedConfigError paths.
2. **`aitosoft_admission.py` `acquire()` docstring**: KNOWN LIMITATION
   rewritten — weight-clamp note retained, multi-URL now rejected upstream
   of the gate (points at AITOSOFT_CHANGES.md contract addendum).
3. **Tests**: new `test_mas_contract.py::test_multi_url_request_rejected_with_400`
   (exercises `api.handle_crawl_request` directly, like test_admission.py);
   existing single-URL MAS payload tests untouched. Two static-mode monitor
   tests used 2-URL batches (shape now unreachable) — converted to
   single-URL; all-fail→502 monitor pin preserved,
   `test_partial_success_still_records_200` became
   `test_static_success_records_200` with a comment explaining why.
4. **Docs**: AITOSOFT_CHANGES.md contract addendum (MAS ack + date);
   CLAUDE.md per-request one-liner + api.py table row; AITOSOFT_FILES.md
   api.py count refreshed (+119/−9 vs upstream/develop).

## Evidence (2026-07-17)

- Offline gates: 26/26 (mas_contract 8, admission 8, static_mode 10);
  pre-commit hooks pass; secret scan clean.
- Deploy: image `0.9.2-single-url`, digest `sha256:cfb148731ec0...`,
  revision `crawl4ai-service--0000028`; render-capacity invariant check OK
  (config.yml 2 == ACA http-renders rule 2).
- Live: `/health` ok; 2-URL request → **400** with the exact contract
  message; single-URL caverna.fi crawl ✅ (971 chars markdown); Tier 1
  regression 4/4 (report `test-aitosoft/reports/single-url-regression-tier1.md`).
  Note: one pre-switch 2-URL probe hit the draining old revision and
  returned 200 (crawled example.com/example.org once — harmless); retried
  after traffic moved to --0000028 and got the 400.

## Progress

- 2026-07-17: Task created from audit; limitation documented in acquire()
  docstring; scope question sent to MAS.
- 2026-07-17: MAS committed to single-URL long-term; task rescoped from
  "weight coherence implementation" to "boundary enforcement + contract pin".
- 2026-07-17: Implemented, tested offline, deployed as `0.9.2-single-url`,
  live-verified. Closed.

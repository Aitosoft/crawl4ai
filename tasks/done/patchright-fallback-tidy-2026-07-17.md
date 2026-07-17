# Patchright fallback: internals tidy (counter, recycle race, frozen persona)

**Status:** DONE (closed 2026-07-17, deployed in `0.9.2-pool-cleanup`)
**Priority:** Low — fallback path only; current failures already degrade gracefully
**Effort:** S-M. **Risk:** low-medium.

## Items (all in `deploy/docker/aitosoft_patchright_fallback.py`)

1. **Private-attr peeking:** `_UNDETECTED_SEM._value` is read at :226 and
   :232 to report in-flight count — fragile against asyncio internals
   changing. Keep an explicit in-flight counter.
2. **Recycle race:** a caller can obtain the singleton crawler ref, then
   `_recycle_undetected` (:170) closes it before the caller enters the
   semaphore (:154) → `arun` on a closed crawler. Swallowed by the per-URL
   except (the retry is silently lost), so self-healing, but real. Fix:
   acquire the semaphore before dereferencing the singleton, or
   generation-tag the crawler and re-fetch on mismatch.
3. **Frozen first persona:** the singleton is built from the FIRST request's
   BrowserConfig (:94-104); later personas' UA/viewport/headers never apply
   to the fallback path. Either document this as accepted (fallback = one
   generic stealth identity) or rebuild the singleton when the persona
   differs. Decision needed; documenting is probably fine — patchright's
   whole point is its own stealth fingerprint.
4. **Comment gap:** upstream `server.py` monkeypatches `AsyncWebCrawler.arun`
   class-wide, so patchright retries also consume GLOBAL_SEM permits — safe
   today (5 > gate 2 + queue) but non-obvious; add a comment where the retry
   enters the crawl (:161 area).

## Plan

Single pass + offline test for the recycle race (mock crawler, force recycle
between deref and acquire). No deploy urgency; ride along with the next image.

## Progress

- 2026-07-17: Task created. No code changes yet.
- 2026-07-17: All four items landed in commit 0a4bf14, deployed in
  `0.9.2-pool-cleanup`.
  1. Explicit `_UNDETECTED_IN_FLIGHT` counter; no more `_UNDETECTED_SEM._value`
     peeking anywhere in the file.
  2. Recycle race closed via "acquire before deref": the singleton is
     dereferenced inside the semaphore with the in-flight counter already
     raised; `_recycle_undetected` only swaps at in_flight == 0. (Chose this
     over generation-tagging — simpler, no re-fetch loop.)
  3. Frozen first persona documented as ACCEPTED (module docstring +
     `_get_undetected_crawler` docstring, marked as coordination decision
     2026-07-17 with explicit "do not fix" guidance).
  4. GLOBAL_SEM interplay comment at the arun call site (retries consume
     GLOBAL_SEM permits via upstream's class-wide capped_arun; safe while
     render_capacity 2 < pool.max_pages 5).
  - Pinned by test-aitosoft/test_patchright_fallback.py (4 offline tests):
    stale-ref regression, recycle no-op mid-arun, counter reset on arun
    exception / startup failure.

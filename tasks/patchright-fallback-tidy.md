# Patchright fallback: internals tidy (counter, recycle race, frozen persona)

**Status:** Open (created 2026-07-17 from the repo audit)
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

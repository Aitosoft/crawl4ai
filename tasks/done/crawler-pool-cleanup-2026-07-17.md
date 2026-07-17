# crawler_pool.py: de-noise the upstream diff + fix PERMANENT re-init

**Status:** DONE (closed 2026-07-17, deployed in `0.9.2-pool-cleanup`)
**Priority:** Medium
**Two independent changes — land 1 first (mechanical, no behavior), then 2.**

## 1. De-noise the diff (Effort S, risk low)

Roughly a third of our +258/−49 diff vs upstream in
`deploy/docker/crawler_pool.py` is pure reformatting of untouched upstream
lines (log-message rewraps, quote style, blank lines, `_sig` separator
spacing). This violates the repo's own top rule — minimal upstream diff
surface (see .pre-commit-config.yaml header for why) — and inflates every
future merge.

- Restore byte-identical upstream lines for all cosmetic-only hunks
  (work hunk-by-hunk from `git diff upstream/develop -- deploy/docker/crawler_pool.py`).
- Delete the dead branch: the overflow scan iterates HOT_POOL for `_ovf_`
  keys that can never exist there (promotion never applies to overflow keys).
- Verify: `git diff upstream/develop -- deploy/docker/crawler_pool.py` shrinks
  to only real changes; offline tests still pass; Tier 1 regression.

## 2. PERMANENT browser re-init after stuck force-close (Effort S-M, risk medium)

After `_force_close_stuck` closes the PERMANENT browser it sets
`PERMANENT = None` and nothing ever re-initializes it — one stuck slot
permanently degrades all default-config traffic to overflow cold browsers
until container restart.

- Fix: lazily recreate on next default-sig `get_crawler` (preferred — no
  janitor-side lifecycle), or immediately in the janitor.
- Add an offline test alongside test_admission.py's style: force-close the
  permanent tier, assert the next default-config request gets a live browser.

## Secondary findings parked here (fix opportunistically while in the file)

- `BUSY_SINCE` is keyed by `id(crawler)` — theoretical id-reuse after GC;
  bounded by the pop-on-release/close discipline. Consider a monotonic key.
- `OVERFLOW_SEQ` not reset in `close_all` (cosmetic).

## Progress

- 2026-07-17: Task created. No code changes yet.
- 2026-07-17: Both changes landed and deployed (`0.9.2-pool-cleanup`,
  revision `crawl4ai-service--0000029`).
  - **De-noise** (commit b253526): rebuilt the file from exact upstream bytes
    + only the real changes. Diff vs upstream/develop: +258/−49 → +210/−36
    (net of the re-init feature); every remaining hunk is nameable. Dead
    HOT_POOL `_ovf_` scan removed (overflow keys only ever live in COLD_POOL;
    promotion only moves plain-sig keys). Zero behavior change — verified
    with `git diff -w`: only f-string collapses (identical log bytes), quote
    style, blank lines.
  - **PERMANENT lazy re-init** (commit 9e6220d): `get_crawler` rebuilds the
    permanent browser on the next default-sig request after
    `_force_close_stuck` nulled it (assign only after `start()` succeeds;
    can't fire pre-init since DEFAULT_CONFIG_SIG is unset until
    init_permanent). Pinned by test-aitosoft/test_crawler_pool.py (4 offline
    tests, mocked browsers).
  - Secondary findings: took `OVERFLOW_SEQ` reset in `close_all` (trivial).
    **BUSY_SINCE id()-rekeying NOT taken** — touches 4 call sites, not a
    ride-along; still bounded by pop-on-release/close discipline. Re-open a
    task if it ever matters.
  - Verified: offline gates 34/34, Tier 1 regression 4/4 against prod, replica
    logs clean (permanent init, cold→hot promotion, no janitor warnings).

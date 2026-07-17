# crawler_pool.py: de-noise the upstream diff + fix PERMANENT re-init

**Status:** Open (created 2026-07-17 from the repo audit)
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

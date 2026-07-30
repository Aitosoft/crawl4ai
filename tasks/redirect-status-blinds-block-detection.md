# Redirect-chain status blinds block detection (block pages returned as success)

**Status:** Open — ready to implement, no external input needed
**Priority:** HIGHEST of the 2026-07-30 batch. Silent data corruption, at scale,
in the direction that costs most (false negative: block page treated as content).
**Effort:** S (a few lines) + M (regression fixtures)
**Risk:** low for the fix, medium for the blast radius — this changes how many
results are marked `success: false`. Expect MAS's failure rate to *rise* after
this ships; that is the point, and MAS must be told before it lands.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §2b

## Problem

`CrawlResult.status_code` carries the **first** hop of the redirect chain, while
block detection needs the **last**. Every redirecting site whose final response
is a 403/503 block page is therefore reported to MAS as a clean success with the
block page as its content.

Live, today, unmodified prod:

```json
{ "url": "https://konecranes.com", "success": true,
  "status_code": 301, "redirected_status_code": 403,
  "redirected_url": "https://www.konecranes.com/", "error_message": "",
  "markdown.raw_markdown": "# Error 403 Forbidden … Varnish cache server" }
```

Finnish company sites redirect apex→www or http→https almost universally, so
the exposed surface is most of the corpus — not an edge case. MAS's recorded
data defect (Konecranes' website stored as `konecranes.careers`) traces
directly here.

## Mechanism (upstream code, carried unmodified)

1. `crawl4ai/async_crawler_strategy.py` ~786-800 walks `request.redirected_from`
   back to the earliest hop and assigns `status_code = first_resp.status`.
   The final status is preserved separately as `redirected_status_code`.
   This is deliberate upstream design — callers can see "this URL 301'd".
2. `crawl4ai/async_webcrawler.py` ~511 (inside the attempt loop) and ~632
   (the final "mark blocked results as failed" pass) both call
   `is_blocked(async_response.status_code, html)` / `is_blocked(crawl_result.status_code, …)`.
   They pass the **301**. `antibot_detector.is_blocked` only fires on
   403/503/429 → never fires.

The bug is the *consumer*, not the producer: `status_code` keeping the first hop
is fine; feeding it to `is_blocked` is not.

## Fix

Feed block detection the **effective final** status at both call sites:

```python
_effective_status = async_response.redirected_status_code or async_response.status_code
_blocked, _block_reason = is_blocked(_effective_status, html)
```

and the same in the final pass using `crawl_result.redirected_status_code`.

Decisions the implementer must make deliberately:

- **Do not** change `status_code` itself to the final status. It is upstream
  semantics, MAS may already branch on it, and `redirected_status_code` already
  carries what we need. Changing it is a contract break for no gain.
- Consider whether `error_message` should name the final status
  (`"Blocked by anti-bot protection: HTTP 403 …"` already will, via
  `is_blocked`'s reason string — verify).
- Check the same blindness in `_needs_fallback` (`async_webcrawler.py` ~556)
  which also calls `is_blocked(crawl_result.status_code, …)`.

## Also: file upstream

This is a clean, self-contained upstream bug with a two-line fix and an obvious
test. File it against `unclecode/crawl4ai:develop` the same way as
`tasks/file-upstream-prs.md` (PR #2085). Doing so keeps our delta small.

## Verification

1. **Offline fixture test** (add to `test-aitosoft/`): construct an
   `AsyncCrawlResponse`-shaped object with `status_code=301`,
   `redirected_status_code=403` and a Varnish-style body; assert the result is
   `success=false` with an anti-bot `error_message`. Do **not** live-test
   against konecranes — it is a real blocked host (site-safety rules).
2. **Regression risk check:** confirm a *benign* redirect (301 → 200) still
   returns `success=true`. `caverna.fi` or any Tier 1 site over `http://` works.
3. Tier 1 regression 4/4 before deploy.

## Coordinate before deploy

MAS's observed success rate will drop when this lands, because results that
were silently wrong become correctly-failed. Tell them the number of affected
hosts is unknown-but-possibly-large, and that they should re-scrape anything
whose stored `status_code` is a 3xx. Suggest they also add the client-side
mitigation immediately (`redirected_status_code >= 400` ⇒ failure) — it needs
no deploy from us.

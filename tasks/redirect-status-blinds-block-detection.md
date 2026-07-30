# Redirect-chain status blinds block detection (block pages returned as success)

**Status:** IMPLEMENTED 2026-07-30, committed, **not yet deployed** — deploy is
gated on Tero relaying the MAS warning below. Upstream PR filed.
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

---

## Progress (2026-07-30, implementation session)

### What shipped

`crawl4ai/antibot_detector.effective_status(status_code, redirected_status_code)`
— one helper, used at all three `is_blocked` call sites in
`async_webcrawler.py` (512, 557, 629). `status_code` untouched, as decided.

`error_message` already names the final status without extra work — verified:
`"Blocked by anti-bot protection: HTTP 403 with HTML content (221 bytes)"`.
The open question in the Fix section is closed.

`_needs_fallback` (line 557) was changed for upstream correctness but is **dead
code in our deployment**: `fallback_fetch_function` is in
`UNTRUSTED_FORBIDDEN_FIELDS`, `aitosoft_trust.py` does not relax it, and nothing
in `deploy/` sets it.

Tests: `test-aitosoft/test_redirect_block_detection.py`, 11 offline tests, no
browser (fake crawler strategy + `crawler.ready = True`). Verified they fail on
the unpatched tree: exactly 3 fail, the other 8 are regression guards that pass
both ways.

### ⚠ Correction to the coordinator's premise — read before deploying

The task file and forensics §2b both say MAS can key on
`redirected_status_code >= 400` because "it is already in the payload".
**After this change it is not**, for exactly the hosts this fixes:

- `server.py:940` raises `HTTPException(500, ...)` when every result is
  unsuccessful (single-URL contract ⇒ always, on any failure).
- `server.py:517-528` genericizes every 500 to
  `{"error": "Internal server error", "correlation_id": …}`.

So a 301→403 host moves from a wrong-but-parseable **200** to an opaque **500**
with `status_code`, `redirected_status_code`, `error_message` and `crawl_stats`
all stripped. Measured end-to-end against a local fixture origin:

| Case | Before | After |
|---|---|---|
| 301 → 200 benign | 200, success | 200, success (3.7 s) |
| 301 → 403 block | 200, `success:true`, block page as content | **500** (13.5 s) |
| direct 403 block | 500 | 500 (12.7 s), unchanged |

This does **not** create a new failure mode — under the single-URL contract
*every* full-mode failure has always been an opaque 500, and `www.konecranes.com`
(no redirect) has always landed there. It enlarges an existing, already-tracked
one (`tasks/origin-vs-crawler-failure-classification.md`, gated on MAS Q2).

**It also corrects forensics §3:** the "konecranes HTTP 500" MAS reported is
most likely this path (block detected → `success:false` → 500 → genericized),
not the ACS-GOTO laundering described there. Same wire symptom, different cause.

### Sequencing consequence

MAS's client-side mitigation works **today** and stops working for these hosts
the moment we deploy. So either:

- **(a)** MAS applies `redirected_status_code >= 400 ⇒ failure` first, gets the
  corpus fix at zero cost and zero retry amplification, and we deploy after; or
- **(b)** we deploy first and MAS must treat 500 for these hosts as terminal,
  not retryable, or per-company cost goes to ~12-16 page loads
  (`tasks/blocked-host-retry-economy.md`).

Recommend (a). Either way the HTTP mapping should be settled by Q2.

### Cost, measured

A blocked verdict re-enters the attempt loop and arms the patchright tier, so a
301→403 host goes from 1 page load to 1 + `max_retries` first-tier renders plus
the patchright pass (≈13 s total with MAS's `max_retries: 1`, matching the
forensics §2a measurement). Pinned by
`test_blocked_result_costs_one_page_load_per_attempt`. Reducing it is
`tasks/blocked-host-retry-economy.md`.

### Upstream

Filed against `unclecode/crawl4ai:develop`. Supporting history found while
preparing it, worth keeping: issue #660 (status_code wrong for redirects) →
issue #1434 ("no way to tell if a redirected result succeeded") → PR #1435 added
`redirected_status_code` (2026-02-06) → `antibot_detector.py` was added
**8 days later** (2026-02-14) still wired to `status_code`. Upstream's own docs
(`docs/md_v2/api/crawl-result.md` §1.3/1.4) already document the semantics the
code ignores. `AsyncHTTPCrawlerStrategy` already uses the final status, so the
same URL yielded different verdicts per strategy. Note PR #2088 (open) edits the
same three lines to add a `check_blocked` opt-out — complementary, will conflict
textually.

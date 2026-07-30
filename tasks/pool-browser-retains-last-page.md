# Every pool browser keeps its last crawled page open forever

**Status:** Open — diagnosed, upstream behaviour, not bundled with the
2026-07-30 deploy.
**Priority:** Low-medium. A steady memory floor per browser, not a leak that
grows. Worth fixing because it makes memory numbers unreadable, and unreadable
memory numbers are how the 2026-04 leak hunt started.
**Effort:** S. **Risk:** low-medium — touches page teardown, which is where
browser-pool bugs hurt.
**Evidence:** triaged 2026-07-30 from the WAA side-findings list.

## Problem

`async_crawler_strategy.py:1283-1292`:

```python
# Close the page unless it's the last one in a headless/managed browser
all_contexts = page.context.browser.contexts
total_pages = sum(len(context.pages) for context in all_contexts)
if not (total_pages <= 1 and (self.browser_config.use_managed_browser
                              or self.browser_config.headless)):
    await asyncio.wait_for(page.close(), PAGE_CLOSE_TIMEOUT_S)
```

We are always headless. So whenever a browser is down to its last page — which
is its steady state between requests, and always true for a browser serving one
request at a time — **the page is not closed.** Refcounting is unaffected
(`release_page_with_context` runs first, unconditionally), so the pool's
accounting is correct and `MAX_PAGES` is not at risk. What stays behind is a
live Chromium tab still holding the last crawled DOM.

Upstream's intent is sound: closing the final page of a headless browser can
take the browser with it, and the PERMANENT pool browser must outlive every
request. The intent does not require *retaining the document*, only the tab.

## Consequence

One page's worth of DOM, JS heap and image cache is pinned per pool browser
between requests, indefinitely. For the reference host measured this week that
is a 312 KB document plus its decoded images. It is the reason
`server_memory_delta_mb` never returns to its pre-request baseline, which in
turn is why that metric has never been usable for spotting a real leak.

## Fix

Navigate the retained page to `about:blank` instead of closing it:

```python
if not (total_pages <= 1 and (...)):
    await asyncio.wait_for(page.close(), PAGE_CLOSE_TIMEOUT_S)
else:
    # Keep the tab (closing the last page can close a headless browser) but
    # drop the document it is holding.
    with contextlib.suppress(Exception):
        await asyncio.wait_for(page.goto("about:blank"), PAGE_CLOSE_TIMEOUT_S)
```

Bound it exactly like `page.close()` is bounded — a wedged renderer must not
block teardown, which is the lesson `tasks/render-retry-unbounded-hang.md`
already paid for.

## Verification

- `test_crawler_pool.py`: after a crawl completes, the browser still has its
  page and the pool still hands it out (no regression in the thing upstream's
  guard protects).
- Measure: `server_memory_delta_mb` across N sequential crawls of a large page,
  before and after. The claim is a lower floor, not a different slope — say so
  in the result either way.
- Tier 1 regression 4/4.

## Related

If this is fixed, revisit whether `server_memory_delta_mb` is worth reporting to
MAS at all, or whether it should be replaced with a post-teardown reading.

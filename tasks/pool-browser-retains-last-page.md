# Every pool browser keeps its last crawled page open forever

**Status:** CLOSED 2026-08-02 as **refuted**. The diagnosis is correct. The
proposed fix recovers nothing, and was measured not to.
**Priority:** was Low-medium. Now zero — do not re-open it as written; if the
retained page ever needs to go, the mechanism is closing the browser, not
navigating the page.
**Evidence:** this file. Priced together with `pool-residency-unbounded.md`
because the retained page was assumed to be a term in the per-browser cost that
sets the cap. It is a term. It is not a recoverable one.

## Problem — confirmed, unchanged

`async_crawler_strategy.py:1283-1292` declines to close the last page of a
headless browser. We are always headless, so a browser serving one request at a
time never closes its page, and a live Chromium tab keeps holding the last
crawled DOM. Refcounting is unaffected (`release_page_with_context` runs first,
unconditionally), so `MAX_PAGES` was never at risk.

Directly observed, not inferred: `experiment_pool_memory.py` now reports
`retained pages across the pool`, and it is **one per browser, every run**.

## Why the fix was dropped

The proposal was to navigate the retained page to `about:blank` instead of
closing it. Measured through the real path, 6–8 pooled browsers, real Chromium,
cgroup `memory.current` and `anon` read before and after, 10 s to settle:

| page the browser was holding | anon returned by `about:blank`, per browser |
|---|---:|
| `/heavy` (236 KB, 17 images, ~900 tags) | **+1.7 MB** (i.e. it *cost* memory) |
| `/heavy?heap_mb=100` (100 MB of retained, fully-committed JS heap) | **−0.5 MB** |

**The instrument is not blind, and the same run proves it.** Loading the
100 MB-heap variant raised the per-browser cost from 170.0 MB to 270.5 MB —
`+100.5 MB`, the heap, exactly. So the harness sees page memory going in with
1 % accuracy. It just does not come back out: V8 and Blink do not return the
freed pages to the OS on a same-process `about:blank` navigation, within 10 s or
at all.

A first attempt at this control **under-committed and would have lied**: the
allocator touched every 4096th `Float64` (one byte per 8 pages), so the kernel
never committed 7/8 of the buffer and `heap_mb=100` showed up as ~13 MB. Fixed
to a 512-element stride (one touch per 4 KiB page) before the number above was
taken. Recorded because a control that silently under-delivers is worse than no
control — it makes "no saving" look measured when it was never applied.

## What the retention actually means, and it is worth carrying forward

Per-browser cost is a **ratchet**. A pooled browser's floor is set by the
heaviest page it has ever crawled, and nothing lowers it again — not idleness,
not the next crawl, not `about:blank`. The only thing that resets it is
**closing the browser**.

That makes the browser cap in `pool-residency-unbounded.md` the sole
reclamation mechanism in the pool, and it is an argument for evicting on an LRU
rather than trusting an idle TTL: a browser that once loaded a 100 MB SPA is
holding 100 MB whether or not it is busy, and only eviction gets it back.

It also explains the metric this file was written about: `server_memory_delta_mb`
never returns to baseline because the page never goes. That is now understood
rather than suspicious, and the metric can be retired instead of chased.

## What NOT to do next

- **Do not close the last page instead.** Upstream's guard is there because
  closing the final page of a headless browser can take the browser with it, and
  the pool depends on the browser outliving the request.
- **Do not re-measure this with a bigger page.** The 100 MB heap is already an
  order of magnitude past any real page, and it returned 0.5 MB.
- **Do not read the 170 MB per-browser figure as the page's cost.** `/ok`
  (1.5 KB, no images) is 142.8 MB against `/heavy`'s 170.0 MB — the Chromium
  process is ~85 % of a pooled browser's cost regardless of what it is holding.

## Related

`server_memory_delta_mb` is not worth reporting to MAS and never was; its
non-return is this, not a leak. If a post-teardown reading is ever wanted, take
it after the browser closes, not after the page navigates.

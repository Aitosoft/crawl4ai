# Anti-bot retry can hang unboundedly — only the 180 s fence stops it

**Status:** IMPLEMENTED 2026-07-30, committed, **not yet deployed** (ships with
`tasks/redirect-status-blinds-block-detection.md`). Upstream PR filed.
Root cause isolated by reproduction, not inference — see Progress.
**Priority:** High. This is the mechanism behind every 504 MAS has ever seen.
**Effort:** M. **Risk:** medium — touches the retry loop that also serves the
legitimate anti-bot retry path.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §1

## Problem

When upstream's anti-bot retry loop (`crawl4ai/async_webcrawler.py` ~418-546)
takes a second attempt, that attempt can block forever. Nothing bounds it:
`page_timeout` does not cover it, and the only thing that eventually fires is
our own 180 s wall-clock fence in `api.py`, which returns a terminal 504.

Measured on `www.maitokolmio.fi` (prod, controlled cells — full matrix in the
forensics record):

| `max_retries` | `delay_before_return_html` | `page_timeout` | Result |
|---|---|---|---|
| 0 | absent | 30 s | **200 @ 5.3 s** |
| 0 | 2.0 | 30 s | **500 @ 7.9 s** (upstream re-raises the `page.content()` error) |
| 1 | 2.0 | 30 s | **504 @ 181.1 s** |
| 1 | 2.0 | 80 s | **504 @ 180.7 s** |

The decisive line is the last two: **dropping `page_timeout` from 80 s to 30 s
changed nothing.** The hang is not inside a Playwright operation that
`page_timeout` governs. Retry cost is therefore unbounded by construction, and
one bad page costs a client 180 s — twice, because MAS retries once — for zero
bytes.

Trigger on this host is `delay_before_return_html: 2.0` widening the window in
which `page.content()` races a committing navigation (Cloudflare Turnstile +
skrollr on WordPress). That is the *trigger*; the *defect* is that the retry is
unbounded.

## What to fix (in priority order)

### 1. Bound the retry — the actual fix

Give the retry loop its own deadline so a hung attempt cannot consume the
request budget. Options, roughly in order of appeal:

- **Per-attempt `asyncio.wait_for`** around
  `self.crawler_strategy.crawl(url, config=config)` inside the attempt loop,
  sized from `page_timeout` plus a margin (e.g. `page_timeout * 1.5 + 10 s`).
  A timed-out attempt becomes a normal caught exception and the loop proceeds
  to the fallback path instead of hanging.
- **A whole-`arun` budget** passed down from `api.py` (we already compute
  `wall_clock_s`) so the retry loop knows how much of it is left and skips a
  second attempt it cannot finish.

Prefer the first: it is local, upstream-shaped, and PR-able. Note this is an
upstream defect — worth filing alongside the redirect fix.

### 2. Retry `page.content()` in place instead of re-navigating

`async_crawler_strategy.py:1085` calls `await page.content()` bare. The
documented remedy for "the page is navigating and changing the content" is to
retry the capture after the navigation settles, not to redo the whole crawl.
A small bounded retry (e.g. 3× with `wait_for_load_state("domcontentloaded")`
between attempts) would have turned every observed failure on this host into a
success, since static mode proves the content is right there.

Do this **and** #1 — #2 removes the trigger, #1 removes the unbounded cost.

### 3. Consider whether `delay_before_return_html` should be a sleep at all

`async_crawler_strategy.py:1003` is a bare `await asyncio.sleep(config.delay_before_return_html)`
immediately before capture — that is the whole implementation. Upstream's
default is `0.1`; MAS sends `2.0`, a 20× wider race window.
`wait_for_load_state` / a settle-loop on `document.readyState` would serve
MAS's actual goal (let late JS finish) without racing. Do not change the
public config semantics without telling MAS — they set it explicitly in V14
and the reply asks whether they depend on the current behaviour.

## Verification

- **Do not live-test `maitokolmio.fi`.** It took 8 requests during the
  investigation, well past the 1–2/session rule. Use a recorded fixture, a
  local page that fires `location.replace()` on a timer, or another
  Turnstile+WordPress Finnish site chosen fresh.
- Offline test: a page that triggers the race must yield a bounded failure
  (< 30 s) rather than a fence 504.
- Tier 1 regression 4/4. Watch that the legitimate anti-bot retry (konecranes
  403 → patchright) still fires — the retry loop is load-bearing there.

## Immediate mitigation available to MAS with no deploy

Drop `delay_before_return_html` from the V14 render config back to upstream's
default (`0.1`; MAS sends `2.0`). On the measured host that converts a 360 s
total loss into a ~5 s success. Communicated to MAS 2026-07-30 — check
`tasks/waa-eval-2026-07-30-forensics.md` §7 for their reply before assuming
they applied it.

**Still worth doing, but no longer load-bearing.** After this task shipped, the
same shape (2 s delay, `max_retries: 1`, `page_timeout: 80 s`) returns HTTP 200
with full content in 5.0 s against a fixture reproducing the race. MAS can keep
`delay_before_return_html: 2.0` if they depend on it.

---

## Progress (2026-07-30, implementation session)

### Root cause — found, not guessed

Built a local fixture origin that reproduces the failure deterministically (a
page that commits a navigation to a URL whose headers are delayed), ran the
production config matrix against it, and dumped the real `await` chain of the
hung task by walking `cr_await` (`Task.get_stack()` returns only one frame for a
suspended coroutine and is useless here). The blocked frame was:

```
crawl4ai/async_crawler_strategy.py:1032  adapter.evaluate(update_image_dimensions_js)
  -> playwright/_impl/_frame.py:320      evaluate()
     -> <awaiting a protocol future that never resolves>
```

**The mechanism, confirmed at the driver level:** Playwright's `page.content()`
and `page.evaluate()` are sent with **no `timeout` field**, so the driver arms
no timer at all — they can only end when they get a reply or the target closes.
What they wait on is the frame's execution-context promise, and every navigation
*replaces* that promise with a fresh unresolved one. A page that keeps
committing navigations therefore wedges them forever.

This explains every piece of evidence at once:

- `page_timeout` is passed only to `page.goto` and the `wait_*` family ⇒ 80 s →
  30 s changed nothing (forensics §1, conclusion 3).
- Both call sites sit inside swallow-all `try/except` ⇒ 172 s of total silence.
- Same race, two outcomes: context destroyed *during* the call raises
  "Unable to retrieve content because the page is navigating"; context already
  gone *at* the call blocks forever. The 2026-07-30 log shows both.
- The first prod 504 (13:25:17) has **no `[ANTIBOT]` retry line at all**, so
  attempt 1 hung too. The defect was never retry-specific — bound every attempt.

`page.close()` is unbounded for the same reason, which matters because an outer
deadline cancels into the `finally` block.

### What shipped — three bounds, outermost last

| Bound | Where | Value |
|---|---|---|
| `bounded_evaluate` | `browser_adapter.py`, all three adapters | 30 s default, per-call override |
| optional DOM steps | image dimensions, consent + overlay removal | 10 s — already degrade gracefully |
| `_capture_html` | `page.content()`, settle-and-retry | 15 s/attempt, 25 s group budget, 3 attempts |
| `page.close()` | `_crawl_web` finally | 10 s |
| `total_timeout` | new `CrawlerRunConfig` field, shared by every attempt | `config.yml` → 100 s |

Design notes worth keeping:

- **Item #2 of the plan above (retry `page.content()` in place) is what turns
  failures into successes** — item #1 only bounds the cost. Both shipped.
- The capture retries share a *group* budget, not one timeout each: a
  recoverable race raises instantly so retries are nearly free, while a wedged
  page would otherwise pay a full timeout per attempt. It also bails out early
  if the page cannot even reach `domcontentloaded` — that means stuck, not
  "between documents", and another attempt buys nothing.
- Inner bounds raise Playwright's `TimeoutError` (a subclass of Playwright
  `Error`), never `asyncio.TimeoutError`. Existing `except Error` /
  `except Exception` handlers therefore keep working unchanged, and the outer
  `total_timeout` stays distinguishable from an inner one.
- `csp_compliant_wait` passes its own timeout + headroom so the adapter bound
  never races the JS polling loop it wraps.
- `total_timeout` is absent from `UNTRUSTED_FIELD_ALLOWLIST`, so a client cannot
  set (or disable) it; api.py's existing `crawler.base_config` pass injects it.
- Sizing: ~fence/2, because the patchright tier runs a second `arun()` inside
  the same 180 s fence, and above the largest client `page_timeout` (MAS sends
  80 s) so one slow navigation still fits in a single attempt.

### Measured (fixture origin, MAS V14-shaped request, full HTTP path)

| Case | Before | After |
|---|---|---|
| navigation race (`maitokolmio.fi` shape) | 504 @ 180 s, no diagnostic | **HTTP 200, full content, 5.0 s** |
| permanently wedged page | 504 @ 180 s, no diagnostic | HTTP 500 @ 94 s, exact reason logged |
| `arun()` w/ 0.4 s budget, 4 attempts | unbounded | ≤ 2 attempts, bounded |

Cancellation was verified to recover cleanly: after a bounded attempt the
browser still serves the next crawl (0.24 s) and the page census does not grow.

Tests: `test-aitosoft/test_render_bounds.py`, 17 offline tests, no browser.
Includes a guard that `config.yml`'s `total_timeout` stays inside
`limits.wall_clock_s` — the two must not drift apart.

### Residual, stated not fixed

A host that is *both* slow and blocked can still reach the fence: the patchright
tier gets its own `total_timeout`, so worst case is 2 × 100 s > 180 s.
`tasks/blocked-host-retry-economy.md` removes it by not running patchright for
reputation blocks. Not a regression — that path was unbounded before.

### Side findings (recorded in AITOSOFT_CHANGES.md, not fixed here)

- `config.yml`'s `crawler.base_config.simulate_user: true` never takes effect
  (api.py applies base_config only when the value `is None or == ""`; the
  default is `False`, which is neither).
- `_crawl_web` skips `page.close()` when the browser has ≤1 page and is
  headless, so the first page of each pool browser is never closed — and a
  wedged tab is never disposed, which is what would abort the orphaned driver
  operation.
- `api.py`'s full-mode branch calls `track_request_end(success=True,
  status_code=200)` unconditionally, so metrics record success even when the
  client gets a 500.

### Upstream

Filed against `unclecode/crawl4ai:develop`. Related prior art: PR #1923 (open)
adds a `total_timeout` at the **dispatcher** level, which only covers
`arun_many` — the Docker `/crawl` path calls `arun()` directly and gets no
protection from it. Cited in the PR as complementary. The
`page.content()` navigation-race error string has **zero** prior mentions
upstream.

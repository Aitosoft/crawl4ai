# Anti-bot retry can hang unboundedly — only the 180 s fence stops it

**Status:** Open — ready to implement, no external input needed
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

# Degrade to static inside the request instead of returning a 504

**Status:** DRAFT — blocked on MAS's answer to Q1 (`tasks/waa-eval-2026-07-30-forensics.md` §7).
The mechanism is settled and cheap; whether MAS wants it automatic is theirs
to decide.
**Priority:** High if MAS says yes — it converts the most expensive failure
mode we have (180 s for zero bytes) into a ~5 s degraded success.
**Effort:** M. **Risk:** medium — changes what a `/crawl` response can contain.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §1

## Problem

Today a full-mode render that cannot finish costs the client 180 s and returns
nothing. On `www.maitokolmio.fi` the identical content was available from static
mode in **1.93 s** (116,484 B HTML → 10,430 B markdown) at the same moment the
browser path was fencing out. MAS then retried once, so the company cost
**~360 s and produced zero pages**, and their batch runner had already deleted
the previous capture.

We are choosing a total loss over a good-enough result that was one httpx GET
away.

## Direction

Two mechanisms, and they compose.

### A. Wire our static fetcher into upstream's `fallback_fetch_function`

Upstream already has the hook. `CrawlerRunConfig.fallback_fetch_function`
(`async_configs.py:1705`) is invoked by `async_webcrawler.py` ~553 as a last
resort *after all retries and proxies are exhausted*, and the result is
processed through `aprocess_html` and marked successful
(`_crawl_stats["resolved_by"] = "fallback_fetch"`). It is also in
`UNTRUSTED_FORBIDDEN_FIELDS` (`async_configs.py:213`), so no caller can set it —
only we can, server-side, which is exactly the property we want.

Set it in `api.py` after `CrawlerRunConfig.load(...)`, pointing at a thin
adapter over `aitosoft_static_mode._fetch_static_one` that returns HTML.

Note the interaction upstream already handles for us: when the fallback
succeeds, the anti-bot re-check is **skipped** (`_fallback_succeeded` guard,
~627), so a static rescue is not then re-flagged as blocked.

Cost of this alone: near zero on the happy path, one httpx GET on the sad path.

### B. A soft deadline that abandons the browser before the fence

`fallback_fetch_function` only fires when the retry loop *returns*. The
maitokolmio failure is a **hang** — the loop never returns, so A alone would
never trigger there. That is why `tasks/render-retry-unbounded-hang.md` must
land first or alongside: once the retry is bounded, the loop returns and A
works.

Belt and braces: in `api.py`, replace the single
`asyncio.wait_for(_crawl_with_patchright(), timeout=wall_clock_s)` with a
two-stage budget — a soft deadline (proposal: ~60–75 s) after which the browser
task is cancelled and a static fetch is run inside the remaining budget. A
504 then means "even static failed", which is a much stronger signal.

Response must be explicit about what happened. Proposal:
`render_mode: "static-fallback"` (distinct from both `"full"` and `"static"`)
plus the existing `success`/`status_code`. MAS can then decide whether a
degraded capture is acceptable per use case — **this is Q1**.

## Trade-offs MAS needs to weigh (put these in the question)

- Static markdown is **not** equivalent: no JS-rendered content, no
  `fit_markdown`, `links.internal`/`external` are empty (see
  `aitosoft_static_mode.py` — links are deliberately not extracted). For a site
  whose contacts are behind JS, a static fallback is a *worse* capture that
  looks like a success.
- Against that: today they get nothing at all, 180 s later.
- A middle option is to return the static content but keep `success: false`
  with the content attached, so MAS's own logic decides. Ugly, but honest.

## Sequencing

1. `tasks/render-retry-unbounded-hang.md` (bound the retry — without it A cannot fire)
2. `tasks/redirect-status-blinds-block-detection.md` (so the fallback is not
   triggered by a mis-detected block, and vice versa)
3. This task
4. `tasks/origin-vs-crawler-failure-classification.md` (the response shape here
   should use whatever taxonomy that task settles)

## Verification

- Offline: force the browser path to raise/hang against a local fixture and
  assert the response carries static content with the agreed tag.
- Assert the fallback respects the remaining wall-clock budget and cannot itself
  push the request past the Azure ingress limit (240 s).
- Assert the SSRF hop validation still runs on the fallback path — it goes
  through `_fetch_static_one`, which calls `egress_broker.check_redirect`;
  prove it, don't assume it.
- Tier 1 regression 4/4, and confirm the happy path never invokes the fallback
  (check `crawl_stats.fallback_fetch_used == false` for all four).

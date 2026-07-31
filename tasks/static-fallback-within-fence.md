# Degrade to static inside the request instead of returning a 504

**Re-price before building (2026-07-31).** This was sized when the untimed
`page.content()` / `page.evaluate()` hang was live and a wedged render burned the
whole 180 s fence. `done/render-retry-unbounded-hang.md` shipped on 2026-07-30
and bounded exactly that, so the population this task rescues may have largely
disappeared. **Do not spend M here until
`post-deploy-measurement-0.9.2-failure-class.md` reports the 504 and
`render_timeout` rate since rev `--0000031`.** If the fence now fires rarely, the
remaining value is as a fallback for `render_error` and `origin_blocked`, which is
a different and smaller argument than the one written below — rewrite it before
implementing rather than inheriting it.

**Status:** UNBLOCKED 2026-07-30 — MAS answered Q1 **(b)**: return the static
content with `success: false` and the content attached; their logic decides.
Not in the current deploy batch — sequence it after the Q2 classification work,
whose `failure_class` shape this response should use.
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

Response must be explicit about what happened: `render_mode: "static-fallback"`
(distinct from both `"full"` and `"static"`) **plus `success: false` with the
content attached** — MAS's answer to Q1.

Their reasoning, worth keeping because it should shape other decisions here:
twice in one week their most costly failure was *a degraded capture wearing a
success label* (our §2b block pages, and the 1-character family in §8c) and
every counter they owned read green. *"A tag is advisory; `success: false` is
structural."*

## Trade-offs MAS needs to weigh (put these in the question)

- ~~empty `links.internal`/`links.external`~~ — **MAS corrected us: this costs
  them very little.** `scrape-page.tool.ts:1586-1587` harvests links from the
  markdown body and unions the two sources; their page discovery has run mostly
  off body-markdown links for months. Requirement that follows: **static
  markdown must preserve anchor text and hrefs** (html2text does; verify it
  survives any move to curl_cffi).
- No JS-rendered content **is** the real cost, and stands.
- No `fit_markdown`.

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

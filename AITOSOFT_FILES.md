# Aitosoft fork: what differs from upstream

The single inventory of our delta against upstream crawl4ai. It describes HEAD:
what is changed, why, and whether it should go upstream. The history (when each
change landed, the evidence, what it cost) is `AITOSOFT_CHANGES.md`. Task files
under `tasks/done/` hold the full investigations.

**Merge-base: `7e80152`** (upstream `v0.9.2`, a commit dated 2026-07-15), merged
into our fork 2026-07-16 as `cfb8c05`. Re-derive the delta from git instead of
trusting this file:

```bash
git diff --stat 7e80152 HEAD -- . ':!tasks' ':!test-aitosoft'   # whole delta
git diff --name-status 7e80152 HEAD | grep -v '^A'                # upstream files we modified
git diff 7e80152 HEAD -- <file>                                   # one file
```

Last verified against git on 2026-11-03 at `f365da2`. At that commit we modify
**20 upstream files (+2,621 / −193)** and add 22 files outside `tasks/` and
`test-aitosoft/`. If git shows a file or hunk this document does not describe,
the document is stale. Fix it here.

---

## How we integrate

Gunicorn loads `aitosoft_entry:app` instead of `server:app`
(`deploy/docker/supervisord.conf`). The wrapper applies deployment behaviour at
import time and then imports upstream's app unchanged:

```
gunicorn → aitosoft_entry:app
             ├─ BrowserConfig.set_defaults(**config.yml browser kwargs)   # stealth/channel/UA/viewport on every request
             ├─ aitosoft_trust.apply_trust_relaxations()                  # untrusted-boundary relaxations for our one client
             └─ from server import app                                    # upstream, AuthGateMiddleware included
```

- **Auth** is upstream's `AuthGateMiddleware`: `Authorization: Bearer
  $CRAWL4AI_API_TOKEN`, fail-closed, constant-time. Reachable without it: `/health`,
  `/token` (itself demands the token) and the static UI under `/dashboard`,
  `/playground`, `/static`.
- **`set_defaults()` is upstream's own `@_with_defaults` mechanism**
  (`async_configs.py`). `CrawlerRunConfig` carries the same decorator, so it is a
  server-side lever we do not use yet. It is the route that works, unlike
  `api.py`'s `base_config` merge (see the trap list below).
- **Trust relaxations** (`aitosoft_trust.py`, pinned by `test_mas_contract.py`):
  `browser_config.headers` is allowed; the `page_timeout` clamp is 180 s, not
  60 s; `magic`, `simulate_user` and `override_navigator` are **accepted**; a
  falsy forbidden field is dropped rather than rejected. A truthy forbidden field
  (`js_code`, proxy fields, `extra_args`, `cookies`, `cdp_url`, …) is still a 400.
  The accepted fields are not safe to send. `magic` destroys pages; the reason is
  harm, not the boundary.

---

## 1. Upstream files we modified

Line counts are `git diff --numstat 7e80152 f365da2`.

| File | +/− | Upstream PR status |
|---|---:|---|
| `crawl4ai/antibot_detector.py` | +371/−20 | `effective_status` filed as #2112; detection tiers deliberately not filed |
| `crawl4ai/async_webcrawler.py` | +55/−6 | #2112 (final hop) + #2113 (`total_timeout`) |
| `crawl4ai/async_configs.py` | +11/−0 | #2113 |
| `crawl4ai/browser_adapter.py` | +69/−16 | #2113 |
| `crawl4ai/async_crawler_strategy.py` | +267/−17 | bounds in #2113; consent reporting unfiled |
| `crawl4ai/browser_manager.py` | +11/−3 | #2085 |
| `crawl4ai/content_scraping_strategy.py` | +72/−1 | `strip_noscript` #2114 (leave open until upstream #2416 is fixed); `desc` cap worth filing, unfiled |
| `crawl4ai/js_snippet/remove_consent_popups.js` | +168/−18 | worth filing, unfiled |
| `crawl4ai/js_snippet/remove_overlay_elements.js` | +50/−8 | not worth filing (upstream has the guard; only the `rgba` fix is left) |
| `deploy/docker/api.py` | +445/−26 | ours (deployment) |
| `deploy/docker/server.py` | +110/−7 | ours (deployment) |
| `deploy/docker/crawler_pool.py` | +630/−50 | ours (deployment) |
| `deploy/docker/config.yml` | +186/−11 | ours (deployment config) |
| `deploy/docker/utils.py` | +74/−1 | ours (memory instrument) |
| `deploy/docker/egress_proxy.py` | +49/−6 | not worth filing; carry until upstream PR #2428 lands |
| `deploy/docker/egress_broker.py` | +7/−0 | docstring only |
| `deploy/docker/schemas.py` | +14/−1 | ours |
| `deploy/docker/supervisord.conf` | +19/−2 | ours |
| `Dockerfile` | +10/−0 | ours |
| `.gitignore` | +3/−0 | ours |

**Upstream PRs.** Four are filed: #2085, #2112, #2113 and #2114. None of them
was merged in `upstream/develop` at `cd61be1` (fetched 2026-11-03). Two more
are worth filing, the consent snippet and the `desc` cap; the overlay snippet's
`rgba` fix, `egress_proxy.py` and the chromium-channel workaround are not.
`tasks/file-upstream-prs.md` owns the reasoning and what to do when one merges.
When a PR merges, drop the fork patch and delete its entry here.

### `crawl4ai/antibot_detector.py`

- **`effective_status(status_code, redirected_status_code)`** returns the final
  redirect hop. Block detection has to judge the status that produced the body.
  `status_code` is the first hop, a 3xx on any redirect, and no status rule can
  match a 3xx. PR #2112.
- **Tier 1 patterns:** `robot-suspicion` and `d1rozh26tys225.cloudfront.net`, the
  asset literals of an unidentified challenge family. MAS found this family in
  371 of 402 stored challenge pages.
- **Challenge tier** (`_CHALLENGE_PATTERNS`: "Checking your browser",
  `<title>Just a moment`, `<title>One moment, please`, "request is being
  verified"). It runs at any status, gated only on visible text ≤ 1,500 chars.
  This tier exists because tier 2 only runs on 4xx/5xx, while interstitials are
  served at 200.
- **`Access Denied`** (tier 2) counts only inside `<title>` or `<h1>`–`<h3>`.
  This closes the Shopify `/pages/access-denied` nav-link false positive.
- **Block-notice tier** (`_BLOCK_NOTICE_PATTERNS`): a page whose entire visible
  text is a refusal notice counts as a block at any status and any byte size.
  It applies at ≤ 500 visible chars, and the notice must be in the title or a
  heading, or cover ≥ 50 % of the text. Without those discriminators the Shopify
  false positive (247 visible chars) comes back.
- **Evidence gates read visible text** (`_visible_text`,
  `_normalized_visible_text`, `_prose_snippet`), not `len(html)`, because a
  vendor pads its 403 page to 80 KB. **The inference gates deliberately keep
  their byte bounds.** These are tier 3 and near-empty-200.
- **Contract with `aitosoft_failure_class`:** every inference reason keeps its
  `Structural:` / `Near-empty content` prefix. The classifier keys on that prefix
  to map inference to `render_error` rather than `origin_blocked`.
  `test_failure_classification.py` pins it.
- The module docstring records which gates moved and which did not.
- Detail: `tasks/done/redirect-status-blinds-block-detection.md`,
  `antibot-detector-challenge-blindspot.md`,
  `detector-round3-evidence-vs-inference.md`.

### `crawl4ai/async_webcrawler.py`

- All three `is_blocked()` call sites pass `effective_status(...)` instead of
  `status_code` (PR #2112).
- `arun()` computes one `total_timeout` deadline and shares it across every
  attempt and proxy. When it is exhausted it raises a `TimeoutError` that names
  the budget. A single wedged page therefore cannot eat the caller's whole
  deadline (PR #2113).

### `crawl4ai/async_configs.py`

- `CrawlerRunConfig.total_timeout` (ms, default `None`), added to the
  docstring, `__init__` and `to_dict()`. It is deliberately absent from
  `UNTRUSTED_FIELD_ALLOWLIST`, so it is server-side only. It is set through
  `config.yml` `crawler.base_config` (PR #2113).

### `crawl4ai/browser_adapter.py`

- Adds `bounded_evaluate()` and `EVALUATE_TIMEOUT_S = 30`, plus a `timeout`
  kwarg on all three adapters' `evaluate`.
- **Why:** Playwright sends `page.evaluate` with no protocol timeout. It waits on
  the frame's execution-context promise, which every navigation replaces, so a
  page that keeps navigating wedges it forever. `page_timeout` does not cover
  this. PR #2113.

### `crawl4ai/async_crawler_strategy.py`

- **`_capture_html()`** replaces the bare `page.content()` calls. It settles and
  retries: 15 s per attempt, 25 s in total, up to 3 attempts, waiting up to 5 s
  for the next `domcontentloaded`. Same untimed-call problem as `evaluate`.
- **Other bounds:**
  - Optional DOM steps get 10 s: image dimensions, consent removal, overlay
    removal.
  - `page.close()` gets 10 s.
  - Virtual scroll gets 300 s.
  - The JS `wait_for` evaluate gets its own timeout plus headroom.

  The constants are at module top. PR #2113.
- **`remove_consent_popups(page, url)`** takes the *requested* URL and reads the
  report the snippet now returns. `_report_consent_pass` logs three disjoint
  tokens: `CONSENT DECLINED`, `CONSENT STRUCTURAL` and `CONSENT NAVIGATION`.
  Navigation is detected by comparing `page.url` across the pass. The check has
  to live here: a click that navigates destroys the JS context, so the snippet
  can never report it.
- **Logging channel:** these lines go through stdlib `logging`, not
  `self.logger`. `AsyncLogger` is silenced by client-settable `verbose`, wraps
  long lines into two log records, and drops `[...]` values. All three were
  measured.
- **Known false positive:** the navigation check compares full URLs, so a
  fragment-only change such as `#products` logs a `CONSENT NAVIGATION`. All 3
  lines in segment 2 were this case. The fix is to strip the fragment before
  comparing; it has not been done. Unfiled.
- Detail: `tasks/done/render-retry-unbounded-hang.md`,
  `consent-scripts-delete-the-page.md`.

### `crawl4ai/browser_manager.py`

- `_build_browser_args` gates `--disable-gpu`, `--disable-gpu-compositing` and
  `--disable-software-rasterizer` on `not enable_stealth`, the same way its
  sibling `build_browser_flags` already does. The GPU flags kill WebGL, which
  anti-bot sensors score. Upstream still hardcodes them at `cd61be1`. PR #2085.

### `crawl4ai/content_scraping_strategy.py`

- **`strip_noscript()`** runs before `document_fromstring` in `_scrap()`.
  `<noscript>` cannot nest, so a nested one leaves the outer element unclosed and
  libxml2 swallows the rest of the body. The function removes elements first,
  then any unpaired tag. Production example: 312 KB of HTML became 1 B of
  markdown at `success: true`, on 406 pages across 70 hosts. PR #2114.
- **Limit:** it does not rescue the *unclosed* `<noscript>` shape. Chromium
  serialises the rest of the document inside the element, so removing the
  element removes the page. `aitosoft_collapse_guard` recovers that shape
  instead.
- **`MEDIA_DESCRIPTION_MAX_CHARS = 200`**, applied with upstream's own
  `truncate()` in `find_closest_parent_with_useful_text`. That function returns
  an ancestor's whole subtree text as an image's `desc`, and `add_variant` copies
  it into every srcset variant. Measured: one page produced 231,708,619 B of
  `media`, and the cap brought it to 538,747 B. `cleaned_html` and markdown stay
  byte-identical.
- **What the cap does not bound:** only `desc` is bounded. `alt` and
  `media.tables` (an unvalidated `colspan`) are not. Worth filing upstream,
  unfiled. `test_media_desc_cap.py` pins it.
- Detail: `tasks/done/noscript-collapses-body-to-empty-markdown.md`,
  `media-desc-duplicates-the-page-per-image.md`.

### `crawl4ai/js_snippet/remove_consent_popups.js`

MAS sends `remove_consent_popups: true` on every request.

- **Structural guard:** `documentElement`, `body` and `head` are never removed,
  whatever matched them. This covers Phase 3 named containers and Phase 4 CMP
  iframe parents.
- **The 20 generic selectors no longer remove anything.** That is 18 substring
  patterns such as `[class*="cookie-consent" i]`, plus `.cc-banner` and
  `.cc-window`. They now live in a separate `genericContainerSelectors` list that
  is observed and reported.
  - **Why:** the Enfold theme puts `av-cookies-no-cookie-consent` on `<html>` to
    mean "consent is off", and the old code deleted the document because of it.
- **Other changes:** `document.body` / `documentElement` accesses are
  null-guarded. `acceptedBy` is recorded before each click. The snippet returns a
  `report`.
- **Selector counts at HEAD:** 86 named + 12 generic accept selectors; **120
  named + 20 generic** container selectors. The counts come from tokenising the
  arrays; a naive quote regex miscounts because selectors contain embedded
  quotes.
- **Worth filing upstream, unfiled.** Argue "the generic tier should hide, not
  remove" (`tasks/file-upstream-prs.md`).
- Detail: `tasks/done/consent-scripts-delete-the-page.md`.

### `crawl4ai/js_snippet/remove_overlay_elements.js`

- Same structural guard and the same `document.body` null-guard as the consent
  snippet.
- **`backgroundColor.includes("rgba")` is replaced with a real alpha test**
  (`0 < a < 1`). `getComputedStyle` returns `rgba(0, 0, 0, 0)` for any
  transparent element, so the old clause was always true. The rule had
  degenerated to "remove every visible fixed or absolute element", which deleted
  a contact-bearing hero at `success: true`.
- MAS sends `remove_overlay_elements: false`. **Do not recommend the flag**: the
  fix removes one degenerate clause, not the rule's appetite.
- **Not worth filing.** Upstream `a574fbc` (v0.9.3) added an equivalent
  structural guard, which leaves only the `rgba` fix, on a flag that deletes
  content even with it.

### `deploy/docker/api.py`

Our heaviest diff. Everything is deployment-specific.

**Shared helpers**
- **`_capacity_http_exception(e)`** is the one 429 builder for `/crawl` and
  `/crawl/stream`. It sets `Retry-After` and attaches `_envelope_extra`
  (`capacity_gate`, plus `memory_pct`/`limit_pct` from the memory gate).
  **`detail` must stay byte-identical**, because MAS regexes
  `memory at N% (limit M%)` out of it.
- **`_normalize_and_validate_seeds` is now async.** It runs the SSRF check off the
  event loop (`asyncio.to_thread`): the check ends in a blocking `getaddrinfo` and
  runs before render admission on the single loop that serves `/health`. On
  refusal, `_host_has_no_address()` decides whether the host has no address at
  all. If so it raises `OriginUnresolvable`, which becomes `origin_unreachable`
  at HTTP 200. An address-level policy refusal stays an SSRF 400.

**`handle_crawl_request(render_mode=…)`**, in request order:
1. Single-URL guard: `len(urls) > 1` returns 400 before seed validation. The MAS
   contract is one URL per request.
2. Static-mode short-circuit after seed validation, with no browser. The monitor
   records 502 when every fetch fails.
3. RenderGate `acquire` **before** browser acquisition and **before** the
   wall-clock fence, so queue wait never eats the render budget. A pool
   `RenderCapacityExceeded` maps to the same 429.
4. The patchright retry (`maybe_retry_blocked`) runs **inside** the fence.
5. For each result:
   - `render_mode: "full"`.
   - `status_code` is rewritten to the final redirect hop. `CrawlResult` itself
     keeps upstream's first-hop semantics.
   - The collapse guard runs (`guard_result`) and logs `COLLAPSE RECOVERED` or
     `RENDER DEFECT`.
   - `failure_class` is set on every result, including successes as `"none"`.
   - Any other failed result logs `RESULT FAILURE`.
6. The monitor records the status the client will actually see. A fence fire
   logs `WALL-CLOCK FENCE 504`.
7. Exception path: `classify_exception`, then `http_status_for`, giving one of:
   - 504.
   - A 200 envelope with a failed result. This logs `ORIGIN FAILURE` or
     `TERMINAL FAILURE`, and is where a pre-admission dead domain lands.
   - 500.

   The gate is released in `finally`.

**`handle_stream_crawl_request`**
- Awaited seed check. A pool refusal uses the same 429 builder.
  `OriginUnresolvable` keeps the old 400, because a stream cannot return an
  envelope.

### `deploy/docker/server.py`

- **`_crawl_response(results)`** replaces upstream's "all results failed → 500".
  The wire status comes from `aitosoft_failure_class.http_status_for` (200, 504
  or 500). Both render modes go through it, so one class has one wire status.
- **`/crawl`** branches to static mode before the stream check.
- **`_http_exception_handler`** adds an envelope-level `failure_class`, used only
  where no result exists to carry one: capacity, auth, malformed request, our
  own 5xx. On non-500 bodies it merges `envelope_extra_for(exc, status)`
  (`capacity_gate`, …). 500 bodies stay genericised.
- **`_unhandled_exception_handler`** adds `failure_class: "render_error"`.
- **Lifespan shutdown** closes the static-mode httpx client and the patchright
  singleton.

### `deploy/docker/crawler_pool.py`

Our second-heaviest diff.

- **Per-browser page cap:** `MAX_PAGES` is enforced per browser. A full browser
  gets an overflow sibling (`<sig>_ovf_N`, `OVERFLOW_SEQ`). Before this,
  `max_pages` was never enforced and one browser reached 44 pages.
- **Stuck-slot janitor:** `BUSY_SINCE` with a `_force_close_stuck` janitor pass
  closes any browser busy longer than `stuck_busy_timeout_sec` (600). The
  permanent browser is re-created lazily after a force-close.
- **`MAX_BROWSERS` cap (6)** with LRU eviction of *idle* browsers
  (`_lru_idle_key`, `_evict_lru_idle`, `_evict_for_capacity`). Evicted browsers
  close in a detached task bounded by `evict_close_timeout_sec`
  (`_close_detached`).
- **`get_crawler` never waits.** `release_crawler` needs the same `LOCK`, so
  waiting inside it deadlocks the whole pool. It either evicts or refuses.
- **Refusals raise `RenderCapacityExceeded` (429), never `MemoryError` (500).**
  - The memory guard sheds one idle LRU browser and then refuses
    (`gate=memory`, with `memory_pct`/`limit_pct`). That shed is a narrow
    memory → browser-count feedback loop (on refusals only); exclude its
    `memory pressure X%` evictions from any browsers→memory fit
    (`FINDINGS.md` §Browser pool).
  - The browser cap refuses with `gate=browser_pool`.
- **`_close_unused_permanent`** closes the boot browser if nothing used it within
  `permanent_unused_ttl_sec` (120). It is unreachable on v0.9.2: see the trap
  list.
- **Janitor changes:**
  - The memory-adaptive TTL collapse is removed. It closed browsers exactly when
    the next request would need them. The poll interval is still adaptive, and
    the memory guard's shed (above) is the one memory-driven close left.
  - The `📊 Pool:` line is logged unconditionally, with `resident=N/cap` and the
    `memory_breakdown()` anon/file split.
- Detail: `tasks/done/crawler-pool-cleanup-2026-07-17.md`,
  `pool-residency-unbounded.md`, `render-500-window-2026-07-31.md`.

### `deploy/docker/config.yml`

Deployment config, always ours. Every value carries an inline comment with its
reasoning. What differs from upstream:

- `limits.wall_clock_s: 180`. This is the per-crawl fence; ACA's ingress limit is
  240 s.
- `crawler.base_config`:
  - `total_timeout: 100000`. It must stay below the fence and above the largest
    client `page_timeout`.
  - `simulate_user: false`, set explicitly. The `base_config` merge never applied
    `true`. Deleting the key would inherit `True` from `utils.py`'s
    `DEFAULT_CONFIG` once that merge is fixed.
- `crawler.retry_capture_wait_s: 10.0` is the capture wait for the patchright
  retry only. Never raise the global `delay_before_return_html` instead: that
  costs about 267 render-hours per sweep.
- `crawler.memory_threshold_percent: 85.0` (upstream 95).
- `crawler.static_fetch_timeout_s: 15`.
- `crawler.pool`:
  - `max_pages: 5` (upstream 40).
  - `max_browsers: 6`, which is 3 × `render_capacity`; the reasoning is in the
    comment.
  - `evict_close_timeout_sec: 30`.
  - `stuck_busy_timeout_sec: 600`.
  - `permanent_unused_ttl_sec: 120`.
  - `render_capacity: 2`, `admission_queue: 4`, `admission_max_wait_s: 15`.
- **`render_capacity` is not the ACA scale trigger.** It is the hard cap on
  concurrent renders per replica. The ACA rule is the autoscaler's trigger,
  measured in different units. `deploy-image.sh` checks the trigger against its
  own constant.
- `crawler.browser.kwargs`:
  - `text_mode: false`.
  - `enable_stealth: true`.
  - `chrome_channel: chrome` and `channel: chrome`.
  - Viewport 1920×1080.
  - Windows Chrome/138 UA, which matches playwright-stealth's `Win32` platform.
- `extra_args`: `--disable-gpu` and `--disable-software-rasterizer` are removed.
  The comment there says `--ignore-certificate-errors` is hardcoded upstream.
  That is true at v0.9.2 and false after upstream `f0ada4c`; see §5.

### `deploy/docker/utils.py`

- Ours: the memory instrument the pool's guard refuses on. It adds
  `_read_memory_stat`, `get_memory_breakdown`, and `get_container_memory_percent`
  reporting the working set, which subtracts `inactive_file`.
- **Caveat:** under sustained crawling the page cache is *active*, so this
  reading still includes reclaimable cache. The 85 % threshold sits near the
  signal's median, so the refusal count measures nothing about memory pressure
  (`tasks/done/memory-guard-charges-reclaimable-page-cache.md`).
- `validate_url_destination` is **deliberately unchanged**. Its opaque 400 is
  correct for the seven non-crawl endpoints that share it, so the dead-domain
  distinction lives in `api.py`.
- Inherited upstream bug, unfixed: cgroup v2 `memory.max == "max"` raises in
  `int()` at `:488`, and the bare `except` falls back to *host* memory. It is
  harmless in ACA, where a limit is set. On the dev container it means offline
  memory-guard tests measure the host. Upstream #2123 / PR #2132.

### `deploy/docker/egress_proxy.py`

- Both `resolve_and_pin` calls go through `asyncio.to_thread`. The proxy runs on
  the app's only event loop, and `getaddrinfo` blocks.
- The upstream connect timeout drops from 30 s to 15 s and becomes
  `DEFAULT_CONNECT_TIMEOUT_S` plus a constructor argument. Chromium's own 30 s
  timer always fired first, so the old value never bound.
- **On the plain `http://` path, a failed connect now closes without replying.**
  A `_BLOCKED` 403 reply is rendered as the page, and our own detector then calls
  it `origin_blocked`. The CONNECT (`https://`) path keeps `_BLOCKED`.
- **Not worth filing.** Upstream rewrote the file for proxy chaining, and its
  open PR #2428 moves the resolve off the loop in its own way. Carry ours until
  #2428 lands, then drop what it covers. Detail:
  `tasks/done/egress-proxy-blocks-the-event-loop.md`.

### Small changes

| File | Change |
|---|---|
| `deploy/docker/egress_broker.py` | Docstring on `_resolve`: it blocks, and callers on a loop must offload it. Behaviour is identical to upstream. |
| `deploy/docker/schemas.py` | `CrawlRequest.render_mode: Literal["full","static"] = "full"`. |
| `deploy/docker/supervisord.conf` | gunicorn target `aitosoft_entry:app`; `RES_OPTIONS="timeout:2 attempts:2 ndots:1"` in the program environment, which overrides ACA's `ndots:5` resolver without root. A typo there is silent, because glibc ignores options it cannot parse. Never verified on a replica; `FINDINGS.md` §Egress says how. |
| `Dockerfile` | `RUN playwright install chrome`, then a conditional copy of the `chrome-*` cache to the appuser home. Real Chrome's TLS fingerprint differs from bundled Chromium's. |
| `.gitignore` | `PRIVATE.md`, which holds infrastructure identifiers kept out of the public repo. |

---

## 2. Upstream behaviour we deliberately did not patch

These are places where upstream's code decides our behaviour and the obvious fix
was rejected or deferred. A merge can change any of them under us.

- **`api.py` `base_config` merge** fills a key only when the current value is
  `None` or `""`. `max_retries` (default 0) and `simulate_user` (default False)
  therefore cannot be set server-side this way. `CrawlerRunConfig.set_defaults()`
  is the lever that works. Upstream #2121 / PR #2122.
- **`CrawlResult.status_code`** keeps upstream's first-hop semantics
  (`tests/test_pr_1435_redirected_status_code.py`). We rewrite it to the final
  hop only when `api.py` serialises.
  - **`response_headers` is also first-hop** (`async_crawler_strategy.py`, "keep
    earliest"), and `models.py` has **no `redirected_response_headers`**. Any
    `Content-Type` check silently no-ops across `http→https` and `apex→www`.
- **The permanent boot browser is unreachable** on v0.9.2. `server.py` builds its
  config without `enforce_egress`, so its pool signature never matches a
  request: 0 hits in 224 production pool gets. We close it after 120 s.
  Upstream `7b02a2c` fixes the signature (see §5).
- **`monitor_routes.py`** calls `init_permanent` inside `async with LOCK`, and
  `init_permanent` takes the same lock. That is a self-deadlock, admin-gated and
  off the traffic path.
- **`_crawl_web` cleanup** skips `page.close()` when the browser holds one page
  and is headless. The first page of each pool browser is therefore never
  closed, and a wedged tab there is never disposed. It is benign at steady state:
  one tab per browser.
- **The five ungated endpoints** (`/md`, `/html`, `/screenshot`, `/pdf`,
  `/execute_js`) turn a pool refusal into a 500. MAS calls none of them.
- **`browser_manager.py`** drops `channel` whenever `chrome_channel ==
  "chromium"`. This is a Windows workaround applied on every platform, and it is
  why our browser test suite runs `chromium_headless_shell`, not production's
  Chrome (`TESTING.md`). Upstream `a1bd6c8` fixes it.
- **The `--ignore-certificate-errors` launch flag** was hardcoded upstream at
  v0.9.2. It is the only reason broken-cert sites crawl in full mode, and it
  makes `enforce_egress`'s `ignore_https_errors=False` moot.
  `CRAWL4AI_ALLOW_INSECURE_TLS` is unset on purpose. Upstream `f0ada4c` removes
  the flag (see §5).
- **Unbounded `media` amplifiers:** `alt` is copied into every srcset variant.
  `table_extraction.py` multiplies cell text by an unvalidated `colspan`: 4.6 KB
  of HTML produced 4.5 MB of `media`, and a non-integer `colspan` silently drops
  the table. Nothing bounds a response body. These are parked because they need
  pathological markup.
- **slowapi** never registers its handler, so `RateLimitExceeded`, a starlette
  `HTTPException(429)`, lands in our envelope handler. That is why
  `capacity_gate` defaults to `"unspecified"`.
- **`config.yml` `rate_limiter`** is read only on the `arun_many` path. The
  single-URL contract never takes it, so we have no outbound politeness; pacing
  is MAS's.
- **`PDFContentScrapingStrategy`** is in `UNTRUSTED_ALLOWED_TYPES`. Its blocking
  `requests.get` bypasses the egress proxy, which is a latent SSRF path. A local
  fix would be one line in `aitosoft_trust.py`, discarding it from
  `UNTRUSTED_ALLOWED_TYPES`; it has not been written. Upstream v0.9.3 fixes the
  path itself (`4772236`, egress validation in the PDF fetch), so the next merge
  removes it.
- **`CrawlerRunConfig.clone()`** round-trips through `to_dict()`, which omits
  seven `__init__` params. The patchright leg (`aitosoft_patchright_fallback`)
  clones the config, so those params revert there. Upstream `a4c4b2d` and
  `b0ed23c` restore six of the seven, on `develop` only (not in v0.9.5).
- **`.env.txt`** is upstream's. Ours is `.env.example`.

---

## 3. Files that are entirely ours

Upstream will never touch these, so they cost nothing at merge time.

**Server modules (`deploy/docker/`)**

| File | Purpose |
|---|---|
| `aitosoft_entry.py` | Wrapper entry point: `BrowserConfig` defaults from config.yml, trust relaxations, then `from server import app`. |
| `aitosoft_trust.py` | Trusted-client relaxations of the untrusted-config boundary. Importable without the server; pinned by `test_mas_contract.py`. |
| `aitosoft_admission.py` | RenderGate: per-replica render admission (capacity 2, queue 4, 15 s max wait, then 429 + `Retry-After: 5`). Defines `RenderCapacityExceeded(gate=…, memory_pct, limit_pct)`. |
| `aitosoft_failure_class.py` | `failure_class` taxonomy. It is the only place error text (`net::ERR_*`, ACS-GOTO, `Download is starting`) is matched, and the only place a class becomes a wire status (`http_status_for`). It also defines `ORIGIN_CLASSES`, `NON_RETRYABLE_CLASSES`, the evidence/inference split (`_INFERRED_BLOCK_RE`), `render_defect` for a capture with no `<body>`, `unrenderable_content`, and the `GATE_*` 429 vocabulary with `envelope_extra_for()`. |
| `aitosoft_collapse_guard.py` | Detects a capture whose body vanished in our parse: visible-text chars in versus markdown chars out, never an HTML-byte ratio. Recovers it with `html2text` over the same HTML, but only if the result clears both floors. It reuses static mode's converter, never static mode's pipeline. |
| `aitosoft_static_mode.py` | `render_mode: "static"`: httpx + `html2text`, no browser. Redirects are validated hop by hop with `egress_broker.check_redirect`; fan-out is bounded. |
| `aitosoft_patchright_fallback.py` | Second-tier retry through patchright for results the detector marked blocked. It gets its own capture wait (`retry_capture_wait_s`), uses a semaphore-bounded singleton, and recycles that singleton periodically. |

**Tests (`test-aitosoft/`)**
- **What's there:** the offline suite, the local failure-class origin
  (`fixture_origin.py`), the four live CLI scripts (`test_regression.py`,
  `test_site.py`, `test_fingerprint.py`, `test_soak.py`), load probes
  (`cold_burst_probe.py`, `sustained_rate_probe.py`) and experiments.
- **Collection:** `conftest.py` registers the fixtures and keeps pytest from
  collecting the live scripts.
- **Historical, do not act on:** `archive/`, `stealth-v4/` and `results/`.
- **Gitignored:** `artifacts/` holds the guard's evidence corpus
  (`tasks/guard-corpus-is-not-in-the-repo.md`).
- `TESTING.md` owns test counts and procedure. To verify the count:
  `pytest --collect-only -q test-aitosoft/` (318 on 2026-11-03).

**Other**
- `azure-deployment/`: `deploy-image.sh` is the only deploy path.
  `batch-scale.sh` is an emergency valve. `setup-memory-alert.sh` sets up the
  memory alert.
- `tasks/`: open work, with `tasks/done/` for closed work. `tasks/README.md` is
  the ordered index.
- `.devcontainer/`, `.env.example`, `.github/workflows/monitor-crawl4ai-releases.yml`,
  `.github/workflows/aitosoft-tests.yml` (the offline half of `test-aitosoft/`, every
  push, Python 3.12; since 2026-11-03). The other workflows are upstream's.
  `security.yml` runs upstream's security tests, only for changes under
  `deploy/docker/**`, `crawl4ai/async_configs.py` or the workflow itself
  (`TESTING.md`).
- `.pre-commit-config.yaml`: the top-level `files:` pattern scopes every hook to
  our files. **Never widen it to upstream code.** Formatter drift on upstream
  files once turned a 10-file delta into an 11.5k-line phantom diff. When you
  add an Aitosoft file outside the listed paths, extend the pattern.
- Docs: `CLAUDE.md`, `AITOSOFT_CHANGES.md`, this file, `AZURE_OPERATIONS.md`,
  `TESTING.md`, `TEST_SITES_REGISTRY.md`, `OVERNIGHT_PLAYBOOK.md`. `PRIVATE.md`
  exists locally and is gitignored.

---

## 4. Patches dropped because upstream superseded them

| Old patch | Replaced by |
|---|---|
| `browser_adapter.py` playwright-stealth 2.x port | Upstream PR #1960 (0.8.7) |
| `api.py` 180 s `asyncio.wait_for` + 504 | Upstream `limits.wall_clock_s`; we set 180 |
| `simple_token_auth.py` + wrapper middleware | Upstream `AuthGateMiddleware` |
| `aitosoft_browser_merge.py` + `api.py` hooks | `BrowserConfig.set_defaults()` in `aitosoft_entry.py` (2026-04-14) |

---

## 5. Syncing with upstream

**Procedure**

`git fetch upstream && git merge upstream/develop`, on a branch.

- Never run formatters over upstream files.
- `git diff --stat upstream/develop...HEAD -- crawl4ai deploy Dockerfile` must
  list only the files in §1 and §3. Use three dots, which diff from the merge
  base; two dots also show everything upstream added. On 2026-11-03 it listed
  26 files, +4,880/−193. If it shows more after a merge, someone reformatted
  upstream code; fix that before anything else.
- The v0.9.2 merge took upstream's tree wholesale and re-applied our patches
  (`merge -s ours` then `checkout upstream/develop -- .`). That restored
  byte-identity after the 2026-04 whitespace incident.

**After merging**
- Run `pytest test-aitosoft/`.
- Run upstream's `deploy/docker/tests/test_security_*.py`, which is what CI runs.
- Run a Tier 1 regression against a local server.
- Update §1 here, and add an entry to `AITOSOFT_CHANGES.md`.

### Pre-merge overlap: upstream `v0.9.2` → `cd61be1` (v0.9.5 + 46)

Measured 2026-11-03 from the subject lines of 233 upstream commits. Only the
items marked *read* were checked against code. Re-derive with
`git log --oneline --no-merges 7e80152..upstream/develop -- <file>`. **Delete
this subsection after the merge.**

**If the merge targets a release tag rather than `develop`:** find the first
release carrying a commit with `git tag --contains <sha> | sort -V | head -1`.
- `a574fbc` and `130a382` are in v0.9.3.
- `7b02a2c` is in v0.9.4.
- `f0ada4c`, `6b5a0d4`, `350a141` and `d6fdff5` are in v0.9.5.
- `3f9f790`, `a1bd6c8`, `a4c4b2d` and `b0ed23c` are on `develop` only.

Upstream touched 17 of our 20 files. It left **`antibot_detector.py`,
`browser_adapter.py` and `.gitignore`** alone, so those merge clean.

**Needs a decision, not just conflict resolution:**

- **TLS: `f0ada4c` removes `--ignore-certificate-errors`** from both launch-flag
  lists (*read*). After the merge, full mode verifies certificates. Broken-cert
  SME sites, which upstream's flag has been silently tolerating, will start
  failing. This is a behaviour change for MAS.
  - **Options:** `CRAWL4AI_ALLOW_INSECURE_TLS=true`, a context-level
    `ignore_https_errors`, or accepting the loss. Decide deliberately, and fix
    the `config.yml` comment that says the flag is hardcoded.
  - Background: `tasks/done/tls-broken-cert-regression-2026-07-17.md`.
- **`<noscript>`: upstream added `unwrap_orphaned_noscript`** (`6b5a0d4`,
  `b59dc9c`, `3442707`; *read*). It unwraps noscript tags and keeps their
  contents when open and close counts disagree. Our `strip_noscript` removes the
  elements. **Keep ours alongside theirs** (it auto-merges). Upstream leaves a
  *balanced* `<noscript>` in the tree and `_scrap` later drops it with
  `getparent().remove()`, which loses the text after it: executed 2026-11-03,
  a phone number after a balanced `<noscript>` is lost on pure v0.9.5 and kept
  on ours (`FINDINGS.md` §Parse collapse). That is upstream #2416, fix in
  progress; drop `strip_noscript` and close #2114 once it lands. Check
  `test_noscript_body_collapse.py` too; the browser fixtures cannot tell the two
  fixes apart.
- **Overlay snippet: `a574fbc` + `004bc1d`** add upstream's own structural guard
  (`isDocumentStructure`) and the `document.body` null-guard (*read*). Ours
  becomes redundant; keep one. The **`rgba` alpha fix is still ours only**,
  because upstream still has `includes("rgba")`.
- **Consent and overlay snippets: `b536bf5` (#2139)** removes the unconditional
  `setTimeout` waits that hang on CSP-sandboxed pages. Expect conflicts near
  Phase 2 and at the snippet tail.
- **Server failure mapping: `130a382`** removes upstream's all-failed → 500 rule,
  the same lines our `_crawl_response` replaced (*read*: upstream `server.py` no
  longer has it). **`588de04`** preserves single-URL failure details in `api.py`.
  Keep our status mapping: it is the MAS contract.
- **Seed validation: `350a141`** reports a refused seed as a failed result
  rather than a 400. `_normalize_and_validate_seeds` now returns
  `(allowed, refused)` (*read*). This conflicts directly with our async version
  and the `OriginUnresolvable` path.
- **Permanent browser: `7b02a2c`** builds it with the egress-hardened config, so
  its signature matches requests. Re-check whether
  `_close_unused_permanent` / `permanent_unused_ttl_sec: 120` still make sense
  once the browser is reachable.
- **Pool: `3f9f790`** replaces dead pooled browsers (`is_connected()` in
  `get_crawler` and the janitor, background close). **`47ea8d7` / `6ccf610`**
  add recycling by pages served (`crawler.pool.max_pages_before_recycle`), and
  `15f4b29` defaults it to 200, which our `config.yml` would inherit. Both edit
  the functions we rewrote. **Set `max_pages_before_recycle: 0` explicitly** until
  upstream PR #2432 ships: upstream #2419 (maintainer-confirmed 2026-10-21) leaks
  a context refcount on a cancelled crawl, after which a recycle waits forever
  and every `/crawl` returns 504 until restart, and our wall-clock fence cancels
  crawls. Recycling replaces contexts inside the same Chromium process, so it is
  not known to bound the memory ratchet either (`FINDINGS.md` §Browser pool).
- **Egress proxy: `890af3d`, `01e6e96`, `07873f1`** chain the egress proxy
  through `HTTP(S)_PROXY` and route seeder fetches through it. That is 149
  upstream lines against our 49; expect conflicts.
- **Untrusted delay cap: `d6fdff5`** caps the untrusted
  `delay_before_return_html` at 60 s. MAS sends 2 s. `raw://` load tests that
  dial render time through that field are capped too. `retry_capture_wait_s` is
  applied server-side and is unaffected.
- **Channel: `a1bd6c8`** passes the `chromium` channel again and falls back to
  the shell. This probably changes which binary our browser test suite runs,
  and it is why the Windows-only workaround fix is not worth filing.

**Probably takes upstream's fix for something we carry or work around:**
- **PDF scraping:** `05de127` adds `pypdf`; `4ccd143` / `2341507` / `4138ada`
  add PDF routing and SSRF; `2e30e54` / #2138 stop treating PDF placeholders as
  blocks.
- **Body visibility:** `0a78f07` / `027b6f0` / #2131 make the body-visibility
  wait configurable.
- **Config cloning:** `a4c4b2d` / `b0ed23c` preserve fields in
  `CrawlerRunConfig.clone()` (`develop` only).
- **`base_config`:** `974275d` / `81efcc3` apply `base_config` to
  `crawler_configs`. This is not necessarily the `None`/`""` trap.

**Not merged upstream, still ours:** #2085 (upstream still hardcodes the GPU
flags), #2112 (upstream still passes the first-hop `status_code`), #2113
(upstream `page.content()` is still unbounded) and the `desc` cap (upstream
still returns the whole subtree).

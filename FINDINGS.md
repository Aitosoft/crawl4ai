# FINDINGS.md

Measured, non-obvious facts about how crawl4ai, Chromium, Playwright and our server behave, plus
the method lessons that produced them. Organised by subsystem: read the section for the code you are
about to touch. Azure/ACA behaviour (scaler, replicas, capacity, 429 populations, the memory guard's
threshold, OOMs, cost, KQL traps) lives in `AZURE_OPERATIONS.md`.

Conventions:
- Each entry gives the fact, then the evidence (date, how it was measured, where in the code), then
  the rule. The `tasks/done/*.md` pointers hold the full evidence.
- Code references name the function, because line numbers drift. All of them were checked against
  `main` @ `f365da2` on 2026-11-03.
- **`[merged v0.9.5]`** records what the 2026-11-03 merge of upstream v0.9.5 did to the entry.
  **`[revisit at next sync]`** marks an upstream change that is on `develop` after v0.9.5 and will
  arrive with the next merge. The [watchlist](#upstream-merge-watchlist) at the end lists both.

---

## Request contract and config defaults

**`max_retries` belongs to MAS, and its value is 1.** Measured 2026-08-05: all 213 `Anti-bot retry`
lines in 14 days read `1/1`. A request is therefore up to `1 + max_retries` = 2 navigations before
our patchright leg. Upstream retries on *any* exception inside `arun`, not just on blocks. The value
multiplies what a dead or blocked host costs, so re-query `Anti-bot retry` before quoting a per-host
cost. (A figure of 2 once circulated, and every cost derived from it came out 1.5× too high.)

**The `base_config` merge in `api.handle_crawl_request` only fills fields whose value is `None` or
`""`.** That means it can never set a field that has a real default, such as `max_retries` (0) or any
boolean (False). `config.yml`'s `base_config.simulate_user: true` never applied in ~10 months. It is
now an explicit `false`, deliberately. `deploy/docker/utils.py`'s `DEFAULT_CONFIG` carries
`simulate_user: True` and `load_config()` deep-merges config.yml over it. So if the key were absent,
fixing the merge rule would quietly turn user simulation on for every request.
`tasks/done/base-config-boolean-defaults-never-applied.md`.
`[merged v0.9.5]`: same rule at v0.9.5 and on develop; the
fix PR #2122 was closed unmerged on 2026-10-11 and issue #2121 is still open. Upstream `81efcc3` also routes any request that carries
`crawler_configs` through `arun_many`.

**`CrawlerRunConfig.set_defaults()` exists and works, and it is the real server-side lever.** It is
decorated `@_with_defaults` in `async_configs.py`, the same mechanism `aitosoft_entry.py` uses for
`BrowserConfig`. Verified by execution on 2026-08-09:
- defaults apply through `CrawlerRunConfig.load(body, provenance=UNTRUSTED)`;
- an explicit client value wins, *including an explicit falsy one*, because the decorator checks
  whether the key is present in `kwargs`, not whether it is truthy;
- each instance gets its own deep copy of the default;
- `clone()` preserves a `set_defaults()` default (but see the next entry for the fields it drops);
- defaults bypass the untrusted filter by design, because that filter inspects the request body.

**`CrawlerRunConfig.clone()` silently drops seven fields.** `clone()` round-trips through
`to_dict()`, which omits `base_url`, `c4a_script`, `cache_validation_timeout`,
`check_cache_freshness`, `fallback_fetch_function`, `force_viewport_screenshot` and
`virtual_scroll_config` (re-derived 2026-11-03 by comparing the `__init__` signature against
`to_dict()`). Those fields revert to their class defaults on the patchright retry leg
(`aitosoft_patchright_fallback`, which calls `crawler_config.clone(delay_before_return_html=…)`).
None of the seven is set today. Watch for it if you add a default or a field.
`[revisit at next sync]`: upstream `a4c4b2d` (2026-10-15) and `b0ed23c` (2026-10-26) restore
six of them, leaving only `c4a_script`, which is forbidden for our client anyway. **Both are on
`develop` only and are not in v0.9.5** (`git tag --contains a4c4b2d` lists no release; v0.9.5's
`to_dict()` still lacks all seven). A merge of the v0.9.5 tag does not bring the fix; a merge of
`develop` does.

**We have no outbound politeness, despite a config key that implies we do.** `config.yml`'s
`crawler.rate_limiter` is only consulted on the `arun_many` path (`async_dispatcher`). `api.py`
picks `arun` when there is one URL, and the single-URL contract guarantees one URL. The top-level
`rate_limiting:` key is *inbound* (1000/min per caller). Pacing across a sweep belongs entirely to
MAS, from one shared SNAT address.

---

## Untrusted-config boundary

**The server accepts `magic`, `simulate_user` and `override_navigator`. It does not reject them.**
`aitosoft_trust.apply_trust_relaxations()` removes them from the forbidden set for our single trusted
client (verified by execution on 2026-08-06). Don't send `magic: true` on the assumption that the
boundary will stop it. It won't, and `magic` + `remove_overlay_elements` are what deleted accountor's
page in January (see [Consent and overlay scripts](#consent-and-overlay-scripts)). The reason not to
use it is page damage, not a 400.

**A falsy forbidden field is dropped, not rejected.** A truthy forbidden field gets a 400, and
unknown fields are dropped silently. `[merged v0.9.5]`: v0.9.5 added
`UNTRUSTED_GLOBAL_FORBIDDEN_FIELDS` (filesystem sinks and code fields, refused on every type) and
checks it inside its own filter, so our tolerant wrapper, which pruned only the per-type sets, let
`{"downloads_path": null}` or `{"save_images_locally": false}` become a 400 where v0.9.2 dropped
them. Found by the merge's independent review; the wrapper now prunes the global set too, pinned by
`test_falsy_global_forbidden_fields_are_dropped_not_rejected`. Don't transcribe the forbidden sets; print them:
`python -c "import sys; sys.path.insert(0,'deploy/docker'); from aitosoft_trust import apply_trust_relaxations as a; a(); import crawl4ai.async_configs as c; print({k: sorted(c.UNTRUSTED_FORBIDDEN_FIELDS[k]) for k in ('CrawlerRunConfig','BrowserConfig')})"`.
Note that `cookies` and `extra_args` are `BrowserConfig` fields. `test-aitosoft/test_mas_contract.py`
pins MAS's contract, so run it after every upstream sync.

**The 180 s `page_timeout` cap is an env var since v0.9.5, set in code.** Until v0.9.2 `aitosoft_trust`
assigned `_ac._MAX_TIMEOUT_MS = 180_000`. Upstream v0.9.5 (`a59f50e`, `61eb573`) replaced that constant
with `_max_timeout_ms()`, which reads `CRAWL4AI_MAX_TIMEOUT_MS` (default 60,000) on every call, so the
old write became an attribute nothing reads and MAS's 90 s was clamped to 60 s with no error; only
`test_mas_contract.py` noticed. `[merged v0.9.5]`: `aitosoft_trust` now does
`os.environ.setdefault("CRAWL4AI_MAX_TIMEOUT_MS", "180000")`, which works whatever the import order
because the read is per call, and never touches the Container App's env vars. The same ceiling caps
`wait_for_timeout` and the newly allowlisted `body_visibility_timeout`. `page_timeout: 0` now becomes
60,000, not the cap (upstream treats malformed input as the default on purpose; MAS never sends 0).
v0.9.5 also caps untrusted `delay_before_return_html` at 60 s and refuses `js:`-style `wait_for` /
`css_selector` (`736a28a`); MAS sends 2.0 s and neither field.

---

## Egress, DNS and dead hosts

**The seed SSRF check is the dominant blocking-DNS call site, and it runs before render admission.**
`api._normalize_and_validate_seeds` → `validate_url_destination` → `egress_broker._resolve` →
`socket.getaddrinfo`. This runs on every `/crawl`, on the single event loop (`gunicorn --workers 1`)
that also serves `/health` and every wall-clock fence. It runs *before* the render gate, so render
capacity does not bound it. Both this call and the two `resolve_and_pin` calls in `egress_proxy.py`
are awaited via `asyncio.to_thread` (2026-08-05). The task file had blamed the proxy alone. But the
proxy never even sees a CONNECT for a name that doesn't resolve, and the file was byte-identical to
upstream, not "ours". Fix the call site that runs, not the file you happened to read.
`tasks/done/egress-proxy-blocks-the-event-loop.md`.
`[merged v0.9.5]`: upstream rewrote `egress_proxy.py` for upstream-proxy chaining (`890af3d`), with
a new `_dial()` and plain-http `dst` dial both hardcoded to `timeout=30`. Taking upstream's side passes
upstream's security suite and silently reverts the budget; taking ours fails two chaining tests. The
merge took upstream's code and threaded `self._connect_timeout_s` into all three TCP dials. Our
offload and close-on-`http://` sat outside the conflict and auto-merged intact.
`test_every_dial_path_honours_the_connect_budget` covers all four paths (CONNECT/plain-http × direct/
via an upstream proxy). Upstream's open PR #2428 does the same offload its own way.

**Measure the resolver in ACA, not in the devcontainer.** ACA injects `options ndots:5` plus four
search domains. Against a nameserver that never answers, one `getaddrinfo` took **22.75 s** (8 UDP
queries), against 12.74 s in the devcontainer. `az containerapp exec … cat /etc/resolv.conf`
settles the question.

**`asyncio.to_thread` moves a blocking call off the loop but does not bound it.** On ACA the default
executor has 8 threads, because `os.cpu_count()` reports the node rather than the cgroup and Python
3.12 has no `os.process_cpu_count()`. Its queue is FIFO and unbounded, and cancelling a request does
not reclaim the thread, which stays parked for the full resolver timeout. So healthy resolves queue
behind dead ones. The intended bound is `RES_OPTIONS="timeout:2 attempts:2 ndots:1"`, glibc's
per-process override, which needs no root. Against a replay of ACA's resolver config it brought a
dead-nameserver resolve from 22.75 s to ~4 s, and it should cut happy-path DNS about 5×, since a
render makes 10–40 uncached resolves. The offload and the bound complement each other.

**`RES_OPTIONS` has never been verified inside the ACA container.** Verified locally (2026-08-05): a
real `supervisord` hands the child `RES_OPTIONS=timeout:2 attempts:2 ndots:1` with quotes stripped.
Not verified: that it reaches gunicorn on a replica, and that glibc honours it there. The failure
mode is silence, because glibc ignores options it cannot parse and the result looks like success.
The variable is set on `[program:gunicorn]` in `supervisord.conf`, not on PID 1, which is supervisord,
so `cat /etc/resolv.conf` cannot show it, and neither can PID 1's environment. To verify, read the
gunicorn process's `/proc/<pid>/environ` via `az containerapp exec` (it needs a pty, see
AZURE_OPERATIONS.md §7; a 2026-08-05 attempt hung), or add a boot log line that prints the variable
from inside the app. Either shows the variable arrived, not that glibc parsed it. A timing test is
harder to read than it looks: the 22.75 s → ~4 s replay made the *configured* nameserver silent,
while in ACA the configured nameserver is the platform's recursive resolver, so a domain with a dead
authoritative server measures that resolver's behaviour as well as ours.
`tasks/done/egress-proxy-blocks-the-event-loop.md` §"What I am least sure of".

**A host with no DNS answer is `origin_unreachable` at 200, not an SSRF 400.**
`egress_broker._resolve` maps `socket.gaierror` onto the same `EgressBlocked` as a policy refusal,
so dead domains used to reach MAS as `400 URL blocked (SSRF protection)` with no `failure_class`.
The fix lives in `api.py` alone. When the SSRF check raises, `_host_has_no_address()` decides
whether the host simply has no address, and if so `OriginUnresolvable` maps to `origin_unreachable`.
The seven other endpoints that share `validate_url_destination` keep their opaque 400 on purpose.
This path costs ~0.08 s and no render slot. The streaming path still returns the old 400 (MAS never
streams). It also mislabels `render_mode` (see [Logging and counting](#logging-and-counting)).

**A host that resolves but never answers costs one connect timeout per navigation leg, now 15 s.**
Measured through a local blackhole:
- Chromium's own 30 s proxy-connect timeout binds first, and our `EgressProxy.DEFAULT_CONNECT_TIMEOUT_S`
  pre-empts it exactly and linearly (12 s gives 12.02 s);
- without the pinning proxy the wait is **134 s**, so the proxy is accidentally what caps it.

It was lowered from 30 to 15 s on 2026-08-05, not to 10 s. The trade-off: an origin whose handshake
would have finished between our timer and Chromium's becomes `origin_unreachable` at 200, which is a
silently dropped page. For the cost per request, multiply by `1 + max_retries`, plus the patchright
leg if it fires.

**On plain `http://`, whatever the proxy replies with is rendered as the page.** We used to answer a
failed connect with `_BLOCKED`, a 403 whose body reads `URL blocked`. Our own detector then read
that as the customer blocking us: `origin_blocked`, plus a wasted patchright leg, 16.1 s in total.
Closing the connection without a reply gives the honest `origin_http_error` (`ERR_EMPTY_RESPONSE`)
in 0.5 s. A 502 or 504 doesn't work either, because its empty body trips the inference tier, which
retries. The `https://` CONNECT path keeps `_BLOCKED`, which is fine there: Chromium turns a non-200
reply to CONNECT into `ERR_TUNNEL_CONNECTION_FAILED` and never renders it.

---

## Render timing and retries

**`page.content()` and `page.evaluate()` have no timeout.** The Python client sends no timeout field,
so the driver arms no timer. The call waits on the frame's execution-context promise, and a
navigation can replace that promise forever. `page_timeout` does not cover these calls. They are
bounded by `browser_adapter.bounded_evaluate()` and by
`AsyncPlaywrightCrawlerStrategy._capture_html()`, which settles and retries within a group deadline.
Any new `page.*` call that carries no protocol timeout needs the same wrapping.
`tasks/done/render-retry-unbounded-hang.md`.
`[merged v0.9.5]`: our wrappers auto-merged; upstream still calls `page.content()` unbounded in
several places (shadow-DOM fallback and others). Our wrappers stay merge surface.

**The patchright retry needs a longer capture wait than the first attempt.** A different engine with
the same budget cannot resolve a challenge that already outlasted the first attempt.
`aitosoft_patchright_fallback` therefore clones the config with
`delay_before_return_html = max(current, retry_capture_wait_s)`, which is 10.0 s in config.yml.
Measured: the retry leg costs W + 1.22 s with zero extra page loads. Don't raise the global wait
instead, because every fetch pays it (~267 render-hours per sweep). This retry goes through
`clone()`; see [Request contract](#request-contract-and-config-defaults).
`tasks/done/challenge-interstitial-resolve.md`.

**MAS's capture point is not `delay_before_return_html` alone.** With `remove_consent_popups: true`
the order is: the delay, the image-dimension pass, the consent snippet (whose in-page "wait for CMP
animations" is 500 ms), the driver's own `page.wait_for_timeout(500)`, then capture. So MAS's 2.0 s
captures about 1 s later than the number says. Upstream #2139 (`b536bf5`, v0.9.5) made the in-page
wait run only when a consent action fired, which moved the capture 0.5 s earlier on every page
without a banner. Measured through two real servers on loopback: a page painting at 2.8 s or 3.0 s
went from 1 navigation (~3.3 s) to 3 navigations (~16 s, blank capture → tier-3 `minimal_text` →
anti-bot retry → patchright), and on a host where the patchright leg fails it would be lost.
`[merged v0.9.5]`: kept unconditional; `test_the_capture_point_includes_the_consent_wait` (paints at
2.8 s, must take 1 navigation) goes red if anything moves it again. How many real pages paint in that
window is unmeasured.

---

## Consent and overlay scripts

**`remove_overlay_elements` deleted accountor's page in January. Cookiebot did not.** The 2026-01
symptom was 99,649 B of `html` → 230 B of `cleaned_html` → 31 tokens, and it was blamed on a cookie
wall. The stored capture says otherwise. The surviving 7,805 B body carries
`style="margin-right: 0px; padding-right: 0px; overflow: auto;"`, which is exactly what
`remove_overlay_elements.js` writes to `<body>` and nothing else in the codebase writes, and it has
zero content elements left. What fixed it that day was turning `magic` and `remove_overlay_elements`
off. `remove_consent_popups` did not exist until upstream `3fc7730` (2026-02-11). Today no
successful accountor capture contains a `CybotCookiebotDialog` element, and the site produces zero
generic consent matches. **Whether `remove_consent_popups` does any work on accountor is not
established.** One request with it set to `false` would settle that (Tier 1 host, not burned).
The January harness is the lesson in [Method](#method-lessons): its control shared the cause.

**The `rgba` test in `remove_overlay_elements.js` was always true.** By default,
`getComputedStyle(el).backgroundColor` returns `rgba(0, 0, 0, 0)`, so `.includes("rgba")` matched
everything. The rule degenerated into "remove every visible fixed or absolute element". Measured: it
deleted an absolutely-positioned hero that contained the contacts, at `success: true`. The script
now parses the alpha and treats only `0 < a < 1` as a scrim. **Still don't recommend this flag**
(MAS sends `false`). The fix removes one degenerate clause, but the rule keeps its appetite: its size
rule removes full-width fixed elements, and it removes every empty block element.
`[merged v0.9.5]`: the overlay snippet now uses upstream's `isDocumentStructure` guard and drops its
50 ms trailing wait; our alpha fix and body null guard stay. In the *consent* snippet, upstream
`b536bf5` (#2139) made the in-page 500 ms wait run only when a consent action fired. That moved MAS's
capture point 0.5 s earlier on every page without a banner (see [Render timing](#render-timing-and-retries)),
so the merge kept it unconditional; `test_the_capture_point_includes_the_consent_wait` pins it.

**`remove_consent_popups` is upstream's flag, MAS sends it on every request, and it used to delete
pages.** Upstream `3fc7730` (v0.8.5) owns the flag and all 140 container selectors: 120 named vendor
selectors, plus 20 generic ones (18 `[class*=…]`/`[id*=…]` substring patterns, `.cc-banner` and
`.cc-window`). Counts re-derived 2026-11-03. Our diff adds guards and counters only.

Phase 3 used to call `el.remove()` on whatever a generic selector matched. Enfold puts
`av-cookies-no-cookie-consent` on `<html>` to mean consent is *switched off*, so we deleted the
document. There were four failure shapes:
- `<html>` matched → 15 B capture → 500;
- `<body>` matched → head-only capture → 500;
- an inner element holding content matched → 200, `success: true`, `failure_class: none`, with 99.5 %
  of the markdown kept and the contacts gone. This one was **silent**;
- a Phase-1 "Accept" click that navigates → the wrong page, delivered in full, at 200. Also
  **silent**.

Fixed 2026-08-06. A structural guard (`documentElement`, `body` and `head` are never removed) now
sits in both snippets, and the generic selectors observe instead of removing. The click-navigation
channel is detected and logged (`CONSENT NAVIGATION`) but not fixed; its ceiling is 0.046 % of
companies. `tasks/done/consent-scripts-delete-the-page.md`.

**Measured on both sides: the generic selectors deliver zero banner value, and their harm is
colliding with document roots.** Segment 2 (2026-08-06, 50 companies, 261 renders) logged 27
`CONSENT DECLINED` lines on 3 companies, every one `node=html structural=True`, i.e. pages that had
been 15 B captures at 500.
- `structural=False`, the silent inner-element channel: 0.
- `CONSENT STRUCTURAL` (a *named* selector hitting a root): 0. It was still 0 across the final
  sweep's 186,178 requests, so the named-selector census holds. Count it with `indexof()`, not
  `contains`; see AZURE_OPERATIONS.md.
- Genuine click-navigations: 0. The 3 lines were all fragment-only false positives
  ([Logging and counting](#logging-and-counting)).

MAS can see what survived, which we cannot: 95 matched containers, 0 containing any contact data
across 34,533 chars, under several deliberately wide nets. Both sides independently count 27 roots
on 3 companies. So argue the upstream PR on the root collision, which needs neither corpus, and on
"hide, don't remove", which is what every maintained consent system does.
`tasks/done/segment-2-counter-readout.md`, `tasks/file-upstream-prs.md`.

**The generic selectors were kept, not deleted, so that they could be counted.** A deleted selector
cannot report what it would have removed. Neither archive can size that loss after the fact either,
because the element is gone before anything is captured. Keeping the selectors removal-free turned
the question into a counter: `CONSENT DECLINED`, logging `n`, `chars`, `pagechars`, `node`, `class`
and `structural` (in `AsyncPlaywrightCrawlerStrategy._report_consent_pass`).

**How to read a `CONSENT DECLINED` line.**
- `pagechars` is `document.body.innerText` at the consent pass: rendered visible text, with no link
  URLs and no hidden content. It is not markdown length. `kubler.fi` reads `pagechars=2634` against
  55,545 markdown chars, 48,673 of them `[text](url)` constructs. Never compare the two units.
- The `chars/pagechars` ratio does not separate a wrapper that held the contacts (9.4 %) from a real
  cookie bar (7.3 %). Absolute `chars` does (1,168 vs 92).
- `node` separates them better still: `html`/`footer`/`section`/`main` is a page region, while
  `div.cookie-notice-bar` is a banner.

The counter sizes the population. Only the removed element's *content* decides whether a removal
was a loss.

**A structural-guard fixture has to use a *named* selector, or it passes for the wrong reason.** Now
that the generic selectors don't remove anything, Enfold's `<html class=…>` triggers nothing
destructive. Every html/body consent fixture would stay green even with the guard reverted.
`/consent/named-root` (`<body id="cookie-notice">`, one of the 120 named selectors) is the shape only
the guard can pass. Likewise the overlay fixture is 280×160 on purpose: the size rule legitimately
removes a full-width hero, which would prove nothing about the `rgba` fix.

---

## Parse collapse: the body lost between render and markdown

**A 15-byte capture is `<!DOCTYPE html>`, and the size is diagnostic.** When `documentElement` is
gone, Playwright's `content()` serialises only the doctype. An empty 200 gives 39 B, and a body that
*is* the text `<!DOCTYPE html>` gives 54 B. So 15 B means a script deleted the root; it never means
an empty origin. lxml then raises `Document is empty`, and that is where upstream's
`Crawl4AI Error: This page is not fully supported` placeholder comes from. Every `Near-empty content`
detector event in a 30-day window was exactly 15 B. Classify on the *shape*, not the byte count: a
padded `<head>` puts the same defect at 20,087 B.

**A capture with no `<body>` is permanent. A near-empty capture is not.** Chromium synthesises
`<body>` for every document it parses, so a missing `<body>` means a script removed it, and no retry
will rebuild it. That case is `render_defect` at 200, which is terminal
(`aitosoft_failure_class._document_root_is_gone`, checked in `classify_result` *after* the origin
branches). A near-empty but structurally intact shell stays `render_error` at 500, because it might
paint next time. Collapsing the two would re-open the `norex.com` inversion from the other side. As
a retryable 500 this cost 16 navigations per URL; Kübler paid it twice in segment 1 (32 navigations,
266 s, 26 % of the run). `tasks/done/total-loss-is-permanent-not-transient.md`.

**A nested `<noscript>` deletes the whole page.** `<noscript>` cannot nest, so the outer element
never closes and libxml2 swallows everything after it. Measured on `kiertopakkaus.fi`: 312,628 B →
97 B `cleaned_html` → 1 B markdown, at 200 `success: true`. The census found 406 pages on 70 hosts.
Fixed by `content_scraping_strategy.strip_noscript()`, which removes noscript elements pre-parse
(removal is correct when rendering with JS on).
`tasks/done/noscript-collapses-body-to-empty-markdown.md`.
`[merged v0.9.5]`: both fixes are in the tree, ours runs first, and
`test_text_after_a_balanced_noscript_survives` pins what upstream's alone would lose. Upstream's fix,
`unwrap_orphaned_noscript()` (community PR #2284,
in v0.9.5), sits at the same `document_fromstring` call. It *keeps* noscript contents when the tags
are unbalanced and leaves a *balanced* `<noscript>` in the tree. `_scrap` later removes that element
with `getparent().remove()` (v0.9.5 `content_scraping_strategy.py` ~827, unchanged on develop at
`cd61be1`), and lxml's `remove()` discards the element's `.tail`, i.e. the text after it. Executed
2026-11-03: `<p>Soita meille <noscript>…</noscript>numeroon 010 123 4567 …</p>` comes out as
`Soita meille ` on pure v0.9.5, phone number gone, while ours keeps the whole sentence, because
`strip_noscript` removes the element from the string before parsing
(`tmp/upgrade-v0.9.5-evidence/review/tail_test.py <tree>`). Upstream acknowledges it as #2416
(2026-10-19): the pattern is in ~11 places and a maintainer said on 2026-11-02 that a fix is in
progress. **Keep our `strip_noscript` alongside theirs until #2416's fix lands** (it auto-merges).
#2416 is wider than `<noscript>`: text after an inline `<style>`, `<link>` or `<meta>` is dropped the
same way, and **that happens on our tree today**, because `strip_noscript` covers only `<noscript>`.
Take upstream's fix when it ships; don't build our own.
0 of 74 stored captures have text after a balanced `<noscript>` (`tasks/upgrade-upstream-v0.9.5.md`),
so the population is small, but the loss is silent and it is contact data. None of the browser
fixtures has this shape either; it needs a test.
**Measured on real WAA pages, 2026-11-04: 0 of 630 change.** MAS stored raw HTML for joint run (ii)
(631 pages, 75 companies; their `WAA_STORE_RAW_HTML`). Re-scraped offline through today's scraper and
a tail-preserving one (`drop_tree()` at the 11 sites that don't already move `.tail` by hand):
identical markdown on every page. Control 1: the offline path reproduces the markdown production
returned on 584/630 exactly; the other 46 differ only in links resolved against `url` instead of
`final_url`. Control 2: a synthetic page with an inline `<style>`, `<link>` and `<meta>` mid-paragraph
loses phone, email and address on today's tree and keeps them on the patched one. So the rate is
under ~0.5 % of pages (95 % bound): **wait for upstream's fix.** Harness, patch recipe and control:
`tmp/research/tailloss/` (gitignored); the raw pages are kept as the offline corpus
(`tasks/optimization-experiments.md` §Instruments).

**An *unclosed* `<noscript>` still deletes the page, and the offline suite cannot see it.** libxml2
auto-closes the element, so `test_noscript_body_collapse.py` reports the shape as fixed. Chromium
instead enters raw-text mode and serialises the rest of the document *inside* the element,
`</body></html>` included. `strip_noscript()` then correctly removes the element and takes the page
with it. Only a browser in the loop shows this; `fixture_origin` found it on 2026-07-31. The
html2text recovery below rescues it.
`[merged v0.9.5]`: upstream `6b5a0d4`/`ba8b722` (in v0.9.5) claim to fix an unclosed noscript.
The fixtures cannot arbitrate between the two fixes: measured for the v0.9.5 upgrade, all 21
noscript/collapse fixtures still pass with *both* defences disabled, because Chromium's
serialisation plus our html2text recovery cover them (`tasks/upgrade-upstream-v0.9.5.md`).

**Four markup shapes swallow the body, and no parser choice fixes the root cause.** Enumerated
through the browser at 73 KB on 2026-08-01 (`fixture_origin.py` `/collapse/{shape}`):
`unclosed-noscript`, `unclosed-script`, `deep-nesting` (libxml2's depth limit) and
`unterminated-comment`. These are three mechanisms, all deterministic. `deep-nesting` is harmless at
1.5 KB and fatal at 73 KB, so enumerate with padded pages or you will miss shapes.
`content_source="raw_html"` prevents only `unclosed-noscript` and `deep-nesting`.
`unclosed-script` and `unterminated-comment` are lost at the *tokenizer*, which is HTML5 spec
behaviour and identical in libxml2 and `html.parser` (priced 2026-08-05).
`tasks/done/cleaned-html-collapse-guard.md` (part 2, root cause, is open).

**The collapse guard compares visible text with markdown, never HTML bytes.**
`aitosoft_collapse_guard` takes visible-text chars in and markdown chars out. It fires only when
visible text is ≥ 500, markdown is < 500 (it returns early at `produced >= 500`) and the ratio is
≤ 0.10. The thresholds were measured on 37 stored real captures: the 31 healthy content pages have
a minimum ratio of 1.311, and the other 6 (cookie-wall shells and a challenge page) had nothing to
lose. Byte ratios fail in both directions:
- the healthy control padded to 73 KB of inline CSS gives the *same* 0.0036
  `len(html)`→`len(cleaned_html)` ratio as a collapsed page, and accountor's capture was 99,649 →
  230 B;
- `unterminated-comment` keeps 74,523 B of `cleaned_html` that still *contains* the content, and
  yields no markdown at all.

**A detected collapse can often be recovered.** Running `crawl4ai.html2text.HTML2Text` over the same
rendered HTML returns the full body for `unclosed-noscript` (1,265 chars, identical to the healthy
control) and for `deep-nesting`. It returns nothing for `unclosed-script` and
`unterminated-comment`. Recovered pages go out as ordinary successes, logged as `COLLAPSE
RECOVERED`; unrecovered ones become `success: false`, `render_defect`, logged as `RENDER DEFECT`.
Reuse the *converter*, not `aitosoft_static_mode`'s pipeline: `_fetch_static_one` runs
`_strip_hidden_decoys()` first, which `decompose()`s every `noscript`. On an unclosed one that
deletes the whole re-serialised document (1,265 chars → 0).

**A recovery must clear the ratio floor, not just the 500-char floor.** Accepting a recovery on
MAS's 500-char degenerate floor alone would let a 599-char rescue of a 41,408-char page out as
`success: true`, with 40,809 chars silently gone. On the normal path we have no evidence of loss,
but here the guard has already proved it, so the bar is higher. Measured headroom of real
recoveries above 0.10 is 10–28×. (`aitosoft_collapse_guard._is_a_real_recovery`.)

**No guard can see a loss that happened before the capture.** The collapse guard exits on
`not success` (total loss) and at `produced ≥ 500` (partial loss). It could never fire on a partial
pre-capture deletion anyway, because visible text in and markdown out shrink together. Neither
repo's archive can size this kind of loss either, since the element is gone before anything is
stored. "We grepped and found zero" is the only possible answer, and it means nothing. Count at the
point of removal, the way `CONSENT DECLINED` does.

---

## Block detection (`antibot_detector.py`)

**Judge the final redirect hop.** `status_code` is the *first* hop of a redirect chain, while the
body comes from the *last*, whose status is kept as `redirected_status_code`. Use
`antibot_detector.effective_status()` or `aitosoft_failure_class.effective_status_of()`. When the
detector judged the 301, every redirect-to-block page went through as a success (fixed 2026-07-30).
`api.py` also rewrites the envelope's `status_code` to the final hop.
`tasks/done/redirect-status-blinds-block-detection.md`.

**`response_headers` is also the first hop, and there is no final-hop equivalent.**
`AsyncPlaywrightCrawlerStrategy._crawl_web` walks `request.redirected_from` back to the earliest
response (`# keep earliest`) and takes both status and headers from it. `models.py` has
`redirected_status_code` but no `redirected_response_headers`. So any `Content-Type` logic silently
does nothing through `http→https` or `apex→www` redirects, and MAS's agent constructs apex URLs. Found
2026-08-09; upstream develop is the same.

**Blocks are IP-based, not fingerprint-based.** Two different browser engines got identical blocks.
A better fingerprint will not unblock a host; see the parked `tasks/residential-egress-retry-path.md`.

**Which gates read visible text and which read bytes.** The *evidence* tiers (challenge prose, the
block-notice tier) gate on visible text. Tier-2 patterns run at any size on 403/503, but still need
`len(html) < 10 KB` on other 4xx/5xx. The *inference* tiers keep their byte bounds on purpose: tier-3
structural (`_STRUCTURAL_MAX_SIZE`, 50 KB) and near-empty-200 (100 B). The reason for the text gates:
one vendor pads its block page to 80 KB, so `403 - Forbidden` in 48 chars of visible text passed as
content at origin status 202. `monidor.com` in `test-aitosoft/artifacts/` is the same defect at
11.5 KB. `tasks/done/detector-round3-evidence-vs-inference.md`.

**Tier-2 patterns never see HTTP 200, which is why the challenge tier exists.** `is_blocked` only
reaches tier 2 through the 4xx/5xx branches, but challenge interstitials are served at 200, so
`Checking your browser` had never once fired. The challenge tier (2026-07-30) runs on any status,
gated on visible text under 1,500 chars. `tasks/done/antibot-detector-challenge-blindspot.md`.

**A notice counts only in a title or heading, or at ≥ 50 % of the page's visible text.** About 15 of
MAS's 22 `Access Denied` hits were Shopify storefronts with a `/pages/access-denied` menu link. Our
fixture for that case has 247 visible chars, which is under any sane low-text gate, so a text gate
alone would re-open the false positive. (`_BLOCK_NOTICE_MIN_COVERAGE = 0.5`; the tier-2 `Access
Denied` pattern is title/heading-only.) `tasks/done/detector-round3-evidence-vs-inference.md`.

**A block verdict must carry *why*.** `is_blocked` returns True both for "the origin said so" and for
"we came back with nothing". Mapping both to `origin_blocked` once reported upstream's "not fully
supported" placeholder (`norex.com`) as the customer's site blocking us. Inference reasons
(`Structural:`) now map to `render_error`. Discarding the reason must not discard the status: 403
and 503 still mean block, and other 4xx mean `origin_http_error`.
`tasks/done/detector-round3-evidence-vs-inference.md`.

**Check which branch fired before believing a diagnosis.** The padded-403 task file said the four
caught hosts proved the pattern side already worked. In fact no pattern matched that body at all.
They were caught by the 403 status fallthrough, and the block-notice tier was the missing half.
Likewise `/block/padded-403` was unfaithful on exactly the axis that mattered. It served a bare
`<div>` (0 content elements, 2 tier-3 signals), where the real page has `<h1>`+`<p>` (2 elements,
1 signal). A fix validated on that fixture would have closed none of the four real hosts.
`[merged v0.9.5]`: upstream `2e30e54` adds `AsyncCrawlResponse.placeholder_html` so
that both anti-bot call sites in `async_webcrawler` skip PDF stubs. It auto-merged next to our
`effective_status` feed; all three `is_blocked` sites still receive `effective_status(...)`.

---

## Failure taxonomy and wire status

**Origin failures are never our 5xx.** Every result carries `failure_class`
(`deploy/docker/aitosoft_failure_class.py`). Origin-caused failures return HTTP 200 with
`success: false`, and 5xx is reserved for faults of ours that a retry might clear. This matters
because MAS's retry decision keys on the wire status alone; `failure_class` is received and logged,
but not read (`tmp/mas-repo-messages/09-from-us-taxonomy-answer-and-zero-traffic.md`, 2026-07-31).
`tasks/done/origin-vs-crawler-failure-classification.md`.

**One class means one wire status, decided in one place: `http_status_for()`.** Both render modes
go through `server._crawl_response`, and `api.py`'s exception path calls the same function. The axis
is **permanence, not ownership**: `NON_RETRYABLE_CLASSES` = the origin classes + `render_defect`,
`bad_request` and `unrenderable_content` → 200; `render_timeout` → 504; anything else → 500.
`render_error` used to be 200 in static mode and 500 in full mode, the same class with opposite retry
behaviour. Don't add a second mapping site; add to the vocabulary instead.
`[merged v0.9.5]`: upstream `130a382` deleted the "all results failed → 500" block
in `server.py` that `_crawl_response` replaces, so upstream now always answers 200. Ours was kept; it
also now gives every result keyed `links`/`media` (`normalize_result_shapes`).

**`arun` does not raise. It returns a failed result.** Upstream wraps the whole body in `try:` and
returns `CrawlResult(success=False, error_message=…)`. So `classify_result`, not
`classify_exception`, decides most failures. The tell is in the log prefix: `Crawl request failed:`
is built only in `server._crawl_response` (the result path), while the exception path emits JSON.
What *does* raise is the pre-admission seed check (`OriginUnresolvable`) and failures outside `arun`
(browser launch, pool acquisition).

---

## Logging and counting

**Put counters on `logging.getLogger(__name__)`, never on crawl4ai's `AsyncLogger`.** `AsyncLogger`
fails in three ways at once (measured 2026-08-06):
- it prints only `if self.verbose or force_verbose`, and `verbose` is client-settable through
  `BrowserConfig`;
- its rich `Console` has `width=200`, so a longer line becomes two Log Analytics records, and a
  query on two fields then loses rows;
- it eats `[`: `_log` inserts values raw and escapes the template as `[[`, which is not a rich escape,
  so `[class*="cookie-notice" i]` renders as the empty string.

`COLLAPSE RECOVERED`, `RENDER DEFECT`, `RESULT FAILURE` and the `CONSENT *` lines all use stdlib
logging.

**How to count failures.** Count the `failure_class=` field across all three tokens that carry it,
`RESULT FAILURE`, `ORIGIN FAILURE` and `TERMINAL FAILURE`, never one token alone. Then add the
`RENDER DEFECT` lines separately, because they carry no `failure_class=` field. The tokens sit on
mutually exclusive paths in `handle_crawl_request`, and no request emits two of them (re-derived
2026-11-03 from the code):
- `RESULT FAILURE` comes from the result loop, for every failed result the collapse guard did not
  claim.
- `ORIGIN FAILURE` (origin classes) / `TERMINAL FAILURE` (anything else non-retryable, and the 504
  branch) come from the `except` block. That is where the pre-admission seed check lands, and the
  seed check is the *dominant* producer of `origin_unreachable`. It costs no render slot and returns
  200. Querying only `RESULT FAILURE` reported 9 `origin_unreachable` events when the truth was 21 on
  13 companies, a 57 % undercount (2026-08-06).
- `RENDER DEFECT` is an unrecovered parse collapse. Its class is `render_defect`, but the line has no
  field, so a `failure_class=render_defect` query sees only the root-gone half, which logs as
  `RESULT FAILURE`.
- An exception-path 500 logs none of these, only the `Crawl error:` traceback that every exception
  gets, then `server.py`'s `server error 500`.

**Count requests, not marker lines.** The dead-domain marker `DNS: host does not resolve` sits
inside an exception message, and the `Crawl error:` traceback repeats it, about 4 console lines per
request (sweep: 5,252 lines for 1,313 requests). Count `ORIGIN FAILURE` with
`failure_class=origin_unreachable` instead.

A second instrument, the ingress-minus-`RenderGate ADMIT` identity, is in AZURE_OPERATIONS.md §5.3.
Use the form given there. The older form, "= pre-admission refusals + 429s", is wrong: a memory-guard
429 is refused *after* admission and has already logged `ADMIT`. It reconciled in segment 2 only
because segment 2 had no memory 429s.

**Moving a class off 5xx deletes its only log line unless you add one.** Failed results used to be
visible only because they produced a 500, and `server.py` logs 500s. `RESULT FAILURE` (2026-08-02)
exists because `unrenderable_content` was about to ship at 200 with no counter at all. When you
change a class's wire status, check what used to log it.

**We cannot count origin 404s. MAS can.** `RESULT FAILURE` only fires for *failed* results. A 404
that serves a normal styled "page not found" body renders fine: `success: true`,
`failure_class: none`, no log line anywhere, yet the envelope still carries `status_code: 404`. So
`failure_class=origin_http_error` counts only the 404s that also failed to render. In segment 3 we
reported 2 and MAS's envelope-side `status >= 400` count found 26 on 26 URLs. **`failure_class`
answers "whose fault"; `status_code` answers "what did the origin say". Never substitute one for the
other.**

**`CONSENT NAVIGATION` fires on fragment-only changes.** `_report_consent_pass` compares `page.url`
before and after with the fragment included. All 3 lines in segment 2 were `www.se.com` `#products`
false positives. The code still does not strip the fragment (checked 2026-11-03), so strip it when
counting.

**A static-mode request to a dead domain is reported as `render_mode: "full"`.** The seed check runs
before the static short-circuit, and the exception path's `failed_result(...)` call omits
`render_mode`, which defaults to `"full"`. This is open task item 2 in `tasks/README.md`. Static-mode
failed fetches also log no `failure_class`. That is real, but static mode was used 0 times in
186,178 requests, so it is zero-width.

---

## Output: markdown, media and payload size

**Use raw markdown, not `fit_markdown`, for contact extraction.** `PruningContentFilter` removes
contacts at thresholds ≥ 0.35.

**An image's `desc` used to be the whole page, copied into every image and every srcset variant.**
`find_closest_parent_with_useful_text` walks *up* the DOM until an ancestor has enough words, then
returns that ancestor's entire subtree text. Image containers have no words, so on a catalogue grid
the walk passes all of them and stops at the container that also holds the page prose. `add_variant`
then copies that text into every srcset variant. On `www.thermokon.fi`, 1,104 of 1,160 entries
carried the same 154,798-char string: `media` was 231,708,619 bytes, 56× the rest of the result, at
200 `success: true` with no log line. With MAS's 210 s per-attempt timeout, that company was lost
deterministically.

It is capped at `MEDIA_DESCRIPTION_MAX_CHARS = 200` (2026-08-09). The capped response is 538,747 B
(430× smaller), with `cleaned_html` and markdown byte-identical and all entries kept. The cap sits in
the shared walker, so it also truncates `<video>`/`<audio>` `description`. That is inert, because
`MediaItem` has no such field. The same document yields `desc: None` when minified and the whole
page when pretty-printed, because the stop condition ANDs `.text` (indentation whitespace is truthy)
with `text_content()`. `tasks/done/media-desc-duplicates-the-page-per-image.md`.

Two lessons: payload size is a failure mode nothing in either repo measures
(`ContainerAppHTTPLogs.BytesSent` is the only surface), and a field with zero consumers still costs.
`[merged v0.9.5]`: upstream's walker is still uncapped at v0.9.5 and on develop; ours auto-merged. The cap is merge
surface, and one of the two PRs worth filing (`tasks/file-upstream-prs.md`).

**The `desc` cap does not bound a media entry, and two amplifiers remain.**
- `alt` is copied into every variant by the same `add_variant`. Measured: a 50,000-char `alt` with 5
  srcset entries gives 300,879 B of media from a 50,244 B document. That growth is linear in the
  document.
- `media.tables` is not linear. `table_extraction` defaults to `DefaultTableExtraction` and runs on
  every request, and it expands `colspan` with an unvalidated `int()` taken from the page. Measured:
  - `<th colspan="50000">` on a 4,624 B page → 4,504,226 B of `media`;
  - `colspan="2000000"` leaves the wire unchanged but costs +91 MB RSS from 905 bytes of HTML;
  - `colspan="auto"` makes `int()` raise, and the table is silently dropped at `success: true`.

Not fixed, deliberately: these need pathological markup and have never been seen in production. But
nothing bounds a *response* anywhere (`limits.max_body_bytes` bounds the request). That is why a
response-size backstop is parked, not unnecessary.
`[merged v0.9.5]`: upstream `ee1a295` clamps colspan/rowspan to 1000 (junk counts as
1) in its new body-row grid. **Header rows (`<thead>` and the implicit first row) still use bare
`int()`**, so the measured `<th>` case and the `"auto"` drop survive the merge.

---

## Downloads and PDFs

**A download navigation is `unrenderable_content` at 200: nobody's fault, and permanent.** Chromium
refuses to commit a navigation to a download. `Content-Disposition: attachment`, inline `text/vcard`
and `application/octet-stream` all raise `Page.goto: Download is starting` (matched in
`aitosoft_failure_class`, `_DOWNLOAD_RE`). It is not `origin_http_error`, because upstream leaves
`status_code` null. `accept_downloads: true` does not rescue it. The class does fire: 12 times in the
final sweep on 8 hosts (five `/vcard/` URLs, two attachment PDFs, one `.ashx`). A claim that it had
"never fired" was contradicted six hours after it was written. A "has never fired" claim has an
expiry date. `tasks/done/download-navigation-is-not-a-render-error.md`.

**Inline `application/pdf` is the exception.** A Chromium carrying the PDF-viewer extension, which
production's real Chrome does, *renders* the PDF into a 174-byte shell with no visible text and no
`<embed>` (it is in shadow DOM). Tier-3 inference calls that blocked → `render_error` → 500, which
MAS retries. Measured on both browser arms on 2026-08-09: 4 of 5 download kinds behave identically,
and only `pdf-inline` diverges. MAS currently removes PDFs at dispatch.
`[merged v0.9.5]`: `pypdf` is now in `deploy/docker/requirements.txt` (so in the image), the PDF
path selected by `scraping_strategy: PDFContentScrapingStrategy` is kept in `api.py` (opt-in; MAS
doesn't), and `placeholder_html` makes the anti-bot checks skip PDF stubs. Production's inline-PDF
500 is unchanged: it comes from the browser path, not `PDFCrawlerStrategy`.

**Whether PDF text extraction regressed, and who caused it, is not established.** MAS holds April
captures with 11,101–45,118 chars of extracted PDF text, while today the same class returns the
174-byte shell and a 500. MAS attributes that to our browser change, but that is their inference,
not a provenance check. This repo can't reproduce it either way. `pypdf` is not in our image
(`deploy/docker/requirements.txt`, `INSTALL_TYPE=default`), the crawl path has no PDF branch, and
neither browser arm yields PDF text. The only in-repo candidate is `render_mode: static`, which has no
content-type gate, but it would emit `%PDF-1.4 …` or mojibake, not prose. One stored April row's
`render_mode` plus the first 200 chars of its markdown would settle it. Nothing is being built.

---

## Browser pool and memory (code level)

Readings of the memory guard, its threshold, OOMs and restarts are in AZURE_OPERATIONS.md. This
section covers the code.

**A pooled browser's memory cost belongs to the process, not to the page.** `/ok` (1.5 KB, no images)
costs +142.8 MB per browser, and `/heavy` (236 KB, 17 images, the shape of the median of 62 stored
captures) costs +170.0 MB. That is only 19 % more (`test-aitosoft/experiment_pool_memory.py`).

**Per-browser memory is a ratchet, and navigating to `about:blank` does not unwind it.** Navigating a
retained page to `about:blank` returns 0.5 MB of anon memory even when the page held a fully
committed 100 MB JS heap; the same run shows the heap going in at +100.5 MB, so the instrument can
see it. A browser's floor is the heaviest page it ever loaded, and only closing the browser resets
it. `tasks/done/pool-browser-retains-last-page.md` (closed, refuted).
`[merged v0.9.5]`: upstream `6ccf610`/`47ea8d7` add `max_pages_before_recycle`, and
`15f4b29` defaults it to 200 in `DEFAULT_CONFIG`; without the key in `config.yml` the deep-merge would
switch recycling on. **It is off: `config.yml` sets `max_pages_before_recycle: 0` and `get_crawler`
does not apply `_apply_pool_defaults`, until upstream PR #2432 ships.** The field is still in the
untrusted allowlist (it was at v0.9.2 too), so a client could opt a browser in; MAS doesn't. Two reasons:
- **It is not known to bound the ratchet.** `BrowserManager._maybe_bump_browser_version()` bumps a
  version in the *context* signature and `context.close()`s the old contexts, inside the same
  Chromium process (read on develop, 2026-11-03). Our measurement says only closing the browser
  resets the floor. Unverified either way.
- **It can wedge the replica.** Upstream #2419 (opened 2026-10-19, maintainer-confirmed 2026-10-21):
  `get_page()` leaks a context refcount when a crawl is cancelled, and after a recycle
  `_maybe_bump_browser_version()` waits forever for it to drain, so every `/crawl` returns 504 until
  the container restarts (the reporter hit it every 10–14 h). Our `wall_clock_s` fence cancels
  crawls. That this reaches us is reasoned from the trigger, not reproduced. The fix is PR #2432,
  open, and `browser_manager.py` is unchanged on develop.

**A capped pool must never wait for a browser.** `release_crawler` takes the same `LOCK` that
`get_crawler` holds, so waiting inside `get_crawler` deadlocks with no 504, no 429 and no janitor
recovery. Evict an idle browser, or refuse with `RenderCapacityExceeded` → 429. Evicted browsers are
closed in a detached task bounded by `EVICT_CLOSE_TIMEOUT_S`, because `close()` has no timeout and a
wedged Chromium closed inline would hold the lock forever. `tasks/done/pool-residency-unbounded.md`.

**Every "we are full" must be a 429 with `Retry-After`, raised as `RenderCapacityExceeded`.** The
pool's memory guard used to answer 500 while RenderGate answered 429. MAS retries a 500 three times,
so memory pressure quadrupled its own load. The pool's refusals reuse `RenderCapacityExceeded`
because it is the only exception `api.py` maps to 429. A new exception type would fall into
`except Exception` and become a 500. Which gate refused is reported as `capacity_gate`; see
AZURE_OPERATIONS.md.
`[merged v0.9.5]`: upstream's `crawler_pool` still raises `MemoryError` on its memory refusal; ours
(429) was kept. `[revisit at next sync]`: dead-browser replacement (`3f9f790`) is develop-only, and
its janitor block would auto-merge into ours calling helpers that only exist on upstream's side.

**The replica's memory split between browsers and everything else is not settled.** The old claim
that 8 browsers "is the whole 4 GiB" never added up: 9 × 165 MB is about 36 %. That refutation
stands. The replacement fit, `mem% = 59.3 + 2.65 × browsers` (n=68, r²=0.22), is not settled: it
has three independent problems, all biasing browsers *down*. Two of them are the next two entries.
Don't quote a per-browser %, an intercept, or "the cap would not have helped" until the split is
re-derived from stored data. `max_browsers: 6` is correct under every candidate slope.
`tasks/done/replica-memory-baseline-unexplained.md` §"Why the fit is not settled".

**Regress on a control loop and you measure the controller.** The janitor's adaptive TTL used to
close browsers when memory was high, so high-memory samples carried fewer browsers, which biased any
browsers→memory slope toward zero. That timer-driven controller was removed on 2026-08-02 (TTLs are
constant now). **A narrower loop is still live**, and it was added the same day:
`crawler_pool.get_crawler`'s memory guard evicts one idle LRU browser on every refusal, then refuses
anyway (checked 2026-11-03). It fires only while arrivals are being refused, not on a timer, but
memory still drives browser count. Each eviction logs `memory pressure X%` as its reason, next to
the refusal's `💥 Memory pressure:` line. So any browsers→memory fit over a build since 2026-08-02
must drop the samples around those lines. Separately, the janitor's *poll rate* is still adaptive,
so its samples oversample high-memory states. Kill the loop and then measure, filter on the reason,
or use the offline instrument, which has no controller in it.

**A metric that changed cannot be regressed across the change.** The 68 pool-stats lines behind that
fit predate `13fcecb` (2026-08-01), which made `get_container_memory_percent` subtract
`inactive_file`. Their intercept is therefore in raw `memory.current`, page cache included, and
page cache is exactly what would sit in an unexplained baseline. Date the metric, not just the data.
Also: `_read_memory_stat`, `get_memory_breakdown` and `get_container_memory_percent` in
`deploy/docker/utils.py` are **ours**, not upstream's. Check with
`git diff upstream/develop -- deploy/docker/utils.py`.

---

## Testing fidelity

**On the devcontainer the browser suite doesn't run production's browser.** (It does inside a
built image, on real Chrome: TESTING.md "Inside a built image", since 2026-11-03.)
`browser_manager._build_browser_args`
drops `channel` whenever `chrome_channel == "chromium"`. That is a Windows workaround applied on
every platform, so Playwright launches `chromium_headless_shell`, which has no PDF viewer.
`fixture_origin._resolve_channel()` falls back to `"chromium"` when there is no `google-chrome` on
PATH, which is always the case on the arm64 devcontainer. `CRAWL4AI_FIXTURE_CHANNEL=chromium` cannot
rescue it, because it produces the same string that gets dropped. Production runs
`chrome_channel: chrome`. As a result, the download tests exercise the download arm, and
`pdf-inline` passes for the wrong reason.
`[revisit at next sync]`: upstream `a1bd6c8` (develop only) passes `channel="chromium"` again and
falls back to the shell, so the suite's browser will change and `pdf-inline` will go red for the true
reason. At v0.9.5 the local suite still runs the headless shell.

**CI runs only the offline half of `test-aitosoft/`.** Until 2026-11-03 no workflow ran it at all.
`aitosoft-tests.yml` now runs the pure-function suite on every push (Python 3.12, no browser, the four
`requires_corpus` tests skipped). The browser suite is still a local gate, and only as good as the
session that runs it.

**Offline (libxml2-only) suites cannot see browser-serialisation shapes.** The unclosed `<noscript>`
was invisible offline. A new failure class gets a `test-aitosoft/fixture_origin.py` route, driven
through the real production path, before any live host is touched (TESTING.md golden rule 0).

**A `raw://` URL is a full-fidelity load generator, with zero egress *if the HTML is
self-contained*.** `validate_url_destination` (`deploy/docker/utils.py`) returns early for `raw:`.
`AsyncPlaywrightCrawlerStrategy.crawl` still sends it through the browser whenever `needs_browser`
is set, which `remove_consent_popups` (on in every MAS request) does. So it exercises RenderGate, the
pool, a real Chromium launch, the consent pass and the collapse guard. Render time is a dial:
`delay_before_return_html` is on the untrusted allowlist, and wall time is about 1.3 s plus the
delay. Reach for it before any live host; unlike a third party, it is byte-identical across A/B
arms. **Replaying a stored real capture is not zero-egress:** the browser fetches every absolute
subresource and runs inline scripts, so it pulls the customer's assets and fires their analytics.
Strip those first; the details are in TESTING.md §"`raw://`".
`[merged v0.9.5]`: upstream caps untrusted `delay_before_return_html` at 60 s.

---

## Method lessons

**A control that shares the suspected cause is not a control.** All five January test presets set
`remove_overlay_elements: True`, *including `minimal`*, the control. No arm could reveal the flag as
the cause, so a workaround got recorded as a diagnosis, and the real mechanism (the `rgba` bug) was
found 6.5 months later. The same family: `/block/padded-403`, the 280×160 overlay fixture, and a test
suite that runs a different browser binary than production.

**Patch the layer *below* the one you are testing.** On 2026-08-05 a reverted exception class left
its `raise` behind, so `egress_broker._resolve`'s `except socket.gaierror` branch raised
`NameError`. It passed 229 offline tests, 54 browser tests, 316 upstream security tests and green
CI, because every test monkeypatched `resolve_and_pin` or `validate_url_destination`, the layer
above the broken line. Production returned `render_error` 500 for every dead domain, which MAS
retries three times. One live probe caught it ~8 minutes after deploy. Patching `socket.getaddrinfo`
is just as hermetic and runs the real branch, which is what `test_egress_dns_offload.py` does now.

**A consumer's "no issues" is not evidence of no data loss.** MAS called the 2026-08-01 run clean, yet
9 of its 328 pages, on 7 of 38 hosts, came back with 0 chars of markdown from 725–40,165 chars of
visible text. From their side that is invisible by construction, because a page with no contacts
looks exactly like a page that has none. Record what we measured, never what we were told.

**A fix for silent loss can open a new silent-loss channel.** When a guard has already proved a loss,
the bar for accepting a repair is higher than the bar on the normal path. See the recovery floor in
[Parse collapse](#parse-collapse-the-body-lost-between-render-and-markdown).

**Verify which branch fired, not just that a verdict came back.** See the padded-403 entry in
[Block detection](#block-detection-antibot_detectorpy).

**Fix the surface that runs, not the file you happened to read.** See the seed-check entry in
[Egress](#egress-dns-and-dead-hosts).

**Count at the point of removal, not at the outcome.** A loss that happens before capture leaves
nothing to find afterwards. See `CONSENT DECLINED` and the pre-capture entry under Parse collapse.

**Enumerate failure shapes at realistic size.** `deep-nesting` is harmless at 1.5 KB and fatal at
73 KB. A small fixture misses root causes, not just thresholds.

**Run every timeout test once with the timeout broken.** `test_connect_timeout_is_honoured` passed
from 2026-08-05 to 2026-11-03 with the connect budget at *any* value: its CONNECT line said `:443`,
the proxy dials the request line's port rather than the pinned target's, so it dialled
`127.0.0.1:443`, got connection-refused at once, and never reached the hanging sentinel. It was found
only because the v0.9.5 merge needed a negative control for the new dial paths (budget set back to
30 s: all five connect tests must fail, and now do). A test that cannot fail is the same family as
a control that shares the cause.

**A measurement that returns zero is a finding about the instrument first.** Re-checking the v0.9.5
table claim tree-against-tree, a script read `ScrapingResult.tables` and reported "0 of 74 captures
have tables, 0 differ", which looked like confirmation. Tables live at `result.media.tables`; read
there it is 13 of 74, and 0 differ. Both readings say "no change"; only one of them measured anything.

**A positive result is a finding about the patch first, too.** The first #2416 comparison (2026-11-04)
reported 22 of 74 pages changed and 4 phones lost. The patch had replaced every `remove()` with
`drop_tree()`, including the two sites (empty-element removal; `<script>`) that already move `.tail`
by hand, so it *duplicated* text ("YYli 100"), and the diff read the duplicate as recovered loss.
Fixed, it is 0 of 74. Keep a synthetic positive control in any comparison like this, and read one
changed page by eye before believing a count.

**Diff the line, not the version.** On 2026-11-04 Redis aborted on every `-se` start (the
environment has no IPv6 loopback). We first concluded the v0.9.5 merge wouldn't fix it, because both
images ran Redis 8.10.x (the Dockerfile's 7.2.7 pin is ineffective). Upstream `fadc53f` had changed
the bind from `::1` to `-::1`, optional, and Redis started on the first v0.9.5 replica. The
version was the wrong variable; the config line was the right one.

---

## Upstream merge watchlist

**v0.9.5 was merged on 2026-11-03** (`838869b`; branch `upgrade-upstream-v0.9.5`). Every entry above
that carried `[revisit after upstream merge]` now says what the merge did (`[merged v0.9.5]`) or what
`develop` still brings (`[revisit at next sync]`). The decisions and evidence are in
`tasks/upgrade-upstream-v0.9.5.md`.

**Deliberately kept as before, each pinned by a test:**

| Upstream change | What it would have done to MAS | Kept by | Pinned by |
|---|---|---|---|
| `f0ada4c` drops `--ignore-certificate-errors` | Broken-cert sites → `origin_unreachable` at 200 | `aitosoft_trust`: `egress_broker.ALLOW_INSECURE_TLS = True`; `ignore_https_errors: true` in `config.yml` | `test_a_broken_certificate_still_renders` + its control |
| `a59f50e`/`61eb573` `_max_timeout_ms()` | `page_timeout` 90 s → 60 s | `CRAWL4AI_MAX_TIMEOUT_MS` via `setdefault` | `test_mas_contract.py` |
| `b536bf5` (#2139) conditional consent wait | Capture 0.5 s earlier; paints in the gap come back blank | One line kept unconditional | `test_the_capture_point_includes_the_consent_wait` |
| `890af3d` `_dial()` at 30 s | Dead host costs twice the render slot | Budget threaded through | `test_every_dial_path_honours_the_connect_budget` |
| `15f4b29` recycle default 200 | Recycling on; #2419 deadlock | `max_pages_before_recycle: 0` | `test_browser_recycling_stays_off_by_default` (`test_mas_contract.py`) |
| `6b5a0d4` path alone (#2416) | Text after a balanced `<noscript>` lost | `strip_noscript` kept | `test_text_after_a_balanced_noscript_survives` |

**Changed, and MAS is told** (`tmp/mas-repo-messages/55-to-mas-…`): failed results carry keyed
`links`/`media`; 36 of 74 stored pages gain whitespace (+2 to +32 chars); `fit_html` keeps
nested-noscript content; `Connection: close` on plain-http origin requests; `/health` says 0.9.5.

**Still on `develop` after v0.9.5, for the next sync:** `3f9f790` (dead-browser replacement; the
silent-janitor trap), `a1bd6c8` (chromium channel; `pdf-inline` goes red for a true reason),
`a4c4b2d`/`b0ed23c` (`clone()` fields), `a8062ab`/`b36eda2` (#2417, the content filter keeps inline
text inside kept sentences; it touches `fit_markdown`, which MAS doesn't read, so low risk, but check
with the `raw://` A/B). Open upstream work that changes what we carry: PR #2428,
PR #2432, #2416.

**Google Chrome is a second upstream, and every image build takes its current stable silently.**
The Dockerfile installs whatever Chrome is current on build day. The v0.9.5 deploy moved production
from Chrome 151 to 157 (2026-11-04 09:12Z), and Chrome 154+ turns on HTTPS-First balanced mode by
default. For a public site whose HTTPS fails, headless Chrome then refuses the http load with
**`net::ERR_BLOCKED_BY_CLIENT`** (0.2–0.6 s, no request leaves the browser). `classify_error_text`
logs that as "unclassified net error, treated as ours" and returns `render_error` → 500, so MAS
retries it three more times. http://steel-air.fi failed 4/4 in MAS's first window after the
deploy. MAS's archive puts it at 35 of 28,636 companies http-only and 150 with at least one http
page. Fixed by a last `--disable-features=…,HttpsFirstBalancedModeAutoEnable` in `config.yml`,
live from 2026-11-04 14:24Z (`0.9.5-https-first`, AITOSOFT_CHANGES).

Three traps from this:
- **Chrome honours only the last `--disable-features` switch.** Measured: with the fix first and
  another switch after it, the page is still blocked. Playwright's own list (which disables
  `HttpsUpgrades`, and since microsoft/playwright#43871 also this feature) is overridden by
  crawl4ai's `MediaRouter,DialMediaRouteProvider` switch, so upgrading Playwright would not have
  fixed it.
- **Chromium's adoption guide spells the feature `…AutoEnabled`; the working name is
  `HttpsFirstBalancedModeAutoEnable`.**
- **Our browser suite can't see it on loopback**, because Chrome exempts localhost and private
  addresses. `test_an_http_only_public_site_renders` maps a public-looking name onto the fixture
  with `--host-resolver-rules`. That flag is one `enforce_egress` strips, so the test relaxes the
  list for its own block only. Its control is red without the switch, on real Chrome only.

**`HttpsUpgrades` is the same family and older than Chrome 157:** an `http://` URL is upgraded,
and Chrome falls back only if https *fails*. A hosting company's https placeholder ("HTTPS Not
Available", 200) doesn't fail, so an http-only site came back as the placeholder
(jr-sahkopalvelu.fi, MAS's window 3). It has been disabled in the same switch since
`0.9.5-http-as-asked`. `test_an_http_url_is_fetched_over_http_even_when_https_answers` pins it,
with a control. On the devcontainer's Chromium the upgrade never happens, so the control runs only
on real Chrome.

**If a rebuild changes Chrome's major version, treat it as an upstream merge.** Run the browser
suite inside the built image, and watch `render_error` with `ERR_` codes in the first window.

**Not a regression if `origin_unreachable` moves after the deploy:** TLS tolerance is kept, so it
should not. If it jumps anyway, check that `aitosoft_trust` still sets `ALLOW_INSECURE_TLS` before
anything else; the fixture tests pin it, but they run on headless Chromium, not production's Chrome.

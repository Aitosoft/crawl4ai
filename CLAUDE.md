# CLAUDE.md

All documentation in this repo is written by Claude for Claude. Optimize for
efficiency and readability in future sessions, not human formatting conventions.
This file auto-loads into context — keep it high-signal. Detailed reference
lives in other files; read those when needed.

## Mission

**Your Role:** Primary AI developer for Aitosoft's internal web scraping service
**Upstream:** Fork of github.com/unclecode/crawl4ai
**Users:** Only Aitosoft AI agents (internal tool, no human users)

---

## Task Tracking

Work is tracked in `tasks/` as markdown files. Completed tasks move to `tasks/done/`.
**Start each session by reading `tasks/README.md`** — the ordered index of open work,
with the gate on each, plus the cross-repo sequence and what each step is conditional
on. Ordering lives only there; the task files carry the reasoning.

**A task file is written to a peer with a clean context — usually you — who will
re-derive the diagnosis, orchestrate the change and dispatch a review.** So it needs
status and size, the evidence with enough detail to re-run the measurements, where
every fact came from, the design space with the reasoning, **the options the author
talked themselves out of and why**, and an honest "what I am least sure of". What it
does *not* need is an ordered checklist: a rigid step list narrows the implementing
session's intelligence, and that session re-deriving things freely is exactly the
mechanism that has caught nine consecutive task files being wrong about something
load-bearing. `tasks/done/consent-scripts-delete-the-page.md` is the current model.

---

## Development Commands

```bash
# Setup
pip install -e .                    # Install in editable mode
crawl4ai-setup                      # Setup browsers (Playwright + Patchright)
crawl4ai-doctor                     # Verify installation

# Server (port 11235)
uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235
curl http://localhost:11235/health

# Code quality
pre-commit run --all-files          # All hooks (black, ruff, mypy)

# Testing (run from repo root — relative artifact paths; see TESTING.md)
pytest test-aitosoft/            # ALL offline suites, 312 tests, ~260 s — no server, no customer site
pytest test-aitosoft/ --ignore=test-aitosoft/test_fixture_origin.py  # pure-function subset, 245 tests, ~30 s
pytest test-aitosoft/test_fixture_origin.py   # browser-driven, local fixture origin, 67 tests, ~215 s
python test-aitosoft/test_regression.py --tier 1 --version <label>  # Tier 1 regression (live server)
python test-aitosoft/test_site.py <domain> --page <path>            # Single site (live server)
python test-aitosoft/test_fingerprint.py --label <label>            # Stealth diagnostic (live server)
```

---

## Architecture

### Core Classes
- **AsyncWebCrawler** — main entry point
- **BrowserConfig** — browser settings (headless, proxy, UA, stealth, channel)
- **CrawlerRunConfig** — per-crawl settings (cache, locale, timezone, extraction)
- **CrawlResult** — `markdown.raw_markdown`, `markdown.fit_markdown`, `links`, `extracted_content`

### Pipeline
```
URL → Browser (Playwright/Patchright) → HTML → Scraping → Markdown → Filtering → Extraction
```

### Key Modules
| Module | Purpose |
|--------|---------|
| `crawl4ai/async_webcrawler.py` | Main crawler class |
| `crawl4ai/async_configs.py` | BrowserConfig, CrawlerRunConfig |
| `crawl4ai/browser_manager.py` | Playwright launch, context/page management |
| `crawl4ai/browser_adapter.py` | PlaywrightAdapter, StealthAdapter, UndetectedAdapter |
| `crawl4ai/antibot_detector.py` | Block detection (Cloudflare, Akamai, etc.) |
| `deploy/docker/server.py` | FastAPI server entry point |
| `deploy/docker/api.py` | API endpoint handlers |
| `deploy/docker/crawler_pool.py` | Browser pool (PERMANENT + hot/cold tiers) |

### Stealth + Anti-Bot (added 2026-04-11)
- **First tier:** Real Chrome (`chrome_channel: chrome`) + playwright-stealth
  (`enable_stealth: true`) patches navigator.webdriver, WebGL, chrome.runtime, etc.
- **Second tier:** Patchright fallback (`aitosoft_patchright_fallback.py`) — when
  antibot_detector marks a result as blocked, retry once through undetected-chromium.
- **Config defaults:** `aitosoft_entry.py` calls `BrowserConfig.set_defaults(**config.yml)`
  at import time so stealth/UA/viewport apply to every request even when the
  client sends no `browser_config`. Without this, config.yml would only affect
  the PERMANENT pool browser.

### Per-Request Customization (for MAS)
Contract: **one URL per request** — server-enforced, `len(urls) > 1` → 400
(MAS ack 2026-07-17, see AITOSOFT_CHANGES.md contract addendum).
MAS sends per-company browser identity via the API:
```json
{
  "browser_config": {"user_agent": "...", "viewport_width": 1920, "headers": {...}},
  "crawler_config": {"locale": "fi-FI", "timezone_id": "Europe/Helsinki", "max_retries": 1}
}
```
`browser_config` fields override config.yml defaults. `locale`, `timezone_id`, `geolocation`
are on CrawlerRunConfig (forwarded to Playwright `new_context()`).

**`max_retries` is theirs and it is 1** — measured 2026-08-05, all 213
`Anti-bot retry` lines in 14 days read `1/1`. This file said 2 for weeks and every
cost figure derived from it was 1.5× too high. It is a straight multiplier on
what a dead or blocked host costs a render slot, so re-check it (one Log
Analytics query on `Anti-bot retry`) before quoting any per-host cost.
**We cannot set it server-side this way:** `api.py:861-881` only fills `base_config` keys
whose value is `None` or `""`, and `max_retries` defaults to `0`.

---

## Testing

### Tier 1 (always test before deploy)
- **caverna.fi** — clean baseline restaurant site
- **accountor.com/fi/finland** — cookie wall (Cookiebot), use `remove_consent_popups: true`
- **solwers.com** — public company, contacts extraction
- **jpond.fi** — software consulting, email obfuscation `(at)`

**Quality gate:** All 4 must pass. Run `test_regression.py --tier 1 --version <label>`.

**CRITICAL: Test site safety rules:**
- **Live traffic is the last instrument, not the first.** A new failure class
  gets a route in `test-aitosoft/fixture_origin.py` (a local origin driven
  through the real production path — delay, size, status and markup shape are
  all arguments). A live request is justified only when the question is about a
  specific third party's behaviour and cannot be answered any other way — then
  it is one request, recorded in `TEST_SITES_REGISTRY.md`, host added to the
  burned list the same session. See TESTING.md golden rule 0.
- NEVER hit the same site more than 1-2 times per session
- Rotate across different sites
- Past over-scraping caused permanent Cloudflare blocks (talgraf.fi lesson)

### Key Findings
| Finding | Detail |
|---------|--------|
| **Accountor was never a cookie wall — it was our own `remove_overlay_elements` flag, and this row said otherwise for six months** | The January 2026 symptom (31 tokens, 99,649 B `html` → 230 B `cleaned_html`) was blamed on Cookiebot. The stored captures say otherwise: the surviving 7,805 B body carries `style="margin-right: 0px; padding-right: 0px; overflow: auto;"` — **the exact triple `remove_overlay_elements.js:150-153` writes, and nothing else in the codebase writes it** — with **zero content elements** left. A cookie wall overlays a page; it does not delete every `<div>`. What unblocked the site on 2026-01-24 was turning `magic` and `remove_overlay_elements` **off**; `remove_consent_popups` **did not exist yet** (upstream shipped it 2026-02-11, `3fc7730`). Today no `CybotCookiebotDialog` **element** appears in any successful accountor capture, `evästeet` appears 0 times in its markdown, and the pre-deploy readout recorded **zero generic matches** on it. So "the flag solves accountor" is an attribution nothing in this repo supports — **one request with `remove_consent_popups: false` would settle it** (Tier 1 host, not burned) |
| Why that mattered for six months, and the harness is the reason | **All five January presets set `remove_overlay_elements: True`, including `minimal` — the control.** No arm in the harness could ever reveal the flag as the cause, so a workaround got recorded as a diagnosis. The *mechanism* (`getComputedStyle().backgroundColor` is the string `rgba(0, 0, 0, 0)` by default ⇒ `.includes("rgba")` always true ⇒ "remove every visible fixed-or-absolute element") was only found **2026-08-06, 6.5 months later**. Same family as `/block/padded-403` and the 280×160 overlay fixture: **a control that shares the suspected cause is not a control** |
| `remove_consent_popups: true` is upstream's, and MAS sends it on every request | Upstream `3fc7730` (2026-02-11, first in v0.8.5) owns the flag and all **140** container selectors (**120 named + 20 generic** — `AITOSOFT_CHANGES.md:463` still says 122, contradicting `:438`). Our diff is guards and counters only, no selector added or removed. It **used to delete customer pages** — fixed 2026-08-06, read the next rows before touching that snippet. Measured value on real traffic: MAS found **95 matched containers, 0 containing any contact data**, and `accountor.com` produced **zero** generic matches |
| **Our own consent JS deleted the page, and two of the four ways were silent** | `remove_consent_popups.js` Phase 3 ended with **20** generic selectors — 18 substring patterns (`[class*="cookie-consent" i]`, …) plus `.cc-banner` and `.cc-window` — and called `el.remove()` with no guard on what matched. Enfold puts `av-cookies-no-cookie-consent` on `<html>` **to mean consent is switched off**, so we deleted the document. Four shapes: `<html>` → 15 B → 500; `<body>` → head-only → 500; **an inner element holding content → 200, `success: true`, `failure_class: "none"`, 99.5 % of the markdown, contacts gone**; **a Phase-1 click that navigates → the wrong page in full, at 200**. Both JS files were byte-identical to upstream. Fixed 2026-08-06: structural guard + the generic selectors observe instead of removing. The click channel is **detected and logged, not fixed** (ceiling 0.046 % of companies). `tasks/done/consent-scripts-delete-the-page.md` |
| `pagechars` is rendered visible text, not markdown length | `document.body.innerText` at the consent pass — no link URLs, no hidden or collapsed content. `kubler.fi` reads `pagechars=2634` against **55,545** markdown chars, and 48,673 of those are `[text](url)` constructs. Never compare the two units; it is the same trap the collapse guard's docs already warn about (visible-text in vs markdown out) |
| Read `node` and `class` in a `CONSENT DECLINED` line before you read the ratio | Measured 2026-08-06 through the real server: a wrapper that also held the contacts is **9.4 %** of its page and a genuine cookie bar is **7.3 %** — the ratio does not separate them. Absolute `chars` does (1,168 vs 92), and `node` does better still: a `<footer>`/`<section>`/`<main>` match is a page region, a `<div class="cookie-notice-bar">` is a banner. The counter's job is to **size the population**, not to classify each hit; only the *content* of the removed element decides whether a removal was loss |
| **Segment 2 settled the consent question, and the loud channel was the whole of it** | 2026-08-06, 50 companies / 61 domains / 261 renders / 274 requests, read end to end (`tasks/done/segment-2-counter-readout.md`). **27 `CONSENT DECLINED` on 3 companies of 50 (6 %), 27 of 209 stored pages (12.9 %) — every one `node=html structural=True`**, i.e. pages that were 15-byte captures at HTTP 500 on the previous image. `structural=False` (the silent inner channel): **0**. `CONSENT STRUCTURAL` (a *named* selector hitting a root): **0**, so the 120-name census holds. Genuine click-navigations: **0** (3 `CONSENT NAVIGATION` lines, all `www.se.com`, all **fragment-only** `#products` false positives — strip the fragment before comparing). This row replaced a weaker Tier-1 "zero on four sites" claim, which segment 2 superseded and whose framing was wrong: the generic selectors **did** match 115 elements here — they just did no *useful* work |
| The selectors' harm is the root collision, and their banner value is **zero** — measured from the far side | Our counter can say we declined a removal; it can never say *what was inside the thing we did not remove*. MAS can, because the fix lets those elements survive into storage: **95 matched containers, 0 containing any contact data across 34,533 characters**, checked with several deliberately wider nets (any `@`, any 3+ digit run, Finnish/English address prose, Finnish numerals) against a control that stayed flat while the signal went 0 % → 12.9 %. Both sides independently count **27 roots on 3 companies**. **So do not argue the upstream PR on "this destroys banner data" — argue the root collision**, which needs neither repo's corpus |
| The counter had to survive the fix, and nearly did not | The task file said "drop the 18 generic selectors" — there are **20**, and the count is not the point. Dropping them would have thrown away the measurement the whole cross-repo plan branches on — a deleted selector cannot decline anything, and **neither archive can size this retrospectively** because the element is removed before either side's capture. They are kept and *evaluated*, removal-free: `CONSENT DECLINED` logs `chars`/`pagechars`, which is what separates "a banner we correctly removed" from "a wrapper that also held the contacts". Same reasoning as the `COLLAPSE RECOVERED` / `RENDER DEFECT` split |
| A 15-byte capture is `<!DOCTYPE html>`, and it is diagnostic | Playwright's `content()` serializes the doctype alone when `documentElement` is gone. An empty 200 gives **39 B**, a body that *is* `<!DOCTYPE html>` gives **54 B** — so 15 means a script deleted the root, never an empty origin. lxml then raises `Document is empty`, which is where our `Crawl4AI Error: This page is not fully supported` placeholder comes from. Every `Near-empty content` event in 30 days was exactly 15 B. **The classifier keys on the shape, not the count** — a padded `<head>` puts the same defect at 20,087 B |
| A guard cannot see a loss that happened **before** the capture | The collapse guard exits at line 1 for total loss (`if not success`) and at `produced ≥ 500` for partial loss — and could never fire on partial loss anyway, because the deletion precedes capture so visible-in and markdown-out shrink together. **Neither repo's archive can size this either**, for the same reason: the matching element is gone before anything is stored, so "we grepped and found zero" is the only possible result. Count at the point of removal, not at the outcome |
| A capture with no `<body>` is permanent, an empty one is not | Chromium synthesises `<body>` for every document it parses, so its absence means a script removed it and no retry rebuilds it → `render_defect`, HTTP 200, terminal. A near-empty but structurally intact shell stays `render_error` at 500 — it might paint next time. Collapsing the two re-opens the `norex.com` inversion from the other side. The old 500 cost **16 navigations** per URL under MAS's retries × our patchright tier; Kübler paid it twice in segment 1 (32 navigations, 266 s, 26 % of the run) |
| `getComputedStyle(el).backgroundColor` is `rgba(0,0,0,0)` by default | So `remove_overlay_elements.js`'s `backgroundColor.includes("rgba")` was **always true**, its size-and-appearance clause a no-op, and the rule degenerated to "remove every visible fixed-or-absolute element". Measured: it deleted an absolutely-positioned hero containing the contacts at `success: true`. Now tests the real alpha (`0 < a < 1`, a translucent scrim). MAS sends `false`; **still do not recommend this flag** — the fix removes one degenerate clause, not the rule's appetite |
| A counter on the rich console is not a counter | `AsyncLogger` (crawl4ai's own, `self.logger`) fails three ways at once: it prints only `if self.verbose or force_verbose` and **`verbose` is client-settable** through `BrowserConfig`; it **wraps at the console width**, so a 190-char line becomes *two* Log Analytics records and a query on two fields loses rows; and it **eats `[`** — `_log` escapes the template but inserts values raw, and `[[` is not a rich escape, so `[class*="cookie-notice" i]` renders as the empty string. Use `logging.getLogger(__name__)`, which is what `COLLAPSE RECOVERED` / `RENDER DEFECT` / `RESULT FAILURE` already do. All three measured 2026-08-06, none guessed |
| A fixture can pass for the wrong reason when two fixes overlap | With the generic selectors gone, the Enfold class matches nothing, so every `<html>`/`<body>` consent fixture stays green **with the structural guard reverted**. `/consent/named-root` (`<body id="cookie-notice">`, one of the *120 named* selectors) is the shape only the guard can pass. Likewise the overlay fixture had to be 280×160: a full-width hero is removed by that script's legitimate *size* rule and would prove nothing about the `rgba` fix |
| Raw markdown > fit_markdown for contact extraction | PruningContentFilter removes contacts at threshold >= 0.35 |
| Use `optimal` config by default | domcontentloaded + remove_consent_popups (2-4s). That flag was a data-loss channel until 2026-08-06 — read the rows above before touching the snippet, and treat `CONSENT DECLINED` counts as the live measure of what it still costs |
| Blocked sites are IP-based, not fingerprint-based | Confirmed: two different browser engines get identical blocks |
| Block detection must use `redirected_status_code` | `status_code` is the FIRST redirect hop; the body is the LAST. Judging the 301 let every redirect-to-block page through as success (2026-07-30) |
| **`response_headers` is the first hop too — and there is no final-hop equivalent** | Same trap, one field over, and worth knowing *before* someone writes content-type logic. `async_crawler_strategy.py:876-886` walks `req.redirected_from` back to the earliest response and assigns both `status_code` and `response_headers` from it (its own comment says `# keep earliest`). `models.py` has `redirected_status_code` but **no `redirected_response_headers`** — so unlike the status, there is no correct field to switch to. Any `Content-Type` check therefore silently no-ops through `http→https` and `apex→www`, and MAS's agent constructs apex URLs it never saw. Found 2026-08-09 while pricing a PDF fix that was then abandoned; recorded because the next content-type idea will hit it |
| `page.content()` / `page.evaluate()` have NO timeout | Sent to the driver with no timeout field ⇒ no timer armed; they wait on the frame's execution-context promise, which a navigation replaces forever. `page_timeout` does not cover them. Bounded in `browser_adapter.bounded_evaluate` + `_capture_html` |
| Origin failures must never be our 5xx | Fixed 2026-07-30: `failure_class` on every result; origin-caused ⇒ HTTP 200 + `success:false`; 5xx reserved for us. `deploy/docker/aitosoft_failure_class.py`, MAS Q2 answer (a) |
| A nested `<noscript>` deletes the whole page | `<noscript>` can't nest ⇒ outer element never closes ⇒ libxml2 swallows the rest. 312 KB → 97 B `cleaned_html` → 1 B markdown, at HTTP 200 `success:true`. 406 pages / 70 hosts. Fixed by `strip_noscript()` pre-parse |
| An **unclosed** `<noscript>` still does, and the offline suite can't see it | libxml2 auto-closes it, so `test_noscript_body_collapse.py` reports that shape fixed. Chromium instead enters raw-text mode and serializes the rest of the document — `</body></html>` included — *inside* the element, so `strip_noscript()` correctly removes the element and takes the page with it. Only visible with a browser in the loop; found by `fixture_origin` 2026-07-31 |
| **Four** markup shapes swallow the body, not one | Enumerated through the browser at 73 KB, 2026-08-01: `unclosed-noscript`, `unclosed-script`, `deep-nesting` (libxml2 depth limit), `unterminated-comment`. Three distinct mechanisms, all deterministic. `deep-nesting` is **harmless at 1.5 KB and fatal at 73 KB** — enumerate padded or you will miss root causes, not just mis-size thresholds. Root cause still open (`tasks/cleaned-html-collapse-guard.md` part 2) |
| **A field nobody reads cost a customer outright, and the only instrument that saw it was the billing surface** | Upstream gives every `<img>` a `desc` by walking **up** the DOM until an ancestor has enough words, then returning that ancestor's **entire subtree text**. Image containers have no words, so on a catalogue grid the walk passes all of them and stops at whatever container also holds the page prose — and `add_variant` copies the result into every srcset variant. `www.thermokon.fi`: **1,104 of 1,160 entries carrying the same 154,798-char string, `media` = 231,708,619 bytes, 56× the entire rest of the result**, four times, at HTTP 200 `success: true`, **with no log line of any kind**. MAS's 210 s per-attempt timeout meant it could never succeed; the company is lost deterministically. Capped at 200 chars 2026-08-09 (`MEDIA_DESCRIPTION_MAX_CHARS`): 538,747 B, **430×**, `cleaned_html` and markdown byte-identical, all 1,160 entries kept. The cap sits in the shared walker, so it also truncates the `<video>`/`<audio>` `description` — verified inert, `MediaItem` has no such field and pydantic drops it. Three lessons, and the third is the one to carry: **payload size is a failure mode and nothing in either repo measures it** (`ContainerAppHTTPLogs.BytesSent` is the only surface, and nothing read it until 2026-08-09); **a field with zero consumers still costs**, which is why "nothing reads it" was the *safety* argument and never a reason to ignore it; and **the same document yields `desc: None` minified and the whole page pretty-printed**, because the stop condition ANDs `.text` (indentation whitespace is truthy) with `text_content()` (the whole subtree) |
| The cap bounds `desc`, **not a media entry** — and one of the two remaining amplifiers is worse than the one we fixed | `alt` is copied into every variant by the same `add_variant` (measured: one `<img>` with a 50,000-char `alt` and 5 srcset entries → 300,879 B of media from a 50,244 B document) — that one *is* linear in the document. **`media.tables` is not.** `table_extraction` defaults to a real `DefaultTableExtraction`, so it runs on every request, and `table_extraction.py` does `row_data.extend([text] * colspan)` with `colspan = int(cell.get("colspan", 1))` — **an unvalidated integer straight from the page**. Measured: `<th colspan="50000">` on a **4,624-byte** page → **4,504,226 bytes** of `media`; `colspan="2000000"` leaves the wire unchanged (rows truncate at `max_columns`) but costs **+91 MB RSS from 905 bytes of HTML in 0.12 s**, an excursion no instrument would attribute to anything; `colspan="auto"` makes `int()` raise and the table is silently dropped at `success: true`. **Not built, deliberately** — it needs pathological markup, no production instance has ever been seen, and the `desc` bug fired on ordinary catalogue HTML. But it is the reason the response-size backstop is *parked*, not *unnecessary*: `limits.max_body_bytes` is the **request**, and nothing anywhere bounds a response |
| A consumer's "no issues" is not evidence of no data loss | MAS called the 2026-08-01 run clean. **9 of its 328 pages, on 7 of 38 hosts, came back with 0 characters of markdown** from 725–40,165 chars of visible text. The failure is invisible from their side *by construction* — a page with no contacts looks exactly like a page that has none. Record what we measured, never what we were told |
| A detected collapse can often be **recovered**, not just reported | `html2text` over the same rendered HTML returns the full body for `unclosed-noscript` (1,265 chars — *identical* to the healthy control) and `deep-nesting`, and nothing for `unterminated-comment` / `unclosed-script`. It is the converter `aitosoft_static_mode` already ships, so recovery costs **no** new divergence from upstream's parser — one fallback beats three pre-parse repairs (2026-08-02, shipped) |
| Reuse the **converter**, not the pipeline around it | "We already ship html2text" was true of `HTML2Text` and false of `aitosoft_static_mode._fetch_static_one`, which runs `_strip_hidden_decoys()` first — and that `decompose()`s every `noscript`, so on an unclosed one it deletes the whole document Chromium re-serialized inside it. **1,265 chars → 0.** The same failure as `strip_noscript()`, by a different route |
| A fix for silent loss can open a **new** silent-loss channel | Recovery accepted on MAS's 500-char degenerate floor alone lets a 599-char rescue of a 41,408-char page out as `success: true` — green, used, 40,809 chars gone. The symmetry argument ("treat a recovery as the normal path would") is wrong: on the normal path we have no evidence of loss; here **the guard has already proved it**. Recovery must clear the ratio floor too (measured headroom 10–28×) |
| `arun` does not raise — it returns a failed result | A task file built a five-step chain on `classify_exception`; upstream wraps its whole body in `try:` and returns `CrawlResult(success=False, …)`, so `classify_result` decides. The log-line *prefix* is the tell: `Crawl request failed:` is built only in `server._crawl_response` (the result path); the exception path emits JSON. Also: upstream retries on **any** exception, not just blocks, so one request is `1 + max_retries` navigations — **two** at MAS's actual 1, not the three this row claimed for weeks |
| A dead host costs 30 s of a render slot per leg | Measured through a local blackhole: **Chromium's** 30 s proxy-connect timeout binds, not our `egress_proxy.py` 30 s (which never fires — its timer arms later). But ours *pre-empts* it exactly and linearly (12 s → 12.02 s), so our constant is still the lever. Without the pinning proxy at all it is **134 s**, so the proxy is accidentally what caps this today. **Lowered to 15 s 2026-08-05** — not 10 s, because the residual risk is an origin whose handshake would have completed between our timer and Chromium's 30 s: it becomes `origin_unreachable` at 200, i.e. a silently dropped page. `tasks/done/egress-proxy-blocks-the-event-loop.md` |
| `resolve_and_pin` blocked the single event loop — **fixed 2026-08-05**, and the file naming it was wrong about where | The task file said three changes in `egress_proxy.py`, "a file we own outright". Both are false: the file is **byte-identical to upstream** (`60886d1`, with 37 upstream tests behind a live CI gate), and the dominant call site is the **seed check in `api.py`**, which runs on every `/crawl` *before* render admission — so the proxy never even sees a CONNECT for a dead nameserver. Fix the surface, not the file you happened to read |
| Measure the resolver in the **environment that runs**, not the one you are typing in | ACA injects `options ndots:5` + four search domains. Against a nameserver that never answers that is **22.75 s** per `getaddrinfo` (8 UDP queries) vs 12.74 s in this devcontainer. The task file's "~5 s or ~20 s" band guessed the wrong machine. `az containerapp exec … cat /etc/resolv.conf` settles it in one call |
| `asyncio.to_thread` **relocates** a blocking call; it does not bound it | The default executor is 8 threads on ACA (`os.cpu_count()` reports the *node*, not the cgroup, and 3.12 has no `os.process_cpu_count()`), its queue is unbounded and FIFO, and **cancelling the request does not reclaim the thread** — it parks for the full resolver timeout. So healthy resolves queue behind dead ones. `RES_OPTIONS="timeout:2 attempts:2 ndots:1"` in `supervisord.conf` is what bounds it, needs no root, and cuts happy-path DNS ~5× (10–40 uncached resolves per render). The two are complements, not alternatives |
| A dead domain was reported to MAS as an **SSRF refusal** | `egress_broker._resolve` mapped `socket.gaierror` onto the same `EgressBlocked` as a policy rejection → HTTP 400 `URL blocked (SSRF protection)`, no `failure_class`. Cheap (0.078 s, no render slot) so it was a *labelling* defect — but a company-registry sweep is mostly lapsed domains, and it is the `norex.com` inversion again. Now `origin_unreachable` at 200, fixed in `api.py` alone so the seven endpoints sharing `validate_url_destination` keep their correct 400 |
| If every test patches a function, that function's **own error paths are untested** | Shipped 2026-08-05: reverting a new exception class left its `raise` behind, so `egress_broker._resolve`'s `except socket.gaierror` branch raised **`NameError`**. It passed 229 offline + 54 browser + 316 upstream security tests and a green CI run, because every test monkeypatched `resolve_and_pin` or `validate_url_destination` — the layer *above* the broken line. Production returned `render_error` at **500** for any dead domain, which MAS retries 3×: worse than the 400 it replaced. Caught by one live probe against the deployed image, ~8 minutes after deploy. **Patch the layer below the one you are testing** — patching `socket.getaddrinfo` gives the same hermetic speed and executes the real branch |
| On plain `http://`, a proxy reply **is the page** | Answering a failed connect with `_BLOCKED` handed Chromium a renderable 403 whose body is our own `URL blocked`, which our own detector read as the customer blocking us: `origin_blocked` + a wasted patchright leg, 16.1 s. Closing without replying gives the honest `origin_http_error` in 0.5 s. A 502/504 does **not** work — an empty body trips our own inference tier and retries anyway. The `https://` CONNECT path was always fine: a non-200 to CONNECT becomes `ERR_TUNNEL_CONNECTION_FAILED` and is never rendered |
| `content_source="raw_html"` does **not** dissolve the collapse family | It prevents only `unclosed-noscript` and `deep-nesting` — the two recovery already fixes. `unclosed-script` and `unterminated-comment` are lost at the **tokenizer** (`CDATA_CONTENT_ELEMENTS`, comment discarding), which is HTML5 spec behaviour identical in libxml2 and `html.parser`, so **no parser choice rescues them**. Priced 2026-08-05, answer no |
| We have **no** outbound politeness, and a config key implies we do | `config.yml:106`'s `rate_limiter` is only consulted on the `arun_many` path (`async_dispatcher.py:285`), and `api.py:839` picks `arun` for one URL — which the single-URL contract guarantees. `rate_limiting:` at `config.yml:54` is *inbound* (1000/min per caller). Pacing across a sweep is entirely MAS's, from one shared SNAT address that is not contractually ours |
| **Count failures by `failure_class=`, never by the log token — and our own runbook told four sessions otherwise** | Two disjoint tokens carry the field on mutually exclusive paths: `RESULT FAILURE` (`api.py:1033`, the result loop) and `ORIGIN FAILURE` / `TERMINAL FAILURE` (`api.py:1180`, `except Exception`). **No request emits both.** Measured 2026-08-06: querying the token reported **9** `origin_unreachable` events when the truth was **21 on 13 companies** — a **57 % undercount** — because a dead domain is refused by `_normalize_and_validate_seeds` (`api.py:760`) *before* render admission, so it never becomes a result. Its marker is `DNS: host does not resolve` (`api.py:698`); it costs **no render slot and no browser** and returns **200**. **Free second instrument: ingress `/crawl` requests − `RenderGate ADMIT` lines = pre-admission refusals + 429s** (274 − 261 = 12 + 1, exact). Two holes remain: static-mode failed fetches log no `failure_class` at all, and `api.py:1198` omits `render_mode` so a static request to a dead domain reports as `"full"` |
| **We cannot count HTTP 404s at all, and MAS can — measured 13:1 against us** | `RESULT FAILURE` (`api.py:1034`) sits inside `elif not result.success`, so it fires **only for failed results**. A 404 that serves a normal styled "page not found" body *renders fine* ⇒ `success: true`, `failure_class: "none"`, **no log line anywhere** — while the envelope still carries `status_code: 404`. So `failure_class=origin_http_error` counts only 404s that *also* failed to render (empty or block-shaped bodies; the code comment "an ordinary 404 lands here" is true only via the inferred-block path). Segment 3: we reported **2**, MAS's envelope-side `>= 400` cross-check reported **26 on 26 distinct URLs**, and **theirs is the complete instrument**. Same family as the row below, one layer further out: a class that stops being a *failure* stops being counted. **`failure_class` answers "whose fault", `status_code` answers "what did the origin say" — never substitute one for the other** |
| A replica count is not a load measurement, and only one table can settle it | Segment 3 ran the whole 30-minute window at `maxReplicas` while **true concurrency was ~1.2 requests** (299 requests, p50 4.95 s). Concurrency is `sum(RequestDuration)/window`, which lives **only** in `ContainerAppHTTPLogs` — our own `RenderGate ADMIT` logs admission but never release, so the console logs cannot produce it. Also: `dcount` of replica names at 10-minute resolution reports churn as if it were concurrency (it said 30 where a 1-minute bin said 6); bin at 1 minute and cross-check with `az containerapp replica list`. Health-probe feedback was the leading root cause and is **refuted** — 0 `/health` requests traverse the ingress. `tasks/autoscaler-ratchets-to-the-cap.md` |
| Moving a class off 5xx deletes its only log line | Nothing logged a failed *result*'s `failure_class` — those URLs were visible only because they produced a 500, and `server.py` logs 500s. So the taxonomy's own success (fewer 5xx) was silently costing observability, and `unrenderable_content` was about to ship with no server-side counter. `RESULT FAILURE` now covers every failed result. **The tail of this row used to say `ORIGIN FAILURE` "describes a token that rarely fires" — that is false and it is what caused the 57 % undercount in the row above.** `arun` rarely raises, but the **pre-admission seed check does**, and it is the dominant producer of `origin_unreachable`. Read the two rows together |
| A download is nobody's fault and permanent — **except an inline PDF, and this row said otherwise for a week** | Chromium refuses to commit a navigation to a download: `Content-Disposition: attachment`, inline `text/vcard` and `application/octet-stream` all raise the byte-identical `Page.goto: Download is starting` → `unrenderable_content` at 200. (`origin_http_error` was rejected because upstream leaves `status_code` **null**, a lie in the field MAS was promised; `accept_downloads: true` does not rescue it.) **Inline `application/pdf` is the one exception.** Any Chromium carrying the PDF-viewer extension — production's real Chrome — *renders* it into a **174-byte shell** with no visible text and no `<embed>` (shadow DOM), which tier-3 structural inference calls "blocked" → `render_error` → **500, retried**. So `unrenderable_content` has fired **zero times in production, ever**, and PDFs are not in it. Measured on both arms 2026-08-09: 4 of 5 download kinds identical, `pdf-inline` alone diverges. The caveat was written when the class shipped (`tasks/done/download-navigation-is-not-a-render-error.md:27-30`) and every downstream reader dropped it |
| **PDF text extraction is a regression, not a limitation — and who caused it is NOT established** | MAS holds April captures with **11,101–45,118 characters** of extracted PDF text (annual reports, financial statements, product catalogues — exactly what a Finnish SME publishes that nothing else on their site contains). Today the same class returns a 174-byte viewer shell and a 500. **They attribute that to our browser change; that is their inference, not a provenance check, and this repo cannot reproduce it either way**: `pypdf` is not in the image (`INSTALL_TYPE=default`), there is no PDF branch in the crawl path, and neither browser arm yields PDF text. The only in-repo candidate is `render_mode: static`, which has no content-type gate and would emit `%PDF-1.4 1 0 obj …` or mojibake, not prose. **Nobody needs it today** — MAS is removing PDFs at dispatch — and nothing is being built. Recorded so a future user's request is not met as a novelty, and so "we regressed it" is not repeated as settled. One stored April row's `render_mode` + first 200 chars of markdown would settle it |
| **The browser suite has never run production's browser, and CI never runs it at all** | `browser_manager.py:1123-1128` is a *Windows* workaround applied on every platform: it drops `channel` whenever `chrome_channel == "chromium"`, so Playwright launches `chromium_headless_shell` — which has no PDF viewer. `fixture_origin.py:1232-1251` falls back to `"chromium"` when no `google-chrome` binary is on PATH, which on this arm64 devcontainer is always, and `CRAWL4AI_FIXTURE_CHANNEL=chromium` cannot rescue it because it produces the same string line 1127 discards. That is why five download tests pass while exercising the *download* arm and `pdf-inline` passes for the wrong reason. Worse than "a config nuisance": **no workflow in `.github/workflows/` runs `test-aitosoft/`** — only `deploy/docker/tests/test_security_*.py`. Same family as "a control that shares the suspected cause is not a control", one layer down: **a test that silently runs a different binary than production is not a test of production** |
| **`CrawlerRunConfig.set_defaults()` exists, and four sessions reasoned as though it did not** | `async_configs.py:1329` decorates it `@_with_defaults` — the same mechanism `aitosoft_entry.py:40` uses for `BrowserConfig`. Verified by execution 2026-08-09: a default applies through `CrawlerRunConfig.load(body, provenance=UNTRUSTED)`; an explicit client value wins, **including an explicit falsy one** (the decorator keys on presence in `kwargs`, not truthiness); `clone()` preserves it; and defaults are **deep-copied per instance** (`:69` and `:91` both `copy.deepcopy`), so a default *object* carries no cross-request state. It also **bypasses the untrusted boundary by design** — the filter inspects the request body, not class defaults — which is what makes it a server-side lever. **`api.py:876-880`'s `base_config` merge is one route, not the only one**, and it is the crippled one (fills only `None`/`""`, the `max_retries` trap). One hazard if anyone adds a *new* field: `clone()` round-trips through `to_dict()`, and seven `__init__` params are missing from it (`base_url`, `c4a_script`, `cache_validation_timeout`, `check_cache_freshness`, `fallback_fetch_function`, `force_viewport_screenshot`, `virtual_scroll_config`), so those silently revert to the class default on the patchright retry leg (`aitosoft_patchright_fallback.py:157`) |
| A collapse guard must compare **text to text**, never HTML bytes | `len(html)`→`len(cleaned_html)` fires on healthy pages: the healthy control padded to 73 KB of inline CSS gives the *same* 0.0036 ratio as the collapsed page, and `accountor.com`'s real cookie wall is 99,649→230. It is also blind to `unterminated-comment`, which keeps 74,523 B of `cleaned_html` **containing the content** and still yields no markdown. Shipped guard: visible-text chars in vs markdown chars out, 500-char floors, ratio 0.10 vs a healthy minimum of 1.311 |
| Every size gate in the detector was on `len(html)` | A vendor pads its block page to 80 KB, so `403 - Forbidden` in 48 characters of text passed as content at origin 202. Evidence gates now read **visible text**; inference gates (tier 3, near-empty-200) keep their byte bounds on purpose. `monidor.com` in our own artifacts is the same defect at 11.5 KB |
| Moving a gate is only half a fix — check that a pattern exists | The task file said "the four caught hosts prove the pattern side already works". **No pattern matched that body at all**; they were caught by the 403 status fallthrough. Measure which branch fired before believing a diagnosis about why |
| A block verdict must carry *why* | `is_blocked` returns True for "the origin said so" and for "we came back with nothing". Mapping both to `origin_blocked` reported our own `not fully supported` placeholder (`norex.com`) as the customer's site blocking us. Inference now → `render_error`; **discarding the reason must not discard the status** (403/503 still block, other 4xx → `origin_http_error`) |
| A low-text gate re-opens the Shopify false positive | ~15 of MAS's 22 `Access Denied` hits were storefronts with an `/pages/access-denied` menu link; our fixture for it has **247** visible chars, *under* any sane text gate. A notice counts only in a title/heading **or** at ≥50 % of the page's text |
| A fixture can be unfaithful on exactly the load-bearing axis | `/block/padded-403` served a bare `<div>` (0 content elements → 2 tier-3 signals). The real page has `<h1>`+`<p>` (2 elements → 1 signal). A fix validated on the fixture would have closed none of the four real hosts |
| The patchright retry re-fetched with the *same* capture wait | Different engine, identical budget — it could never resolve a challenge the first attempt outlasted. Now `retry_capture_wait_s: 10.0`; measured retry leg = `W + 1.22 s`, zero extra page loads. Never raise the global wait instead: 267 render-hours per sweep |
| A large part of the replica's memory is **not** the pool — but the split is **not settled** | The record said 8 browsers "is the whole 4 GiB"; 9 × 165 MB is ~36 %, so that arithmetic never closed and four sessions read past it. **That refutation stands.** The replacement — `mem% = 59.3 + 2.65 × browsers` (n=68, r²=0.22) — does **not** yet: the coordinator's re-check found three independent problems, all biasing browsers *down* (`tasks/replica-memory-baseline-unexplained.md` §"Why the fit is not settled"). Do not quote a per-browser %, an intercept, or "the cap would not have helped" until it is re-derived from stored data. `max_browsers: 6` ships anyway — it is correct under every candidate slope |
| Regress on a control loop and you measure the controller | The janitor *closed browsers when memory was high* (adaptive TTL, live in the probe data). So high-memory samples systematically carry fewer browsers, biasing any browsers→memory slope toward zero. Fitting an observational slope through a feedback loop estimates the loop, not the cost. Kill the loop, then measure — or use the offline instrument, which has no controller in it |
| A metric that changed is not a metric you can regress across the change | The 68 pool-stats lines predate `13fcecb` (2026-08-01), which made `get_container_memory_percent` subtract `inactive_file`. The intercept is therefore in **raw `memory.current`**, page cache included — and page cache is exactly what would sit in an unexplained baseline. Date the metric, not just the data |
| A pooled browser costs the *process*, not the *page* | `/ok` (1.5 KB, no images) +142.8 MB vs `/heavy` (236 KB, 17 images — the median of 62 stored captures) +170.0 MB. Only +19 %. Suspecting a fixture is too small is right; assuming that makes the figure badly wrong is not |
| Per-browser memory is a **ratchet**, and `about:blank` cannot unwind it | Navigating a retained page to `about:blank` returns 0.5 MB of anon **even when it holds a fully-committed 100 MB JS heap** — while the same run shows the heap going in at +100.5 MB, so the instrument is not blind. A browser's floor is the heaviest page it ever loaded; only closing it resets it. `pool-browser-retains-last-page.md` closed as refuted |
| A capped pool must **never wait** for a browser | `release_crawler` takes the same `LOCK`, so waiting inside `get_crawler` waits on code needing the lock the waiter holds: no 504, no 429, no janitor recovery. Evict or refuse (`RenderCapacityExceeded` → 429), and close evicted browsers in a detached bounded task — `close()` has no timeout and a wedged Chromium closed inline holds the pool lock forever |
| "We are full" had two wire statuses | RenderGate said 429; the pool's memory guard said 500, which MAS retries 3× — memory pressure quadrupled its own load. Both now 429 + `Retry-After`. Symptom only: nothing bounds live browsers (`tasks/pool-residency-unbounded.md`) |
| One `failure_class` must mean one wire status | `render_error` was 200 in static mode (never raises) and 500 in full mode — same class, opposite retry behaviour, decided by `render_mode`. Both modes now route through `server._crawl_response` → `http_status_for`. The missing axis was **permanence, not ownership**: `render_defect` is entirely ours *and* must not be retried (`NON_RETRYABLE_CLASSES`) |
| Tier-2 antibot patterns never see HTTP 200 | `is_blocked` only reaches tier 2 via the 4xx/5xx branches, but challenge interstitials are served with 200 — so `Checking your browser` had never fired. Fixed by the challenge tier (2026-07-30) |
| **The ACA scale trigger is not `render_capacity`, and pinning them was a category error** | `render_capacity` is a hard in-process cap on **concurrent renders** (the safety mechanism; RenderGate enforces it). ACA's `concurrentRequests` is only **when Azure adds a replica**, and Microsoft's own doc defines it as *"requests in the past 15 seconds divided by 15"* — a **rate**, while naming it concurrency. Two numbers in different units can never meaningfully be equal. The old "MUST match" comment made the trigger maximally twitchy. **Trigger is 6 since 2026-08-08** (ACA's own default is 10; we were at 2). Raising it cannot oversubscribe a replica. `deploy-image.sh` now checks live-vs-`ACA_SCALE_TRIGGER`, not live-vs-`render_capacity` — and it **hard-fails `exit 1` after the image is already updated**, so a scale-rule change made without editing that constant breaks the next deploy |
| **The scaler is not broken on smooth load — measured, and it killed our own headline** | The task file said the fleet "ratchets to the cap on a load that justifies one replica". A **controlled** run on 2026-08-08 (uniform `raw://` traffic at segment 3's exact arrival rate, 10.7 req/min, concurrency 0.9) produced **1 replica, zero scale-up events, in 12 minutes** — `ceil(0.9/2) = 1`, correct behaviour. MAS's segment 3, at the **same arrival rate** but bursty (peak in-flight 8, p99 36 s, max 52 s), reached **30**. So arrival rate is *not* the driver, and two independent model fits that said it was had both been fitted to observational runs where rate and burstiness co-varied. **The remaining candidates are concurrency bursts and connection count** — an ACA maintainer states publicly that the scaler *"takes into account active connections as well as requests"*, which appears in no documentation |
| A `raw://` URL is a full-fidelity load generator with zero egress | `utils.py:354` returns early for `raw:` before any DNS/SSRF check, and `async_crawler_strategy.py:488` still routes it through the browser whenever `needs_browser` — which `remove_consent_popups` (the flag MAS sends on every request) sets. So it exercises RenderGate, the pool, a real Chromium launch, the consent pass and the collapse guard. Render time is a dial: `delay_before_return_html` is on the untrusted allowlist, and wall time is linear at ~1.3 s overhead + the delay. **Reach for this before any live host** — it satisfies golden rule 0 outright and, unlike a third party, is byte-identical across A/B arms |
| ACA exposes no scale-down damping at all, so stop looking for it | `pollingInterval` and `cooldownPeriod` are real writable ARM fields (API ≥ `2024-08-02-preview`) and both are **no-ops here**: Microsoft documents polling as *"doesn't apply to HTTP and TCP scale rules"* and cooldown as governing only the final replica → 0. What actually damps scale-in is the **300 s scale-down stabilization window**, which has **no configuration surface anywhere** (`microsoft/azure-container-apps#1418`, open since 2025-02). Levers are `maxReplicas`, `minReplicas`, `concurrentRequests` — nothing else |
| The 429 window is cold start, where there is one replica whatever `maxReplicas` says | The ingress is **round-robin, decided per request, session affinity off** (`stickySessions: null`); Envoy picks the endpoint *then* the connection pool, so a keep-alive client does **not** pin to a replica. A big fleet therefore *dilutes* bursts rather than absorbing them — and dilution needs the replicas to already exist. MAS's own control says the same: three crossings of 5 concurrent in minute one produced their single 429, seven after KEDA had scaled produced none. **So the cost/429 trade the task file framed as central is largely illusory; the 429 lever is `minReplicas`, not the scale trigger** |
| Over-provisioning cost is €0 cash and 205× the free grant — both true, and only one matters | The subscription is **Sponsored** (`quotaId: Sponsored_2016-01-01`) and has emitted zero Azure usage records since 2026-06-03, so cash cost is **€0**. At list price segment 3 wasted **€2.98–3.16**, not the task file's €0.30 — **10× low, in the opposite direction it guessed**, because the estimate anchored on the 30-replica peak instead of integrating ramp + plateau + drain. Free grant gives no comfort: one run is **51 %** of the monthly grant and the projected 18,000-company sweep is **205×**. `minReplicas: 0` also makes the cheaper idle rate permanently unreachable |
| Per-replica render capacity is 2 (2 vCPU) | Benchmarked 2026-07-17; >2 concurrent renders degrade all requests. Enforced by RenderGate; the ACA scale rule is a separate trigger (row above) |
| **MAS's `--concurrency 2` bounds COMPANIES, not renders — our docs said otherwise and were wrong** | Measured by MAS 2026-08-06 across 3,541 runs and confirmed against our own 429: each company's agent fetches pages **in parallel**, up to 4 at once, and **74 % of companies issued ≥2 simultaneous fetches**. Peak **7 in flight**. Our claim that a 429 was impossible at concurrency 2 is false — one cold replica is 2 slots + 4 queue = **6**, and they can present 7. Their trace and our `2/2 rendering, 4 queued` reconcile exactly: 6 admitted + 1 rejected = 7 |
| The good consequence: **the in-flight ceiling does not grow with cohort size** | It is their flag × per-company fan-out (≈ 2 × 4 = 8). 50 companies or 15,000, at `--concurrency 2` the peak stays ~8. So **scaling the cohort buys duration, not concurrency** — and our fleet ceiling is `render_capacity: 2` × `maxReplicas: 45` = **90 concurrent** (it was 60 at `maxReplicas: 30`, raised 2026-08-08). **Their flag is free up to ~15**; above that the lever is `maxReplicas`, which is a *scale* setting (no token risk) and costs nothing at `minReplicas: 0`. **Verify Azure accepts a higher cap before quoting one** — the `--memory 8.0Gi` note never was a valid command |
| ~~A cold-start 429 is structural, ~one per segment~~ — **there are two 429 populations and this row described only the smaller one** | The cold-start half still holds: MAS crossed 5 concurrent **ten** times; the **three inside the first minute** produced the single 429, the **seven after KEDA had scaled** produced none — replica warmth was the only variable, and the lever is `minReplicas: 1`. **What the row missed is that RenderGate is not the only thing that emits a 429.** The overnight 2026-08-09/10 sweep returned **434**, of which RenderGate rejected **25** — the other ~409 were `crawler_pool`'s **memory guard**, at a true concurrency of **1.3** against ~26 render slots. **Never read a 429 as a capacity signal without splitting it**: `RenderGate REJECT` vs `refusing new browser` are different mechanisms with opposite fixes. `tasks/memory-guard-charges-reclaimable-page-cache.md` |
| **The memory guard refuses on cache it would never OOM on, and the reading is ~14 points too high** | `get_container_memory_percent` (`utils.py:457`, ours) subtracts `inactive_file` only — correct as a working-set definition, and its docstring sized that at *1 % warm / 16 % cold*. Under 15 h of sustained crawling the cache is **active**, not inactive: at 420 refusal events the guard read **88.7 %** while `anon` was **68.6 %**, with **583 MB of active file cache** charged in. **Only 4 of 420 refusals had `anon` itself ≥85 %.** Zero OOM kills, zero exit 137, ~1.25 GB of genuine headroom. Two things follow. **`max_browsers` is not the fix** — `config.yml:171-177` says so outright and the refusal log shows `resident=4/6`, under the cap, refused on percentage alone. And **p50/p95 memory are biased upward**: the janitor samples every 10 s above 80 % and 60 s below 60 %, oversampling high states ~6× (measured overstatement 5.3×). **`max` is unbiased and so is the refusal count; the percentiles are not** |

---

## Key Principles

1. **Minimal upstream changes** — keep modifications isolated, document in `AITOSOFT_CHANGES.md`
2. **Security first** — no secrets in code, use env vars (see Security section below)
3. **`[aitosoft]` commit prefix** — all our commits
4. **Test before deploy** — Tier 1 regression must pass
5. **Claude is the lead developer.** Tero (owner) does not review code or
   PRs — never block work on owner approval. Quality gates are tests and
   coordinator sign-off; outward-facing artifacts (upstream PRs, cross-repo
   contracts) are decided by the coordinator session. Tero sets direction,
   runs sessions, and relays MAS messages.
6. **Roles are separated across sessions, each with a clean context.** Whoever
   *writes* a plan does not *implement* it; whoever implements does not sign off
   on it; experiments, evals and review are their own sessions again. This is
   not process for its own sake — it is the quality gate that has actually
   worked here. **Four consecutive implementing sessions found the coordinator's
   task file materially wrong about something load-bearing**, each time because
   a fresh context re-derived the diagnosis instead of inheriting it (see the
   `tasks/README.md` intro for the running count). A session that plans and then
   implements cannot do that: it re-reads its own reasoning as evidence.

   Practically:
   - The coordinator writes task files, holds the big picture and the cross-repo
     state, and does not edit `crawl4ai/`, `deploy/` or `test-aitosoft/`.
   - The implementing session is expected — required — to **challenge the task
     file**, and to record what it found wrong in the file itself. A task file
     that survives implementation unamended is the unusual case, not the norm.
   - **Verify the diagnosis, not just the plan.** For a detector claim that means
     asserting *which branch fired*, not that some verdict came back.
   - Disagreement between two sessions is the signal, not a problem to smooth
     over. Write down which one measurement settled it.
7. **Reach for the cheapest lever before the cleverest one.** Our characteristic
   failure is not sloppiness — it is *elaboration*: a real defect gets found,
   the investigation is genuinely interesting, and three task files later nobody
   has asked whether a config change would have deleted the problem.

   The case that named this rule, **including how it went wrong**: an April note
   recorded that `--memory 8.0Gi` "doubles headroom at zero cost (MS credits)".
   It was never tried, and meanwhile three task files went into apportioning the
   4 GiB. The coordinator cited that as proof we over-complicate — then Azure
   **rejected the command**: 2 vCPU / 4 GiB is this environment's maximum and the
   note was never valid. So the rule earned itself twice. Reach for the cheap
   lever first — **and verify the cheap lever exists before building an argument
   on it.** One `az` call would have settled it in either direction.
   **Buying headroom, deleting a feature, raising a limit and doing nothing are
   all legitimate answers**, and they beat a correct implementation of the wrong
   question.

   Before an M-or-larger task: what would make this problem not exist?
8. **Run a second-opinion pass before committing to a plan, and again before
   calling it done.** A separate agent with a clean context, asked exactly three
   questions:
   - **What did we miss?**
   - **Is there a simpler solution?**
   - **Do we already have something we could use?**

   These are the questions that break work loops, and none of them can be asked
   honestly by the session that wrote the plan. Question 3 has paid out
   repeatedly: `monidor.com` — a live instance of a defect we were designing a
   synthetic fixture for — was sitting in `test-aitosoft/artifacts/` for weeks;
   `fixture_origin.py` now removes most reasons to touch a customer's site;
   upstream's `fallback_fetch_function` hook already existed. **Check the corpus
   and the code we already hold before building or before crawling.**
9. **When you write instructions, you are writing to yourself.** The next
   session has this same repo, the same tools and the same capabilities. It is a
   peer with a clean context, not a subordinate — and the clean context is the
   *point*, because it is what lets them catch what we missed.

   So: give principles, reasoning and evidence, and let them draw the
   conclusion. Do not write narrow, rigid rules — a rule without its reason
   cannot be re-derived, cannot be safely broken when the situation differs, and
   silently becomes wrong when the code moves under it. Say what you measured,
   what you assumed, and what you are unsure of. **Name the things you suspect
   are wrong in your own work**; that is the most useful paragraph in any task
   file we have written. Where a task file and this index disagree, the task
   file wins and the index is stale.

---

## Security

**PUBLIC REPOSITORY. NEVER COMMIT SECRETS.**

- Tokens go in `.env` (gitignored) or Azure Key Vault, never in code/docs
- Always use `os.getenv("CRAWL4AI_API_TOKEN")` in code
- If a token is leaked: rotate immediately via `az containerapp update --set-env-vars`, update `.env`, notify MAS team

**`PRIVATE.md` (gitignored) holds infrastructure identifiers** — Log Analytics
workspace ID, egress addresses, the dev container's home-ISP connection. Read it
when you need one; tracked files point at it rather than inlining it.

The line, so it does not get re-decided every session: **identifiers that let
someone act** go in `PRIVATE.md`; **facts and reasoning stay public**. Crawled
hostnames, measurements, failure classes, costs and architecture all stay in the
tracked files — scrubbing those would cost more in future sessions than the
exposure is worth. One deliberate exception: the production endpoint URL stays
tracked, because it is fail-closed behind the token and is live tooling config.

**Before every commit, this must return exit 1 (no output):**

```bash
git grep -InE '(crawl4ai-(test-)?|jwt-secret-)[0-9a-f]{32,}' -- .
```

Exit 0 = a real secret is staged. Stop, remove it, rotate the token.

Why this exact form (don't "simplify" it back):
- **`git grep`, not `grep -r`** — `grep` here is ugrep, which honors ignore-files and
  silently skips gitignored paths. A plain `grep -r` cannot distinguish "clean" from
  "never looked", so it gives false confidence. `git grep` scans tracked files, which
  is exactly the public-exposure surface — only tracked files reach GitHub.
- **`[0-9a-f]{32,}`, not `[a-z0-9]`** — real tokens are `crawl4ai-` + `openssl rand -hex`
  (48 hex chars in prod, 32 in older scripts). The loose
  pattern matched 10 harmless strings (`crawl4ai-download-models`, `crawl4ai-standalone`,
  the `crawl4ai-service:<tag>` image names), so "must return empty" could never hold and
  trained us to wave it through. A check that always cries wolf is worse than no check.
- **`jwt-secret-` included** — old deploy scripts minted `jwt-secret-$(openssl rand -hex 32)`;
  keep catching the shape even though those scripts were deleted 2026-07-17.

Token shapes this catches: `crawl4ai-<32-or-48 hex>`, `crawl4ai-test-<32 hex>`,
`jwt-secret-<64 hex>`.

---

## What's Ours vs Upstream

### Integration Architecture (wrapper entry point)
We use a **wrapper entry point** (`aitosoft_entry.py`) that imports and extends
upstream's `server.py`. This keeps merges clean.

```
gunicorn → aitosoft_entry:app
             ├─ BrowserConfig.set_defaults(**config.yml)  # config.yml defaults for all requests
             ├─ untrusted-boundary relaxations             # allow browser_config.headers; page_timeout cap 60s→180s
             └─ from server import app                     # upstream (auth comes with it)
```

Auth is upstream's `AuthGateMiddleware` since v0.9.2: `Authorization: Bearer
$CRAWL4AI_API_TOKEN`, fail-closed, constant-time. Only `/health` is public.

**v0.9.x untrusted-config boundary (debug 400s here):** request-body configs are
filtered — forbidden fields give HTTP 400, unknown fields are silently dropped,
`page_timeout` is clamped (to 180 s, not upstream's 60 s). See
`crawl4ai/async_configs.py` UNTRUSTED_* constants + our relaxations in
`aitosoft_trust.py`.

**Two things this file asserted that are false — verified by executing
`apply_trust_relaxations()` 2026-08-06, not by reading:**

- **`magic`, `simulate_user` and `override_navigator` are ACCEPTED, not rejected.**
  `aitosoft_trust.py:44-49` discards them from the forbidden set and adds them to
  the allowlist for our single trusted client. Four files still say the server
  rejects `magic`. **All of those were fixed 2026-08-06 to 2026-08-09** —
  `TESTING.md`, `TEST_SITES_REGISTRY.md` and `test_site.py` now say the server
  accepts it and that the ban is about page damage. If you find another copy,
  it is stale — **and that is the dangerous
  direction**: a session could send `magic: true` believing the boundary would
  stop it. It would not, and January is what `magic` does to a page. The *harm*
  argument stands on its own; the "server rejects it" argument does not.
- **"400 on presence, even falsy" is false for our server.**
  `aitosoft_trust.py:51-63` **drops** falsy forbidden fields instead of rejecting.
  Truthy ones still 400.

The actual forbidden sets, after our relaxations:
`CrawlerRunConfig` — `base_url c4a_script deep_crawl_strategy experimental
fallback_fetch_function js_code js_code_before_wait process_in_browser
proxy_config proxy_rotation_strategy proxy_session_* session_id shared_data`.
`BrowserConfig` — `browser_context_id cdp_url channel chrome_channel cookies
debugging_port extra_args host init_scripts proxy proxy_config storage_state
target_id user_data_dir`. Note `cookies` and `extra_args` are **BrowserConfig**
fields; this file listed them as if they were `CrawlerRunConfig`.

### Aitosoft Modifications (changes to upstream files)
| File | What changed |
|------|-------------|
| `Dockerfile` | `RUN playwright install chrome` + copy chrome cache to appuser |
| `crawl4ai/browser_manager.py` | `_build_browser_args`: GPU flags gated on `enable_stealth` (PR upstream pending) |
| `crawl4ai/antibot_detector.py` | +`effective_status()` — the final redirect hop is what block detection must judge (PR upstream pending) |
| `crawl4ai/async_webcrawler.py` | 3× `is_blocked` fed the final hop; `total_timeout` deadline shared by every attempt (PR upstream pending) |
| `crawl4ai/browser_adapter.py` | `bounded_evaluate()` + `timeout` kwarg — `page.evaluate` has no protocol timeout (PR upstream pending) |
| `crawl4ai/async_crawler_strategy.py` | `_capture_html()` settle-and-retry for `page.content()`; bounds on optional DOM steps, `page.close()`, virtual scroll (PR upstream pending); `remove_consent_popups(page, url)` reads the snippet's report and logs it, and detects a self-inflicted click-navigation from `page.url` (`_report_consent_pass`) |
| `crawl4ai/js_snippet/remove_consent_popups.js` | Structural guard (`documentElement`/`body`/`head` are never removed); the 20 generic selectors (18 substring patterns + `.cc-banner`/`.cc-window`) **observe instead of removing**; returns a report. **Was byte-identical to upstream** — **fifth** PR candidate, written and now *fileable* (its "wait for segment 2" gate fired on 2026-08-06; see `tasks/file-upstream-prs.md`) |
| `crawl4ai/js_snippet/remove_overlay_elements.js` | Same structural guard; `backgroundColor.includes("rgba")` → a real alpha test. **Was byte-identical to upstream** — sixth PR candidate |
| `crawl4ai/async_configs.py` | +`CrawlerRunConfig.total_timeout` (default None, server-side only) (PR upstream pending) |
| `crawl4ai/content_scraping_strategy.py` | +`strip_noscript()` before `document_fromstring` — a nested `<noscript>` makes libxml2 swallow the whole body (PR upstream pending); +`MEDIA_DESCRIPTION_MAX_CHARS = 200` capping `find_closest_parent_with_useful_text` — an image's `desc` was an ancestor's whole subtree text, i.e. the whole page, copied per image and per srcset variant (**seventh PR candidate, and the cleanest**) |
| `deploy/docker/egress_proxy.py` | Both `resolve_and_pin` calls awaited off the loop; connect budget 30 s→15 s (`DEFAULT_CONNECT_TIMEOUT_S` + ctor arg); `http://` connect failure **closes** instead of replying `_BLOCKED`. **Was byte-identical to upstream** — new merge surface, and an unnumbered PR candidate (this row said "fifth" too; `tasks/file-upstream-prs.md` is the numbering, and it gives fifth to the consent snippet) |
| `deploy/docker/egress_broker.py` | `_resolve` docstring only: it is blocking, callers on a loop must offload it. **Was byte-identical to upstream** |
| `deploy/docker/utils.py` | **+74/−1 over upstream — this row said "unchanged" until 2026-08-14 and that was false in the dangerous direction.** What is unchanged *deliberately* is `validate_url_destination`: its opaque 400 is right for the seven non-crawl endpoints that share it. What is **ours** is the whole memory instrument — `_read_memory_stat`, `get_memory_breakdown`, `get_container_memory_percent` (`utils.py:411-507`), i.e. the reading the pool's memory guard refuses on. A session trusting the old row would have treated the guard's metric as upstream and routed a fix elsewhere. Verify with `git diff upstream/develop -- deploy/docker/utils.py`, not by reading this table |
| `crawl4ai/antibot_detector.py` | +challenge tier (`robot-suspicion`, browser-check prose); `Access Denied` tightened to title/heading |
| `deploy/docker/api.py` | +static-mode short-circuit, patchright retry inside wall-clock deadline, `render_mode` tagging, render-admission gate (429 when replica full; fence starts after admission), single-URL guard (multi-URL → 400), fence-504 warning; `failure_class` on every result, `status_code` rewritten to the final redirect hop, origin-caused exceptions return an envelope not a 500, monitor records the client's real outcome, collapse guard on every successful result; seed SSRF check awaited **off the loop** (it runs before render admission, so it is not bounded by render capacity) and a host with no address at all is `origin_unreachable` at 200, not an SSRF 400 |
| `deploy/docker/server.py` | static branch in `/crawl`; lifespan closes static client + patchright singleton; `_crawl_response` maps `failure_class` → 200/504/500 for **both** render modes instead of always 500 (full) / always 200 (static); error envelopes carry `failure_class` |
| `deploy/docker/schemas.py` | `CrawlRequest.render_mode` field |
| `deploy/docker/crawler_pool.py` | MAX_PAGES enforcement + overflow keys; BUSY_SINCE stuck-slot janitor; `max_browsers` cap + LRU eviction of *idle* browsers (evict-or-refuse, **never wait** — waiting deadlocks against `release_crawler`); memory-adaptive TTL collapse removed (file unchanged upstream since 0.8.6) |
| `deploy/docker/config.yml` | Deployment config: stealth kwargs, `wall_clock_s: 180`, `total_timeout: 100000` (per-`arun` fetch budget), pool limits, render admission (`render_capacity: 2` — **deliberately NOT tied to the ACA scale rule**; they are different quantities in different units, see the Key Findings row). `base_config`'s `simulate_user` sat at `true` for ~10 months and **never applied** (`api.py:861-881` fills only `None`/`""`), and is now explicit `false`. **Deleting it would have changed nothing** — `utils.py:63`'s `DEFAULT_CONFIG` carries `simulate_user: True` and `load_config()` deep-merges this file on top, so an absent key inherits `True`. An explicit `false` is what defuses it: fixing that merge rule now sets `False` instead of silently turning user simulation on for every request. Zero behaviour change today |
| `deploy/docker/supervisord.conf` | Entry point: `aitosoft_entry:app` instead of `server:app`; +`RES_OPTIONS="timeout:2 attempts:2 ndots:1"` — glibc's per-process resolver override, no root needed |

Dropped in v0.9.2 upgrade (upstream superseded): browser_adapter stealth port
(upstream #1960), api.py timeout patch (`limits.wall_clock_s`),
`simple_token_auth.py` (upstream `AuthGateMiddleware`).

### New Aitosoft Files (in upstream directories)
| File | Purpose |
|------|---------|
| `deploy/docker/aitosoft_entry.py` | Wrapper entry point: BrowserConfig defaults + trusted-client boundary relaxations |
| `deploy/docker/aitosoft_static_mode.py` | `render_mode: "static"` implementation (httpx + html2text) |
| `deploy/docker/aitosoft_patchright_fallback.py` | Second-tier retry via patchright for blocked crawls |
| `deploy/docker/aitosoft_admission.py` | RenderGate: per-replica render admission (capacity 2, bounded queue, 429 + Retry-After) |
| `deploy/docker/aitosoft_trust.py` | Trusted-client relaxations of the untrusted-config boundary (pinned by test_mas_contract.py) |
| `deploy/docker/aitosoft_failure_class.py` | `failure_class` taxonomy + transport mapping — the single place `net::ERR_*` / ACS-GOTO / download text is matched, and the single place a class becomes a wire status (`http_status_for`). Both `api.py`'s exception gate and `server._crawl_response` now ask it rather than testing set membership. A capture with **no `<body>` element** is `render_defect` at 200, not `render_error` at 500 — permanence, not emptiness |
| `deploy/docker/aitosoft_collapse_guard.py` | Detects a capture whose body vanished in our parse: **visible text chars in vs markdown chars out**, never an HTML-byte ratio. Thresholds measured against 37 stored real captures. Also **recovers** it — html2text over the same rendered HTML, accepted only if it clears both floors; recovered pages go out as ordinary successes |

### 100% Aitosoft Code (safe to modify freely)
- `tasks/` — task tracking
- `test-aitosoft/` — test suite, fingerprint diagnostics, persona reference.
  `fixture_origin.py` is the local failure-class origin (routes + the
  `fixture_origin` / `production_path` pytest fixtures, registered for the
  directory by `conftest.py`); reach for it before reaching for a live host
- `azure-deployment/` — deployment scripts and docs
- `.devcontainer/` — dev container setup
- `CLAUDE.md`, `AITOSOFT_CHANGES.md`, `AITOSOFT_FILES.md`, `DEPLOYMENT_INFO.md`

### Upstream sync
- **Last synced:** upstream/develop == v0.9.2 (2026-07-16)
- **Sync procedure:** `git fetch upstream && git merge upstream/develop` — near-conflict-free; our whole delta is the tables above
- **Key technique:** `BrowserConfig.set_defaults()` (upstream's `@_with_defaults` in `async_configs.py`) applies config.yml defaults to every request without patching `api.py`. **`CrawlerRunConfig` is decorated the same way (`:1329`) and we do not use it** — see the Key Findings row; it is a lever, not a gap
- **CRITICAL:** never run formatters over upstream files — pre-commit is scoped to Aitosoft files via the top-level `files:` pattern in `.pre-commit-config.yaml`. Keep it that way or merges drown in noise (see AITOSOFT_CHANGES.md v0.9.2 entry)

---

## Documentation Index

**Always read at session start:** This file (auto-loaded) + `tasks/README.md`
(ordered open work).

**Read when needed:**
| Doc | When |
|-----|------|
| `tasks/waa-eval-2026-07-30-forensics.md` | The five root causes behind the 2026-07-30 image; cited by most open tasks |
| `AITOSOFT_CHANGES.md` | Understanding what we changed and why (authoritative change log) |
| `AITOSOFT_FILES.md` | Quick inventory of our files vs upstream |
| `DEPLOYMENT_INFO.md` | Endpoint, credentials, Azure resource details |
| `TESTING.md` | Full testing framework, quality gates |
| `TEST_SITES_REGISTRY.md` | Test site metadata, expected contacts, patterns |
| `OVERNIGHT_PLAYBOOK.md` | Tero says "monitor overnight" — read this, then loop via `ScheduleWakeup` |

---

## Azure Deployment

- **Endpoint:** `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Image:** `aitosoftacr.azurecr.io/crawl4ai-service:0.9.2-desc-cap` (revision `--0000040`, deployed 2026-08-09 14:31 UTC). This line goes stale — **`AITOSOFT_CHANGES.md` "Current State" is authoritative**, and `az containerapp revision list` beats both.
- **Resources:** 2 vCPU / 4 GiB per replica, **0-45 replicas** (raised from 30 on 2026-08-08 for MAS's ~18,000-company plan; scales to zero; explicit `http-renders` scale rule — trigger **6**, see below). **The hard ceiling is 50** — environment quota `ManagedEnvironmentConsumptionCores` is 100 and we are 2 vCPU/replica (`az containerapp env list-usages`); MAS's `aitosoft-edge` shares the environment at 0.25 cores. The scale rule "MUST match `render_capacity`" claim is **settled and gone** — it was a category error (different quantities, different units), the trigger is **6** since 2026-08-08, and `deploy-image.sh` now checks the live rule against its own `ACA_SCALE_TRIGGER` constant instead of against `render_capacity`. **2 vCPU / 4 GiB is this environment's hard maximum** — it is a legacy Consumption-only managed environment and Azure rejects anything larger; more memory needs an environment migration with a different billing model, not a resize (2026-08-02, tested).
- **Auth:** Bearer token via `CRAWL4AI_API_TOKEN` env var
- See `DEPLOYMENT_INFO.md` for full details

**Deploy flow:**
```bash
./azure-deployment/deploy-image.sh <tag>   # az acr build + image-only update + invariant check
```
Never set env vars during a deploy — that's how MAS's token gets broken.
Provisioning reference (scale rule, probes, env vars): `DEPLOYMENT_INFO.md`.

---

## Cross-Repo Communication

This repo works alongside `aitosoft-platform` (main multi-agent system). Both have
Claude as developer. To exchange information between repos, ask the business owner
to relay messages. Use for: API contracts, deployment coordination, debugging shared issues.

Messages live in gitignored `tmp/mas-repo-messages/`, numbered and
direction-labelled. **Cite filenames, never integers** — the two repos' numbering
has diverged before and a message sat unread for two days because of it.

Three habits that have each paid out, with the reasoning so they can be broken
when the situation differs:

- **Divide work by what each side can physically see, not by who thought of it.**
  We can see inside the browser; they can see 117,000 stored pages and the
  agent's decisions. The 2026-08-06 defect was invisible to their archive *by
  construction*, and their click-channel ceiling was invisible to ours. Written
  up in `tmp/mas-repo-messages/20-…` §6.
- **Verify their diagnosis before adopting it, and expect them to verify ours.**
  They run several agents on a problem and their read moves between messages;
  so does ours. Twice in one week each side corrected a claim of the other's
  that had reached a right answer by a route that did not exist.
- **Count headline numbers twice, from two instruments.** Cheap when both sides
  have already counted, and it has caught an artefact on each side.

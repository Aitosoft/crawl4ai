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
Each task file has: goal, status, plan, progress, learnings. **Start each session by
reading `tasks/README.md`** — the ordered index of open work, with the gate on each.
Ordering lives only there; the task files carry the reasoning.

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
pytest test-aitosoft/            # ALL offline suites, 271 tests, ~235 s — no server, no customer site
pytest test-aitosoft/ --ignore=test-aitosoft/test_fixture_origin.py  # pure-function subset, 217 tests, ~13 s
pytest test-aitosoft/test_fixture_origin.py   # browser-driven, local fixture origin, 54 tests, ~220 s
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
  "crawler_config": {"locale": "fi-FI", "timezone_id": "Europe/Helsinki", "max_retries": 2}
}
```
`browser_config` fields override config.yml defaults. `locale`, `timezone_id`, `geolocation`
are on CrawlerRunConfig (forwarded to Playwright `new_context()`).

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
| `remove_consent_popups: true` solves cookie walls | Accountor: 7811 tokens without magic mode |
| Raw markdown > fit_markdown for contact extraction | PruningContentFilter removes contacts at threshold >= 0.35 |
| Use `optimal` config by default | domcontentloaded + remove_consent_popups (2-4s) |
| Blocked sites are IP-based, not fingerprint-based | Confirmed: two different browser engines get identical blocks |
| Block detection must use `redirected_status_code` | `status_code` is the FIRST redirect hop; the body is the LAST. Judging the 301 let every redirect-to-block page through as success (2026-07-30) |
| `page.content()` / `page.evaluate()` have NO timeout | Sent to the driver with no timeout field ⇒ no timer armed; they wait on the frame's execution-context promise, which a navigation replaces forever. `page_timeout` does not cover them. Bounded in `browser_adapter.bounded_evaluate` + `_capture_html` |
| Origin failures must never be our 5xx | Fixed 2026-07-30: `failure_class` on every result; origin-caused ⇒ HTTP 200 + `success:false`; 5xx reserved for us. `deploy/docker/aitosoft_failure_class.py`, MAS Q2 answer (a) |
| A nested `<noscript>` deletes the whole page | `<noscript>` can't nest ⇒ outer element never closes ⇒ libxml2 swallows the rest. 312 KB → 97 B `cleaned_html` → 1 B markdown, at HTTP 200 `success:true`. 406 pages / 70 hosts. Fixed by `strip_noscript()` pre-parse |
| An **unclosed** `<noscript>` still does, and the offline suite can't see it | libxml2 auto-closes it, so `test_noscript_body_collapse.py` reports that shape fixed. Chromium instead enters raw-text mode and serializes the rest of the document — `</body></html>` included — *inside* the element, so `strip_noscript()` correctly removes the element and takes the page with it. Only visible with a browser in the loop; found by `fixture_origin` 2026-07-31 |
| **Four** markup shapes swallow the body, not one | Enumerated through the browser at 73 KB, 2026-08-01: `unclosed-noscript`, `unclosed-script`, `deep-nesting` (libxml2 depth limit), `unterminated-comment`. Three distinct mechanisms, all deterministic. `deep-nesting` is **harmless at 1.5 KB and fatal at 73 KB** — enumerate padded or you will miss root causes, not just mis-size thresholds. Root cause still open (`tasks/cleaned-html-collapse-guard.md` part 2) |
| A consumer's "no issues" is not evidence of no data loss | MAS called the 2026-08-01 run clean. **9 of its 328 pages, on 7 of 38 hosts, came back with 0 characters of markdown** from 725–40,165 chars of visible text. The failure is invisible from their side *by construction* — a page with no contacts looks exactly like a page that has none. Record what we measured, never what we were told |
| A detected collapse can often be **recovered**, not just reported | `html2text` over the same rendered HTML returns the full body for `unclosed-noscript` (1,265 chars — *identical* to the healthy control) and `deep-nesting`, and nothing for `unterminated-comment` / `unclosed-script`. It is the converter `aitosoft_static_mode` already ships, so recovery costs **no** new divergence from upstream's parser — one fallback beats three pre-parse repairs (2026-08-02, shipped) |
| Reuse the **converter**, not the pipeline around it | "We already ship html2text" was true of `HTML2Text` and false of `aitosoft_static_mode._fetch_static_one`, which runs `_strip_hidden_decoys()` first — and that `decompose()`s every `noscript`, so on an unclosed one it deletes the whole document Chromium re-serialized inside it. **1,265 chars → 0.** The same failure as `strip_noscript()`, by a different route |
| A fix for silent loss can open a **new** silent-loss channel | Recovery accepted on MAS's 500-char degenerate floor alone lets a 599-char rescue of a 41,408-char page out as `success: true` — green, used, 40,809 chars gone. The symmetry argument ("treat a recovery as the normal path would") is wrong: on the normal path we have no evidence of loss; here **the guard has already proved it**. Recovery must clear the ratio floor too (measured headroom 10–28×) |
| `arun` does not raise — it returns a failed result | A task file built a five-step chain on `classify_exception`; upstream wraps its whole body in `try:` and returns `CrawlResult(success=False, …)`, so `classify_result` decides. The log-line *prefix* is the tell: `Crawl request failed:` is built only in `server._crawl_response` (the result path); the exception path emits JSON. Also: upstream retries on **any** exception, not just blocks, so one request at `max_retries: 2` is **three** navigations |
| Moving a class off 5xx deletes its only log line | Nothing logged a failed *result*'s `failure_class` — those URLs were visible only because they produced a 500, and `server.py` logs 500s. So the taxonomy's own success (fewer 5xx) was silently costing observability, and `unrenderable_content` was about to ship with no server-side counter. `RESULT FAILURE` now covers every failed result. `ORIGIN FAILURE` is on the *exception* path, which `arun` almost never takes — it had been describing a token that rarely fires |
| A download is nobody's fault and permanent | Chromium refuses to commit a navigation to a download, at any content type — inline `application/pdf` and `application/octet-stream` behave exactly like `Content-Disposition: attachment`, so the trigger is "will not render inline", not the header. `unrenderable_content` at 200; `origin_http_error` was rejected because upstream leaves `status_code` **null**, making it a lie visible in the field MAS was promised. `accept_downloads: true` does not rescue it |
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
| Per-replica render capacity is 2 (2 vCPU) | Benchmarked 2026-07-17; >2 concurrent renders degrade all requests. Enforced by RenderGate + ACA scale rule |

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

**v0.9.x untrusted-config boundary (debug 400s here):** request-body configs
are filtered — forbidden fields (`magic`, `js_code`, `simulate_user`, proxy
fields, `extra_args`, `cookies`…) give HTTP 400 **on presence, even falsy**;
unknown fields are silently dropped; `page_timeout` is clamped. See
`crawl4ai/async_configs.py` UNTRUSTED_* constants + our relaxations in
`aitosoft_entry.py`.

### Aitosoft Modifications (changes to upstream files)
| File | What changed |
|------|-------------|
| `Dockerfile` | `RUN playwright install chrome` + copy chrome cache to appuser |
| `crawl4ai/browser_manager.py` | `_build_browser_args`: GPU flags gated on `enable_stealth` (PR upstream pending) |
| `crawl4ai/antibot_detector.py` | +`effective_status()` — the final redirect hop is what block detection must judge (PR upstream pending) |
| `crawl4ai/async_webcrawler.py` | 3× `is_blocked` fed the final hop; `total_timeout` deadline shared by every attempt (PR upstream pending) |
| `crawl4ai/browser_adapter.py` | `bounded_evaluate()` + `timeout` kwarg — `page.evaluate` has no protocol timeout (PR upstream pending) |
| `crawl4ai/async_crawler_strategy.py` | `_capture_html()` settle-and-retry for `page.content()`; bounds on optional DOM steps, `page.close()`, virtual scroll (PR upstream pending) |
| `crawl4ai/async_configs.py` | +`CrawlerRunConfig.total_timeout` (default None, server-side only) (PR upstream pending) |
| `crawl4ai/content_scraping_strategy.py` | +`strip_noscript()` before `document_fromstring` — a nested `<noscript>` makes libxml2 swallow the whole body (PR upstream pending) |
| `crawl4ai/antibot_detector.py` | +challenge tier (`robot-suspicion`, browser-check prose); `Access Denied` tightened to title/heading |
| `deploy/docker/api.py` | +static-mode short-circuit, patchright retry inside wall-clock deadline, `render_mode` tagging, render-admission gate (429 when replica full; fence starts after admission), single-URL guard (multi-URL → 400), fence-504 warning; `failure_class` on every result, `status_code` rewritten to the final redirect hop, origin-caused exceptions return an envelope not a 500, monitor records the client's real outcome, collapse guard on every successful result |
| `deploy/docker/server.py` | static branch in `/crawl`; lifespan closes static client + patchright singleton; `_crawl_response` maps `failure_class` → 200/504/500 for **both** render modes instead of always 500 (full) / always 200 (static); error envelopes carry `failure_class` |
| `deploy/docker/schemas.py` | `CrawlRequest.render_mode` field |
| `deploy/docker/crawler_pool.py` | MAX_PAGES enforcement + overflow keys; BUSY_SINCE stuck-slot janitor; `max_browsers` cap + LRU eviction of *idle* browsers (evict-or-refuse, **never wait** — waiting deadlocks against `release_crawler`); memory-adaptive TTL collapse removed (file unchanged upstream since 0.8.6) |
| `deploy/docker/config.yml` | Deployment config: stealth kwargs, `wall_clock_s: 180`, `total_timeout: 100000` (per-`arun` fetch budget), pool limits, render admission (`render_capacity: 2` — MUST match ACA scale rule) |
| `deploy/docker/supervisord.conf` | Entry point: `aitosoft_entry:app` instead of `server:app` |

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
| `deploy/docker/aitosoft_failure_class.py` | `failure_class` taxonomy + transport mapping — the single place `net::ERR_*` / ACS-GOTO / download text is matched, and the single place a class becomes a wire status (`http_status_for`). Both `api.py`'s exception gate and `server._crawl_response` now ask it rather than testing set membership |
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
- **Key technique:** `BrowserConfig.set_defaults()` (upstream's `@_with_defaults` in `async_configs.py`) applies config.yml defaults to every request without patching `api.py`
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
- **Image:** `aitosoftacr.azurecr.io/crawl4ai-service:0.9.2-collapse-recovery` (revision `--0000034`, deployed 2026-08-02). This line goes stale — **`AITOSOFT_CHANGES.md` "Current State" is authoritative**, and `az containerapp revision list` beats both.
- **Resources:** 2 vCPU / 4 GiB per replica, 0-30 replicas (scales to zero; explicit `http-renders` scale rule at 2 concurrent/replica — MUST match `render_capacity` in config.yml). **2 vCPU / 4 GiB is this environment's hard maximum** — it is a legacy Consumption-only managed environment and Azure rejects anything larger; more memory needs an environment migration with a different billing model, not a resize (2026-08-02, tested).
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

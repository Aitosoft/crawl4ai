# Add `mode=static` Fallback to `/crawl` Endpoint

**Status:** open, ready to start
**Origin:** Inbound handoff from the MAS repo after the 2026-04-15 roadscanners.com investigation (F-87o-04). Reframed from "fix the hang" to "route around the Playwright capability gap."
**Estimated effort:** ~2h implementation + ~1h verification + deploy.

---

## TL;DR

Add a new request mode to the `/crawl` endpoint that fetches URLs via plain
`httpx.get` + converts the response to markdown with `html2text`, bypassing
Playwright entirely. This gives MAS a clean fallback for sites where
Playwright hangs at the C-level DevTools protocol before our instrumentation
can even log (ref: Fix 1 timeout path). The fallback is opt-in per request;
the default `/crawl` path stays unchanged.

---

## Who reads this file

Anyone with no prior session context. You're Claude working in the
`crawl4ai-aitosoft` repository. All necessary background is in this file +
the files it points to.

---

## Background the reader needs

### What this repo is

Fork of `github.com/unclecode/crawl4ai` customized for Aitosoft's internal
use. Runs on Azure Container Apps as a bearer-token-auth'd scraping service.
The only consumers are Aitosoft's own AI agents, primarily the **Website
Analysis Agent (WAA)** running in the sibling repo `aitosoft-platform`
(internally nicknamed "MAS" — multi-agent system). See `CLAUDE.md` for a
concise architecture overview and `AITOSOFT_CHANGES.md` for the change log.

### Production state (as of 2026-04-15)

- **Image:** `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-leak-fix`
- **Endpoint:** `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Resources per replica:** 2 vCPU / 4 GiB, minReplicas=3 (during batches)
  up to maxReplicas=20 via KEDA http-scaler.
- **Hardening in place:** Fix 1 (180s `asyncio.wait_for` around arun +
  patchright retry in `deploy/docker/api.py`), Fix 2 (janitor force-close
  stuck browser slots in `deploy/docker/crawler_pool.py`), Fix 3
  (`./azure-deployment/batch-scale.sh` to pin minReplicas during runs).
  See `tasks/done/scale-audit-2026-04-14.md` for the capacity analysis and
  `AITOSOFT_CHANGES.md` "Request-Timeout + Stuck-Slot Leak Fixes" for the
  full write-up.
- **Verified at scale:** Two overnight batches have run since the fixes
  — ~2,200+ page completes, ~165 clean Fix-1 504s, 0 stuck-slot
  force-closes, 0 outages.

### How MAS uses `/crawl` today

MAS calls `POST /crawl` with `{"urls": [url], "crawler_config": {...},
"browser_config": {...}}`. The crawler returns a JSON payload of the shape:

```json
{
  "success": true,
  "results": [ { "url": "...", "markdown": { "raw_markdown": "...", "fit_markdown": "..." }, "links": {...}, "success": true, ... } ],
  "server_processing_time_s": 12.3,
  "server_memory_delta_mb": 0.0,
  "server_peak_memory_mb": 240
}
```

On the server side this goes through `handle_crawl_request` in
`deploy/docker/api.py`, which calls `AsyncWebCrawler.arun` (Playwright under
the hood) wrapped in `asyncio.wait_for(..., timeout=180)`. When the 180s
timeout trips, the endpoint returns HTTP 504 with a structured detail body.

MAS also uses a second mode internally called `mode=links_only` — their
client-side wrapper, NOT an endpoint on our side — which fetches raw HTML
over HTTP and only extracts `<a href>` links. That mode already proves the
raw HTML of "problem hosts" is reachable by plain HTTP; it just doesn't
extract readable content.

---

## Why this task exists

During batch execution on 2026-04-15, the domain
`https://www.roadscanners.com/*` caused Playwright to hang in a way our
180s timeout (Fix 1) was the only thing able to rescue. Investigation in
Azure Log Analytics showed:

- **Every other site** emits `[FETCH]` / `[SCRAPE]` / `[COMPLETE]` banners
  within 5-20s.
- **Every roadscanners request** produced the pool `Using hot pool browser`
  log then NOTHING for 180s until Fix 1 fired. Zero `[FETCH]`, zero
  `[SCRAPE]`, zero `[ANTIBOT]`, zero `[patchright]`.
- Playwright's internal 60s `page_timeout` should have fired first but did
  not, meaning the hang is in a C-level DevTools-protocol/IPC await that
  doesn't respect our Python-level timeout the way a regular `asyncio.sleep`
  would.
- The site's HTML is reachable by plain HTTP. MAS's Gemini-grounded search
  successfully summarized the `/contact/offices/` page content (server-side
  rendered). Other sites exhibit the same pattern (Framer/Next.js SPAs,
  certain custom stacks).

This is a **Playwright-level capability gap**, not a crawl4ai bug. The right
fix is an alternate rendering path, not deeper surgery on Playwright's
wait-state machinery.

MAS's agreed client-side behavior once this task lands: after 2 consecutive
504s on the same host in a session, auto-pivot that host to
`render_mode: "static"` for the remainder of the session. This caps the
worst-case per-company cost at 2 × 180s = 360s before the host is
blacklisted for the session.

### Parent project on the MAS side

MAS is preparing a multi-night campaign (internally called task-181) to
enrich ~9,600 Talgraf CRM companies at 2,000 companies/night with 5 parallel
WAA agents. The fix-the-gap work for `render_mode=static` must ship before
that campaign starts so the per-company budget is deterministic.

---

## What to build

### Scope

Add a new request field to the existing `POST /crawl` endpoint. A minimal,
decisive contract:

**Request:** same shape as today, with one new optional field in the
top-level JSON: `"render_mode": "static"` (default `"full"`).

```json
POST /crawl
{
  "urls": ["https://www.roadscanners.com/contact/offices/"],
  "render_mode": "static",
  "crawler_config": {}
}
```

When `render_mode == "static"`:
- Do **not** acquire a crawler from the browser pool. Do not touch
  Playwright.
- Use `httpx.AsyncClient` to GET each URL. Timeout: **15s per URL**
  (separate from Fix 1's 180s bound; static requests should be fast or
  fail fast). `verify=False` to tolerate broken TLS (same rationale as
  the existing `--ignore-certificate-errors` in `config.yml`'s
  `extra_args`). Follow redirects.
- Convert the response body to markdown using the `html2text` package
  that's vendored into crawl4ai at `crawl4ai/html2text/__init__.py` — reuse
  it to avoid adding a new dependency.
- Return a `CrawlResult`-shaped dict in the existing `"results": [...]`
  wrapper so MAS's client code doesn't branch. Minimum fields:
  - `url`: final URL (post-redirect)
  - `success`: bool
  - `status_code`: int
  - `markdown.raw_markdown`: string
  - `markdown.fit_markdown`: `""` (no pruning pass; keep cost minimal)
  - `error_message`: string or null
  - **`render_mode`: `"static"`** — NEW field so MAS can weight confidence
    downstream. Also set this to `"full"` on the existing path so every
    response reliably indicates what produced it.
  - `links`: best-effort object with `internal` / `external` arrays
    extracted via BeautifulSoup or a simple regex. If cheap to add, yes.
    If it adds meaningful complexity, return
    `{"internal": [], "external": []}` — MAS already has its own link
    extractor and doesn't depend on us for this in static mode.
- Keep the top-level `server_processing_time_s`,
  `server_memory_delta_mb`, `server_peak_memory_mb` fields populated so
  monitoring queries continue to work.

### Error handling

- httpx timeout or connection error → return HTTP **200** with an
  error-shaped result payload:
  ```json
  {
    "success": true,
    "results": [{
      "url": "...",
      "success": false,
      "status_code": 0,
      "error_message": "static-fetch: timeout after 15s",
      "render_mode": "static",
      "markdown": {"raw_markdown": "", "fit_markdown": ""},
      "links": {"internal": [], "external": []}
    }]
  }
  ```
  NOT HTTP 504 — 504 is reserved for Fix 1's "we tried to render and failed"
  case. Static failures should be fast failures, distinguishable in logs.
- httpx returns 4xx/5xx from the site → still wrap the (usually error-page)
  body as markdown and return `success: false` in the inner result with the
  upstream status code. MAS can decide whether that's useful.

### Out of scope (do not do)

- Do **not** modify the existing `full` path behavior. The leak-fix stack is
  production-proven; do not risk it.
- Do **not** add a separate endpoint (e.g. `/crawl/static`). Keeping it as a
  field on `/crawl` lets MAS's single client path work unchanged.
- Do **not** add hookability, extraction strategies, or content filtering
  for static mode. Static is deliberately minimal: raw HTML → markdown.
  That's what MAS is asking for.
- Do **not** touch `handle_stream_crawl_request` / `/crawl/stream` — static
  mode is non-streaming by definition.
- Do **not** add the `/monitor/recent-504s` endpoint MAS mentioned as a
  secondary ask. That's explicitly deferred to a future iteration.
- Do **not** pursue the upstream `page.content()` timeout investigation.
  Also deferred.

---

## Files to touch

Primary:

- **`deploy/docker/api.py`** — add a branch at the top of
  `handle_crawl_request` (see the function around line 573; enter the
  static branch right after the `urls = [...]` normalization and before
  `BrowserConfig.load(browser_config)`) that reads `render_mode` from the
  request payload and dispatches to a new `handle_static_crawl_request`
  helper when `render_mode == "static"`. The new helper does the
  httpx+html2text work and returns the same response shape as the
  full-mode branch.

- **`deploy/docker/server.py`** — the `CrawlRequestWithHooks` pydantic
  model (grep for it; it's the `/crawl` endpoint's request body schema)
  needs a new optional field
  `render_mode: Literal["full", "static"] = "full"`.

Likely:

- **`deploy/docker/requirements.txt`** (or `pyproject.toml`) — confirm
  `httpx` is already present (it is — `monitor_routes.py` and other parts
  use it). `html2text` is already vendored in `crawl4ai/html2text/` and
  should be imported directly: `from crawl4ai.html2text import HTML2Text`.

Tests:

- **`test-aitosoft/test_site.py`** — add a `--render-mode static` CLI flag
  so we can ad-hoc test the new mode against a URL.
- **`test-aitosoft/test_soak.py`** — optional: add a static-mode variant to
  the soak harness to confirm no regression under load. Not a blocker.

Docs:

- **`AITOSOFT_CHANGES.md`** — add a new section under "Current State"
  describing the new mode and the deploy tag.
- **`DEPLOYMENT_INFO.md`** — no change expected unless the deploy procedure
  changes.

---

## Verification

Before declaring done, run these against the DEPLOYED service (not local):

### 1. The target case — roadscanners.com

```bash
set -a; source .env; set +a
curl -s -H "Authorization: Bearer $CRAWL4AI_API_TOKEN" \
     -H "Content-Type: application/json" \
     -X POST "$CRAWL4AI_API_URL/crawl" \
     -d '{
       "urls": ["https://www.roadscanners.com/contact/offices/"],
       "render_mode": "static"
     }' | python -m json.tool
```

**Acceptance:** top-level `success: true`; result has `render_mode:
"static"`, `success: true`, and `markdown.raw_markdown` contains ALL of
the following strings:
- `annele.matintupa@roadscanners.com`
- `virpi.halttu@roadscanners.com`
- one of `+358 40 1544 011` or `+358 50 353 4268`

If any are missing, the static renderer stripped content MAS needs. Debug
before shipping.

### 2. Non-regression — Tier 1 regression suite

```bash
python test-aitosoft/test_regression.py --tier 1 --version static-mode
```

Must be **4/4 PASS** using the existing `full` mode (Tier 1 runs without
`render_mode` set, so it exercises the default path). This gates that
nothing about the new branch broke the existing one. Tier 1 covers
caverna.fi, accountor.com/fi/finland, solwers.com, jpond.fi — see
`test-aitosoft/test_regression.py` for the list.

### 3. Short soak — optional but preferred

```bash
python test-aitosoft/test_soak.py --duration-min 30 --parallel 1
```

Confirms memory still stays flat and Fix 1 still fires cleanly. The existing
test doesn't exercise `render_mode=static` yet — acceptable; the goal here
is non-regression of the full-mode path. If you've extended the soak with a
static-mode variant, run both.

### 4. Spot-check a second SPA site

Pick one live Finnish SPA (`https://www.columbia-road.com/about/`, a
Framer-hosted one, or any site in your own judgment). Send a
`render_mode: "static"` request and confirm the response shape is correct
even if the content isn't as rich as roadscanners.

---

## Deploy procedure

Identical to the procedure in `DEPLOYMENT_INFO.md` "Update to New Version",
which is the proven path that preserves the `CRAWL4AI_API_TOKEN` env var:

```bash
# 1. Build in ACR (no local Docker required). Choose a meaningful tag.
az acr build --registry aitosoftacr \
  --image crawl4ai-service:0.8.6-static-mode \
  --file Dockerfile .

# 2. Swap the image (preserves env vars including the MAS bearer token).
az containerapp update \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --image aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-static-mode

# 3. Health-check
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io/health
```

**Do NOT use** `deploy-aitosoft-prod.sh --update-only` — it regenerates the
API token (documented gotcha in `DEPLOYMENT_INFO.md`).

If `minReplicas` isn't already ≥1, pin before the MAS campaign starts:

```bash
./azure-deployment/batch-scale.sh up 6   # for the 5-agent campaign
# After campaign:
./azure-deployment/batch-scale.sh down
```

---

## Handing off the result

Once deployed and verified:

1. **Update `AITOSOFT_CHANGES.md`** with a section documenting the new mode,
   the deploy tag, verification results, and any deviations from this spec.
2. **Move this file** to `tasks/done/static-html-fallback-mode-YYYY-MM-DD.md`
   (consistent with the pattern used for `leak-fixes-deploy-2026-04-14.md`).
3. **Tell Tero** (the human running this) that static mode is live, and
   share the deploy tag so MAS can pin its fallback logic against it.
4. **Write a brief reply note for the MAS-side Claude** describing the
   final API contract:
   - Exact location of the `render_mode` field (top level vs inside
     `crawler_config`) — this spec says top level; confirm you shipped it
     that way.
   - Exact string value MAS should send (`"static"`).
   - The error shape static-mode failures produce (HTTP 200 + inner
     `success: false`, not HTTP 504).
   - Any deviations from this spec.

   Put the note into the same archived file in `tasks/done/` so there's a
   single discoverable record.

---

## What MAS commits to do on its side (informational — not your work)

MAS's `scrape_page` tool wrapper will:
- Track 504s per host per session.
- After 2 consecutive 504s on any host, pivot that host to
  `render_mode: "static"` for the rest of the session.
- If static also fails, fall further back to their client-side
  `mode=links_only`.
- Never use `render_mode: "static"` as the default — `full` stays primary.

This keeps our side simple: we just need to offer the capability reliably.

---

## Pointers into the codebase (fast onboarding)

- `CLAUDE.md` — architecture overview, what's ours vs upstream.
- `AITOSOFT_CHANGES.md` — chronological change log; read the 2026-04-14
  entries for context on Fix 1/2/3/4.
- `deploy/docker/api.py:573` — `handle_crawl_request` function, the
  extension point for this task.
- `deploy/docker/api.py:678-736` — Fix 1 wrapper (`asyncio.wait_for` +
  504 response shape). Mirror this pattern for static-mode error handling.
- `deploy/docker/crawler_pool.py` — pool logic; static mode deliberately
  doesn't touch it.
- `deploy/docker/aitosoft_patchright_fallback.py` — the second-tier
  anti-bot retry; static mode bypasses this entirely.
- `crawl4ai/html2text/__init__.py` — vendored html2text, reuse for the
  markdown conversion.
- `test-aitosoft/test_regression.py` — Tier 1 regression harness.
- `test-aitosoft/test_soak.py` — soak test harness (memory drift + 504
  gates).
- `azure-deployment/batch-scale.sh` — minReplicas toggler.

---

## Open questions — decide and document as you go

- Do you keep `links` extraction in static mode, or drop it? Recommendation:
  drop it (empty arrays) unless a quick BeautifulSoup pass fits in the 2h
  budget. MAS doesn't depend on it for static.
- `httpx.AsyncClient` lifecycle: reuse a module-scope client if one already
  exists in `deploy/docker/`; otherwise create one lazy-init'd at first
  use and closed in the FastAPI lifespan shutdown. Don't create per-request.
- `html2text` encoding: wrap the conversion in try/except; on failure, still
  return `success: true` with the raw HTML as `raw_markdown` so MAS can fall
  back to its own parser.

---

## Done-definition

- [x] Code changes applied to `deploy/docker/api.py` and
      `deploy/docker/server.py` (also `schemas.py`; the `CrawlRequest`
      model lives there, not in `server.py` as the spec guessed).
- [x] `render_mode` field present in both static-mode and full-mode
      responses (not just static).
- [x] Tier 1 regression 4/4 PASS against the deployed new image
      (`static-mode` label, 2026-04-15 17:25 UTC).
- [x] roadscanners.com acceptance strings verified in live deployment —
      all four present, `@null` decoy gone, md=9654B, time=0.16s.
- [x] One other SPA site spot-checked for response-shape correctness
      (columbia-road.com timed out as expected with correct 200 +
      inner-success=false shape; caverna.fi succeeded with full envelope).
- [x] `AITOSOFT_CHANGES.md` updated with the new entry.
- [x] This task file moved to
      `tasks/done/static-html-fallback-mode-2026-04-15.md`.
- [x] Tero notified with the deploy tag (final commit message /
      end-of-session summary).
- [x] Reply note for MAS-side Claude appended (see below).

---

## Deploy record

- **Built:** 2026-04-15 17:07 UTC via `az acr build`, 8m34s, digest
  `sha256:7cf6e3419c581b967185c1c3279c92375cc67a4f45abcab223b1767c1bb9bc68`.
- **Image tag:** `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-static-mode`.
- **Revision:** `crawl4ai-service--0000011`, provisioned 2026-04-15 17:14 UTC,
  3 replicas healthy, 100% traffic.
- **Deploy command:** `az containerapp update --name crawl4ai-service
  --resource-group aitosoft-prod --image
  aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-static-mode`
  (MAS bearer token preserved — did NOT use `deploy-aitosoft-prod.sh --update-only`).
- **Commit:** `ab51d3c` on `main`.

### Deviations from spec

1. Schema field lives in `deploy/docker/schemas.py` (which `server.py`
   imports from), not directly in `server.py`. Spec said "grep for it;
   it's the `/crawl` endpoint's request body schema" — consistent with
   that hint.
2. Added a `_strip_hidden_decoys` BeautifulSoup pass **before**
   html2text because roadscanners.com uses an Odoo-style
   `<span class="oe_displaynone">null</span>` injected inline in every
   email. Without the strip, MAS would receive
   `annele.matintupa@nullroadscanners.com` and the spec's own acceptance
   check would fail. The stripped class list is conservative:
   `oe_displaynone`, `d-none`, `is-hidden`. Deliberately NOT stripping
   `sr-only` / `visually-hidden` because those legitimately hold
   accessibility content.
3. `/crawl/stream` now explicitly rejects `render_mode=static` with
   HTTP 400. Spec said "do not touch" that endpoint; this is a one-line
   guard that makes the contract loud instead of silent — protecting
   MAS from accidentally sending `{stream: true, render_mode: static}`
   and getting a Playwright-backed stream instead of the fast fallback.

### Post-launch follow-ups (none blocking)

- Add a static-mode tier to `test_regression.py` once MAS depends on the
  path in production (revisit after first campaign night).
- Add an `asyncio.Semaphore` cap inside `handle_static_crawl_request` if
  usage patterns shift to batched static calls against a single host.
- Revisit the hidden-class list if any site reports missing content.

---

## Reply note for MAS-side Claude

> **Static-mode fallback is LIVE on the Aitosoft crawl4ai service.**
> Deployed tag: `0.8.6-static-mode` (revision `crawl4ai-service--0000011`).
>
> **API contract:**
> - Endpoint: unchanged — `POST /crawl` at the same URL, same bearer auth.
> - New **top-level** (NOT nested inside `crawler_config`) optional field:
>   `render_mode`. Valid values: `"full"` (default, unchanged behavior)
>   or `"static"`. Pydantic validates; anything else returns HTTP 422.
> - When you send `"render_mode": "static"`:
>   - The browser pool is bypassed entirely. No Playwright. No patchright
>     fallback.
>   - Per-URL HTTP timeout is 15s (not the 180s Fix-1 fence).
>   - Response envelope is identical to full-mode. Each inner result
>     carries `"render_mode": "static"`. Full-mode responses now also
>     carry `"render_mode": "full"` on every result so you can tag
>     downstream confidence without branching on shape.
> - Error contract: static-mode failures return **HTTP 200** with
>   `inner.success=false`, `status_code=0`,
>   `error_message="static-fetch: timeout after 15s"` (or similar).
>   **Never HTTP 504** — 504 stays reserved for Fix-1's "we tried to
>   render and failed."
> - `/crawl/stream` rejects `render_mode=static` with HTTP 400. Static
>   is non-streaming by definition.
>
> **Verified against the deploy:**
> - Roadscanners `/contact/offices/` returns all four spec-required
>   strings (annele/virpi emails, both Finnish phone numbers) in 0.16s,
>   no `@null` decoy.
> - Tier 1 regression 4/4 passes on the default `"full"` path — the
>   leak-fix stack is intact.
> - Timeout path: columbia-road.com returns HTTP 200 + inner
>   `success:false` + `error_message:"static-fetch: timeout after 15s"`.
>
> **Your agreed client-side behavior:** after 2 consecutive 504s on a
> host in a session, pivot that host to `render_mode: "static"` for the
> rest of the session. Worst-case per-company cost is now 2 × 180s =
> 360s before blacklist. Static stays a fallback — `"full"` remains
> primary.
>
> Anything missing or surprising, ping via Tero.

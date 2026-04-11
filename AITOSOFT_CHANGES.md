# Aitosoft Changes Log

This file tracks all modifications made to the crawl4ai fork for Aitosoft's internal use.
Keeping this log helps when syncing with upstream updates.

---

## Current State

**Last Updated**: 2026-04-11

### Version
- **Local**: v0.8.6 (merged from upstream 2026-03-26) + stealth package (2026-04-11)
- **Production**: v0.8.6 + stealth (deployed 2026-04-11)
- **Docker Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-stealth`

### Production Deployment
- **Endpoint**: `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Location**: West Europe (co-located with MAS)
- **Resource Group**: `aitosoft-prod`
- **Authentication**: ✅ Enabled (simple Bearer token)
- **Status**: ✅ Running

### Environment
- **Host**: Windows 11 (Snapdragon X Elite, 32GB RAM)
- **Local Path**: `c:\src\crawl4ai-aitosoft` → `/workspaces/crawl4ai-aitosoft`
- **Dev Container**: Python 3.11 on Debian Bookworm
- **Key Tools**: Node.js 20, Azure CLI, GitHub CLI, Claude Code

### Tests
- 3/3 test-aitosoft/ tests passing

---

## Stealth Package (2026-04-11)

### What Changed
Full stealth overhaul of the Docker image and runtime browser configuration,
driven by MAS observing consistent HTTP 500s on 4 Cloudflare/AEM/WP.one-fronted
sites (baxter.fi, lundbeck.com/fi, pedelux.fi, rederiabeckero.ax) while the
same sites responded 200 to plain `curl`. Fingerprint diagnostic against bot
detection pages (sannysoft, areyouheadless, creepjs, browserleaks) confirmed
multiple fingerprint leaks: stale UA, no WebGL, wrong locale/timezone, missing
stealth patches.

### Files Modified (Upstream)

**`Dockerfile`** — added one RUN step to install real Google Chrome:
```
RUN playwright install chrome
```
Playwright's bundled Chromium has a distinct TLS/JA3 handshake that Cloudflare's
bot-management rulesets flag. Real Chrome matches ~65% of desktop web traffic
and is the cheapest single fingerprint fix. The `chrome-*` cache copy into
`appuser` home is conditional (falls back cleanly if Playwright bundles Chrome
system-wide via apt instead of cache-local).

**`deploy/docker/api.py`** — two 2-line edits in `handle_crawl_request` (line
~567) and `handle_stream_crawl_request` (line ~740). Both call the new
`merge_browser_config()` helper instead of `BrowserConfig.load()` directly.
Root cause: upstream `api.py` loaded the user's `browser_config` dict into a
BrowserConfig with class defaults, so config.yml.browser.kwargs only affected
the PERMANENT pool browser (which is never hit by real requests — its
signature differs from the all-defaults signature of a bare request). Our
stealth/channel/UA/viewport settings were dead code for API traffic until
this fix.

**`crawl4ai/browser_adapter.py`** — `StealthAdapter._check_stealth_availability`
and `apply_stealth` ported to the `playwright-stealth` 2.x class-based API
(`from playwright_stealth import Stealth; Stealth().apply_stealth_async(page)`).
Upstream v0.8.6 pins `playwright-stealth>=2.0.0` in pyproject.toml but still
imports the old 1.x names (`stealth_async` / `stealth_sync`), which no longer
exist. Imports failed silently and `apply_stealth` became a no-op — so
`enable_stealth=True` had zero effect, even when set correctly. Confirmed in
the v2 deploy where `navigator.webdriver` remained `false` and `chrome.runtime`
remained absent on sannysoft/creepjs. Worth filing a PR upstream.

**`crawl4ai/browser_manager.py`** — `BrowserManager._build_browser_args` (line
~1057) hardcoded `--disable-gpu`, `--disable-gpu-compositing`, and
`--disable-software-rasterizer` at the top of its arg list. The sibling
`ManagedBrowser.build_browser_flags` (line ~69) gates those same flags on
`if not config.enable_stealth:`. The two flag builders had drifted out of
sync. Moved the GPU flags into the same conditional block so stealth-enabled
crawls keep WebGL (via SwiftShader), which is one of the loudest anti-bot
signals Cloudflare scores against. Also worth a PR upstream.

**`deploy/docker/config.yml`** — browser kwargs overhaul:
```yaml
browser:
  kwargs:
    headless: true
    text_mode: false                 # was true — real browsers load images/fonts
    enable_stealth: true             # NEW — playwright-stealth patches
    channel: chrome                  # NEW — use installed real Chrome
    viewport_width: 1920             # NEW — was default 1080
    viewport_height: 1080            # NEW — was default 600
    user_agent: "Mozilla/5.0 (X11; Linux x86_64) ... Chrome/133.0.0.0 ..."
  extra_args:
    - "--no-sandbox"
    - "--disable-dev-shm-usage"
    - "--allow-insecure-localhost"
    - "--ignore-certificate-errors"
    # REMOVED: --disable-gpu, --disable-software-rasterizer (killed WebGL)
    # REMOVED: --disable-web-security (Cloudflare bot rules match on this)
```

### Files Modified (Aitosoft-only)

- `test-aitosoft/test_regression.py` — refreshed `TIER_1_SITES` list to match
  CLAUDE.md (caverna, accountor, solwers, jpond). Retired sites removed:
  talgraf (CF block), tilitoimistovahtivuori (404), monidor (restructure).
  Default config swapped from `fast` (magic=true) → `optimal` (matches MAS).
- `test-aitosoft/test_site.py` — `optimal` config now includes
  `remove_consent_popups: true`. `CRAWL4AI_URL` reads from `CRAWL4AI_API_URL`
  env var so tests can target localhost/staging.

### New Files

- `deploy/docker/aitosoft_browser_merge.py` — 50-line helper that merges
  config.yml browser kwargs under a user's request `browser_config`. Called
  from `api.py` at the two `BrowserConfig.load()` sites. Defensive: if the
  user sends a fully serialized BrowserConfig (`{type, params}` shape), the
  merge is skipped and the object is respected as-is.
- `test-aitosoft/test_fingerprint.py` — before/after fingerprint diagnostic.
  Hits sannysoft, areyouheadless, creepjs, browserleaks through crawl4ai's
  own `/crawl` API, runs a JS probe inside the page (navigator.webdriver,
  UA, platform, timezone, locale, plugins, cores, screen, viewport, WebGL
  vendor/renderer, chrome.runtime, canvasFp, audioContext), and saves the
  full HTML + screenshot + probe JSON + summary under `stealth-<label>/`.
- `test-aitosoft/stealth-baseline/` — fingerprint capture with OLD config
  (for before/after comparison). Key baseline signals:
  - `webdriver: false` (tells: real Chrome is `undefined`)
  - UA `Chrome/116.0.0.0` (2 years stale)
  - viewport `1080x600` (unusual, signals narrow bot)
  - `timezone: UTC, locale: en-US` (wrong for Finnish sites)
  - `webgl: no-webgl` (HUGE tell: `--disable-gpu` flag)
- `test-aitosoft/stealth-after/` — fingerprint capture with NEW config
  (post-deploy). See file for comparison.
- `test-aitosoft/reference/persona_generator.ts` — reference TypeScript for
  the MAS team. Deterministic persona (UA/viewport/Accept-Language/sec-ch-ua)
  from `master_company_id` via SHA-256(salt + id). Pool is Chromium-family
  only (Chrome + Edge) to match crawl4ai's engine. Weighted by EMEA desktop
  share. Rotatable via `PERSONA_SALT` constant.

### Rationale (the "why")

See the brainstorm dialogue between crawl4ai-Claude and aitosoft-platform-Claude
preceding this change (conversation thread in the Claude Code session).
Short version: every change moves the request one step closer to a real
browser visit. None of the changes add new behavior to sites that already
worked — they only REMOVE the hostile flags / outdated defaults / missing
stealth patches that were leaking automation signals to bot detectors.

### Per-Request Customization (for MAS)

Locale, timezone, and geolocation are already forwarded by crawl4ai via
`CrawlerRunConfig` → Playwright `new_context()` (see `browser_manager.py`
lines ~1351-1366). No code change was needed for those. MAS can send them
on every request under `crawler_config`:
```json
{
  "urls": ["https://example.fi"],
  "browser_config": {
    "user_agent": "<from persona>",
    "viewport_width": 1920,
    "viewport_height": 1080,
    "headers": {"Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8"}
  },
  "crawler_config": {
    "locale": "fi-FI",
    "timezone_id": "Europe/Helsinki",
    "wait_until": "domcontentloaded",
    "remove_consent_popups": true,
    "page_timeout": 90000,
    "max_retries": 2
  }
}
```

### Deployment

Built via `az acr build` (remote ACR build — no local Docker needed in the
devcontainer) and deployed via `az containerapp update --image ...`. Four
iterations landed as revisions `stealth-v1` → `stealth-v4`; each revealed
an additional layer of the same root cause (config.yml wasn't reaching the
request path, then the stealth library's API had changed, then a duplicate
flag list had drifted out of sync, then the webdriver patch was gated on a
condition that never fired, then platform and UA were mismatched). Final
deployed image: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-stealth-v4`.

### Results

**Fingerprint diagnostic — baseline vs v4:**

| Signal                  | Baseline                 | v4                                   |
|-------------------------|--------------------------|--------------------------------------|
| `navigator.webdriver`   | `false` (automation tell)| `undefined` (matches real Chrome)    |
| User-Agent              | Chrome 116 / X11 Linux   | Chrome 133 / Windows NT 10.0         |
| `navigator.platform`    | `Linux x86_64`           | `Win32` (matches UA)                 |
| Viewport                | 1080 × 600               | 1920 × 1080                          |
| WebGL vendor            | `no-webgl`               | `Intel Inc.`                         |
| WebGL renderer          | `no-webgl`               | `Intel Iris OpenGL Engine`           |
| `chrome.runtime`        | `false` (Chromium)       | `false` (matches real Chrome w/o ext)|

Full artifacts: `test-aitosoft/stealth-baseline/` vs `test-aitosoft/stealth-v4/`
(HTML + screenshots + probe JSON per target site).

**Tier 1 regression (Caverna, Accountor, Solwers, JPond):** 4/4 PASS. Report
at `test-aitosoft/reports/stealth-v4-regression-tier1.md`.

**Previously-blocked sites — still blocked, but with clear diagnostics:**

| Site                   | Baseline   | v4 Result                                                    |
|------------------------|------------|--------------------------------------------------------------|
| baxter.fi              | HTTP 500   | Blocked: "Access Denied on short page (HTTP 403, 6264 bytes)" (Akamai) |
| lundbeck.com/fi        | HTTP 500   | Blocked: "HTTP 403 with HTML content (923 bytes)" (WAF)     |
| pedelux.fi             | HTTP 500   | Blocked: "Cloudflare JS challenge" (never resolves)         |
| rederiabeckero.ax      | HTTP 500   | Blocked: "Structural: no <body> tag (15 bytes)" (proxy?)    |

v4 fingerprint work did NOT unblock these four. The nature of the blocks
(static 403 pages from Akamai/WAFs, a Cloudflare challenge that never
resolves, a 15-byte near-empty response) points at **IP-based or network-path
detection** rather than fingerprint detection. The Azure Container Apps
egress IP is almost certainly flagged by these specific gatekeepers — which
stealth improvements cannot fix.

**What v4 DID fix:** the fingerprint side of the equation for the ~380 sites
that already work. Those sites now get a request that's substantially harder
to flag as automation: real Chrome binary, current Chrome version, stealth
patches active, WebGL present, platform/UA matched, viewport realistic. This
is protective insurance against future fingerprint-based detections — a
site that passes today shouldn't start failing in 6–12 months because our
fingerprint got stale.

**Next steps for the blocked 4 (recommended, not in this change):**
1. **Residential proxy** via crawl4ai's `proxy_config` for the handful of
   sites confirmed to IP-block Azure. Add to CrawlerRunConfig per-site, not
   globally. Cost: ~€10–30/month for 4 sites × 1 request/month.
2. **Patchright (undetected-playwright) escalation** on retry. `patchright`
   is already in `pyproject.toml`. A 2-tier retry — normal stealth first,
   patchright fallback on block — would handle Cloudflare challenge sites
   without proxy costs.
3. **Accept the ~1% loss.** 4 blocked sites out of ~380 = 1.05%. If the
   business cost is low, it's cheaper to skip them than to chase them.

### Per-Request Customization (for MAS)

---

## Resource Scaling Fix (2026-04-04)

### What Changed
Investigation of 500s+ request latency incidents revealed severe resource starvation.
Azure logs showed requests waiting 8+ minutes in queue for CPU/memory, while actual crawls
completed in <10 seconds. Root cause: 1 CPU / 2 GiB running 40 concurrent Playwright pages.

### Config Changes
- `deploy/docker/config.yml`: `max_pages` 40→5, `memory_threshold_percent` 95→85%
- `azure-deployment/deploy-aitosoft-prod.sh`: Updated defaults to 2 CPU / 4 GiB / 20 replicas

### Azure Changes (Applied Live)
| Setting | Before | After |
|---------|--------|-------|
| CPU | 1.0 | 2.0 |
| Memory | 2.0 GiB | 4.0 GiB |
| minReplicas | 0 | 0 |
| maxReplicas | 3 | 20 |
| max_pages (per replica) | 40 | 5 |
| memory_threshold | 95% | 85% |

### Strategy
Horizontal scaling: fewer pages per replica, more replicas. Each replica gets its own
Chromium process with dedicated CPU. Azure Container Apps scales replicas based on HTTP
traffic and scales to zero when idle (zero cost).

### Evidence (from Azure Log Analytics)
- tassufoods.fi: 524s total latency, but FETCH log shows 9.51s actual crawl time
- 8+ minutes spent waiting with pool health checks showing 85% memory, no FETCH activity
- Memory spiking to 100% intermittently during concurrent page processing

---

## v0.8.6 Upgrade (2026-03-26)

### What Changed
Merged 197 upstream commits covering v0.8.0 → v0.8.5 → v0.8.6.

### Security Fixes (Critical)
- **litellm supply chain compromise**: Replaced `litellm` with `unclecode-litellm==1.81.13` (PyPI supply chain attack)
- **Redis CVE-2025-49844 (CVSS 10.0)**: Upgraded Redis to 7.2.7
- **Pod deadlock fix**: Removed shared LOCK contention in monitor

### New Anti-Blocking Features (v0.8.5)
- **`remove_consent_popups=True`**: CMP-aware cookie consent removal (OneTrust, Cookiebot, Didomi)
  - Tested on accountor.com: 7811 tokens without needing `magic=True` (was 32 tokens before)
- **3-tier anti-bot retry + proxy escalation**: `max_retries=N` with proxy list auto-escalation
- **`flatten_shadow_dom=True`**: Flattens Web Components into readable DOM
- **`fallback_fetch_function`**: Custom async fallback when all retries fail

### Bug Fixes
- `scan_full_page` hang fix (prevents infinite-scroll pages from hanging)
- `is_blocked()` re-check on fallback fetch failure
- BM25ContentFilter deduplication fix
- Screenshot distortion fix
- MCP SSE endpoint crash fix on Starlette >=0.50

### Dependency Changes
- `litellm` → `unclecode-litellm==1.81.13` (security)
- `tf-playwright-stealth` → `playwright-stealth>=2.0.0`

### Merge Conflicts Resolved
- `deploy/docker/server.py` — Kept our auth middleware, took upstream's `get_crawler` top-level import + `crawler = None` cleanup pattern
- `deploy/docker/config.yml` — Kept `enabled: true`, added upstream's `api_token` field
- `crawl4ai/__version__.py` — Took upstream v0.8.6
- `Dockerfile`, `README.md`, `SECURITY.md`, `deploy/docker/README.md`, `docs/md_v2/blog/index.md` — Took upstream versions

### Regression Test Results (v0.8.6)
| Site | Config | Result | Tokens |
|------|--------|--------|--------|
| monidor.fi | baseline | 404 (site restructured) | - |
| caverna.fi | baseline | PASS | 5833 |
| accountor.com | `remove_consent_popups=True` | PASS | 7811 |
| solwers.com | baseline | PASS | 12441 |

### Recommended Config Updates for MAS
```python
# Default config (replaces "fast" config)
CrawlerRunConfig(
    remove_consent_popups=True,
    remove_overlay_elements=True,
)

# Heavy config (replaces magic=True workaround)
CrawlerRunConfig(
    remove_consent_popups=True,
    remove_overlay_elements=True,
    scan_full_page=True,
    max_retries=2,
)
```

---

## v0.8.0 Upgrade Notes

### Security Fixes (Critical)
- **RCE Fix**: Removed `__import__` from hook allowed builtins
- **LFI Fix**: Added URL scheme validation, blocked file://, javascript:, data: URLs

### Breaking Changes (No Impact on Aitosoft)
- Hooks disabled by default (we don't use hooks)
- file:// URLs blocked in Docker API (we only use http/https)

### Dependency Changes
- Python requirement: 3.9 → 3.10 (we use 3.11)
- New: `patchright>=1.49.0` (stealth browser)
- **REMOVED from core**: `sentence-transformers` (now optional, saves ~500MB)

---

## Change Log

### 2026-01-20: Production Deployment to West Europe

**Purpose:** Deploy to production using existing aitosoft-prod infrastructure

**Deployment Details:**
- **Location**: West Europe (co-located with MAS)
- **Resource Group**: `aitosoft-prod` (reusing existing resources)
- **Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.0-secure`
- **Endpoint**: `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Authentication**: ✅ Enabled and tested
- **Cost**: ~€30-50/month (only container app cost)

**Files Created:**
- `azure-deployment/deploy-aitosoft-prod.sh` - Production deployment script
- `DEPLOYMENT_INFO.md` - Current production info, credentials, usage examples

**Infrastructure Used:**
- `aitosoftacr` - Existing ACR (now has crawl4ai-service repository)
- `aitosoft-aca` - Existing Container Apps environment
- `workspace-aitosoftprodnCsc` - Existing Log Analytics

**Benefits:**
- Cost efficient (reuses existing infrastructure)
- Same region as MAS (lower latency)
- Simple token auth working correctly

---

### 2026-01-20: Add Simple Token Authentication

**Purpose:** Add simple Bearer token authentication for production security

**Files Modified:**
- `deploy/docker/server.py` - Added SimpleTokenAuthMiddleware to security setup (3 lines)
- `deploy/docker/config.yml` - Enabled security: true
- `azure-deployment/production-config.yml` - Enabled security, disabled JWT

**Files Created:**
- `deploy/docker/simple_token_auth.py` - Middleware for static token authentication (39 lines)
- `azure-deployment/SIMPLE_AUTH_DEPLOY.md` - Auth implementation guide

**How it works:**
- Uses `CRAWL4AI_API_TOKEN` environment variable as the auth token
- Requires `Authorization: Bearer <token>` header on all requests (except /health, /docs)
- Bypasses auth if `CRAWL4AI_API_TOKEN` is not set (development mode)
- Total modification: 42 lines of code added to upstream

**Why:** Upstream crawl4ai only provides JWT auth where anyone can get a token by calling `/token` with any email. This is unsuitable for preventing unauthorized access. Our simple token auth provides real security with one static secret token.

---

### 2026-01-19: Repository Cleanup

**Purpose:** Consolidate documentation and clean up repo structure

**Files Deleted:**
- `DEVELOPMENT_NOTES.md` - Merged into this file
- `message-to-claude.md` - Redundant with CLAUDE.md
- `.github/workflows/test-release.yml.disabled` - Dead code
- `.github/workflows/release.yml.backup` - In git history

**Files Moved:**
- `test_llm_webhook_feature.py` → `test-aitosoft/`
- `test_webhook_implementation.py` → `test-aitosoft/`

**Files Updated:**
- `CLAUDE.md` - Removed reference to deleted message-to-claude.md

---

### 2026-01-19: Repository Cleanup and Test Fixes

**Purpose:** Clean up development notes and fix async test support

**Files Modified:**
- `DEVELOPMENT_NOTES.md` - Cleaned up, removed outdated sections
- `test-aitosoft/test_fit_markdown.py` - Added `@pytest.mark.asyncio` decorator

**Dependencies Added:**
- `pytest-asyncio` - Required for running async tests with pytest

---

### 2026-01-19: Initial Repository Setup

**Purpose:** Configure development environment for Aitosoft team

**Files Modified:**
- `.devcontainer/devcontainer.json` - Refactored to use setup.sh, added GitHub CLI feature
- `.gitignore` - Added exception for `.devcontainer/setup.sh`

**Files Created:**
- `.devcontainer/setup.sh` - Extracted setup logic into maintainable script
- `CLAUDE.md` - Project guidance for Claude
- `AITOSOFT_CHANGES.md` - This file (change tracking)

**Files Updated (local only, git-ignored):**
- `.claude/settings.local.json` - Configured broader permissions for Claude Code
- `.env.local` - Fresh API token for local development

---

## Inherited from Previous Work (July 2025)

These files were created in the original Aitosoft fork:

| File/Directory | Purpose | Status |
|----------------|---------|--------|
| `test-aitosoft/` | Aitosoft-specific tests (separate from upstream) | Working |
| `azure-deployment/` | Azure Container Apps deployment guides | Needs review |
| `run_validation_tests.py` | Test orchestration script | Working |
| `.github/workflows/` | CI/CD pipelines | Working |

---

## Upstream Sync Notes

When merging upstream updates:
1. Check if `.devcontainer/devcontainer.json` has upstream changes
2. Our `setup.sh` approach may need reconciliation with upstream's inline commands
3. Review any changes to `deploy/docker/` which we depend on
4. Test that `test-aitosoft/` tests still pass after merge

---

## Planned Changes

- [ ] Deploy v0.8.0 to Azure production
- [ ] Verify production health check + auth
- [ ] Connect to multi-agent platform

---

## Quick Reference

### Start Local Server
```bash
uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235
```

### Test Endpoints
```bash
# Health check
curl http://localhost:11235/health

# Crawl request
curl -X POST http://localhost:11235/crawl \
  -H "Content-Type: application/json" \
  -d '{"urls": "https://example.com", "priority": 10}'
```

### Run Tests
```bash
pytest test-aitosoft/                    # Aitosoft-specific tests
pytest -xvs test-aitosoft/test_fit_markdown.py  # Single test
```

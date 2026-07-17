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
Each task file has: goal, status, plan, progress, learnings. Start each session by
checking `ls tasks/` for open work.

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
pytest test-aitosoft/test_mas_contract.py test-aitosoft/test_admission.py test-aitosoft/test_static_mode.py test-aitosoft/test_crawler_pool.py test-aitosoft/test_patchright_fallback.py  # OFFLINE suites (no server needed)
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
| Per-replica render capacity is 2 (2 vCPU) | Benchmarked 2026-07-17; >2 concurrent renders degrade all requests. Enforced by RenderGate + ACA scale rule |

---

## Key Principles

1. **Minimal upstream changes** — keep modifications isolated, document in `AITOSOFT_CHANGES.md`
2. **Security first** — no secrets in code, use env vars (see Security section below)
3. **`[aitosoft]` commit prefix** — all our commits
4. **Test before deploy** — Tier 1 regression must pass

---

## Security

**PUBLIC REPOSITORY. NEVER COMMIT SECRETS.**

- Tokens go in `.env` (gitignored) or Azure Key Vault, never in code/docs
- Always use `os.getenv("CRAWL4AI_API_TOKEN")` in code
- If a token is leaked: rotate immediately via `az containerapp update --set-env-vars`, update `.env`, notify MAS team

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
| `deploy/docker/api.py` | +132/−10: static-mode short-circuit, patchright retry inside wall-clock deadline, `render_mode` tagging, render-admission gate (429 when replica full; fence starts after admission), single-URL guard (multi-URL → 400), fence-504 warning ("WALL-CLOCK FENCE 504" w/ URL + elapsed + gate snapshot) |
| `deploy/docker/server.py` | static branch in `/crawl`; lifespan closes static client + patchright singleton |
| `deploy/docker/schemas.py` | `CrawlRequest.render_mode` field |
| `deploy/docker/crawler_pool.py` | MAX_PAGES enforcement + overflow keys; BUSY_SINCE stuck-slot janitor (file unchanged upstream since 0.8.6) |
| `deploy/docker/config.yml` | Deployment config: stealth kwargs, `wall_clock_s: 180`, pool limits, render admission (`render_capacity: 2` — MUST match ACA scale rule) |
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

### 100% Aitosoft Code (safe to modify freely)
- `tasks/` — task tracking
- `test-aitosoft/` — test suite, fingerprint diagnostics, persona reference
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

**Always read at session start:** This file (auto-loaded) + `ls tasks/` for open work.

**Read when needed:**
| Doc | When |
|-----|------|
| `AITOSOFT_CHANGES.md` | Understanding what we changed and why (authoritative change log) |
| `AITOSOFT_FILES.md` | Quick inventory of our files vs upstream |
| `DEPLOYMENT_INFO.md` | Endpoint, credentials, Azure resource details |
| `TESTING.md` | Full testing framework, quality gates |
| `TEST_SITES_REGISTRY.md` | Test site metadata, expected contacts, patterns |
| `OVERNIGHT_PLAYBOOK.md` | Tero says "monitor overnight" — read this, then loop via `ScheduleWakeup` |

---

## Azure Deployment

- **Endpoint:** `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Image:** `aitosoftacr.azurecr.io/crawl4ai-service:0.9.2-pool-cleanup`
- **Resources:** 2 vCPU / 4 GiB per replica, 0-30 replicas (scales to zero; explicit `http-renders` scale rule at 2 concurrent/replica — MUST match `render_capacity` in config.yml)
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

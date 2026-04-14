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

# Testing
pytest test-aitosoft/               # Aitosoft-specific tests
python test-aitosoft/test_regression.py --tier 1 --version <label>  # Tier 1 regression
python test-aitosoft/test_site.py <domain> --page <path>            # Single site
python test-aitosoft/test_fingerprint.py --label <label>            # Stealth diagnostic
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
- **Config merging:** `aitosoft_browser_merge.py` merges `config.yml` browser kwargs
  into every request so stealth/UA/viewport apply even when the client sends no
  `browser_config`. Without this, config.yml only affected the PERMANENT pool browser.

### Per-Request Customization (for MAS)
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
- Before every commit: `grep -r "crawl4ai-[a-z0-9]" --exclude-dir=.git --exclude=".env" .` must return empty
- If a token is leaked: rotate immediately via `az containerapp update --set-env-vars`, update `.env`, notify MAS team

---

## What's Ours vs Upstream

### Integration Architecture (wrapper entry point)
We use a **wrapper entry point** (`aitosoft_entry.py`) that imports and extends
upstream's `server.py` without modifying it. This keeps merges clean.

```
gunicorn → aitosoft_entry:app
             ├─ BrowserConfig.set_defaults(**config.yml)  # config.yml defaults for all requests
             ├─ from server import app                     # upstream, unmodified
             └─ app.add_middleware(SimpleTokenAuthMiddleware)  # our auth
```

### Aitosoft Modifications (changes to upstream files)
| File | What changed |
|------|-------------|
| `Dockerfile` | Added `RUN playwright install chrome` for real Chrome binary |
| `crawl4ai/browser_adapter.py` | Ported StealthAdapter to playwright-stealth 2.x API (PR upstream pending) |
| `crawl4ai/browser_manager.py` | Gated `--disable-gpu` flags on `enable_stealth` (PR upstream pending) |
| `deploy/docker/api.py` | 4 lines: patchright retry after first-tier crawl |
| `deploy/docker/config.yml` | Stealth config: enable_stealth, chrome_channel, UA, viewport |
| `deploy/docker/supervisord.conf` | Entry point: `aitosoft_entry:app` instead of `server:app` |
| `.pre-commit-config.yaml` | Excluded upstream files from ruff + mypy (pre-existing issues) |

**NOT modified** (moved to wrapper): `server.py` (auth), `api.py` (config merge)

### New Aitosoft Files (in upstream directories)
| File | Purpose |
|------|---------|
| `deploy/docker/aitosoft_entry.py` | Wrapper entry point: sets BrowserConfig defaults + auth middleware |
| `deploy/docker/simple_token_auth.py` | Bearer token auth middleware (39 lines) |
| `deploy/docker/aitosoft_patchright_fallback.py` | Second-tier retry via patchright for blocked crawls |

### 100% Aitosoft Code (safe to modify freely)
- `tasks/` — task tracking
- `test-aitosoft/` — test suite, fingerprint diagnostics, persona reference
- `azure-deployment/` — deployment scripts and docs
- `.devcontainer/` — dev container setup
- `CLAUDE.md`, `AITOSOFT_CHANGES.md`, `AITOSOFT_FILES.md`, `DEPLOYMENT_INFO.md`

### Upstream sync
- **Last synced:** upstream/develop (2026-04-14), includes v0.8.6 + security hardening
- **Sync procedure:** `git fetch upstream && git merge upstream/develop` — should be near-conflict-free now
- **Key technique:** `BrowserConfig.set_defaults()` (upstream's `@_with_defaults` in `async_configs.py`) applies config.yml defaults to every request without patching `api.py`

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

---

## Azure Deployment

- **Endpoint:** `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Image:** `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-security-v2`
- **Resources:** 2 vCPU / 4 GiB per replica, 0-20 replicas (scales to zero)
- **Auth:** Bearer token via `CRAWL4AI_API_TOKEN` env var
- See `DEPLOYMENT_INFO.md` for full details

**Deploy flow:**
```bash
az acr build --registry aitosoftacr --image crawl4ai-service:<tag> --file Dockerfile .
az containerapp update --name crawl4ai-service --resource-group aitosoft-prod --image aitosoftacr.azurecr.io/crawl4ai-service:<tag>
```
Note: `deploy-aitosoft-prod.sh` regenerates the API token on every run — use the
manual `az` commands above to swap the image without breaking MAS's token.

---

## Cross-Repo Communication

This repo works alongside `aitosoft-platform` (main multi-agent system). Both have
Claude as developer. To exchange information between repos, ask the business owner
to relay messages. Use for: API contracts, deployment coordination, debugging shared issues.

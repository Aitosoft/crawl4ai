# Aitosoft Changes Log

This file tracks all modifications made to the crawl4ai fork for Aitosoft's internal use.
Keeping this log helps when syncing with upstream updates.

---

## Current State

**Last Updated**: 2026-03-26

### Version
- **Local**: v0.8.6 (merged from upstream 2026-03-26)
- **Production**: v0.8.0-secure (deployed to West Europe) — **NEEDS REDEPLOY**
- **Docker Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.0-secure` — **NEEDS REBUILD**

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

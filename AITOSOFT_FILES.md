# Aitosoft Files Reference

Quick reference for what's ours vs upstream. **Read this before making changes.**

---

## Integration Architecture

We use a **wrapper entry point** pattern. Gunicorn loads `aitosoft_entry:app`
instead of `server:app`. The wrapper imports upstream's app unmodified, then
adds our auth middleware and sets `BrowserConfig` defaults from config.yml.

```
gunicorn → aitosoft_entry:app
             ├─ BrowserConfig.set_defaults(**config.yml)
             ├─ from server import app  (upstream, unmodified)
             └─ app.add_middleware(SimpleTokenAuthMiddleware)
```

---

## 100% Aitosoft Code (Safe to Modify)

### Documentation
- `CLAUDE.md` - Claude Code guidance (entry point for new sessions)
- `AITOSOFT_CHANGES.md` - Change tracking and current state
- `DEPLOYMENT_INFO.md` - Production deployment info (endpoint, token, examples)
- `AITOSOFT_FILES.md` - This file

### Wrapper + Aitosoft Modules (in deploy/docker/)
- `aitosoft_entry.py` - Wrapper entry point (sets defaults, adds auth)
- `simple_token_auth.py` - Bearer token auth middleware (39 lines)
- `aitosoft_patchright_fallback.py` - Second-tier retry via patchright for blocked crawls

### Deployment
- `azure-deployment/deploy-aitosoft-prod.sh` - Production deployment script
- `azure-deployment/*.py` - Test and helper scripts
- `azure-deployment/*.md` - Deployment guides

### Testing
- `test-aitosoft/` - All files (our test suite)

### Development Environment
- `.devcontainer/` - All files (our dev container setup)
- `tasks/` - Task tracking

---

## Modified Upstream Files

### deploy/docker/api.py
**Lines modified**: 4 lines (patchright retry after first-tier crawl)
**Why**: Retry blocked results through patchright/undetected-chromium
**Upstream sync**: Lines are in result-processing section, separate from most upstream changes

### deploy/docker/config.yml
**What changed**: Browser kwargs (stealth, chrome channel, UA, viewport), security enabled
**Why**: Production stealth configuration
**Upstream sync**: Deployment config, always ours

### deploy/docker/supervisord.conf
**Lines modified**: 1 word (`server:app` → `aitosoft_entry:app`)
**Why**: Load our wrapper instead of upstream's server directly

### crawl4ai/browser_adapter.py
**What changed**: Ported StealthAdapter to playwright-stealth 2.x API
**Why**: Upstream bug — pins 2.x in pyproject.toml but imports 1.x names
**Upstream sync**: PR upstream when ready, then delta drops to 0

### crawl4ai/browser_manager.py
**What changed**: Gated `--disable-gpu` flags on `enable_stealth` in `_build_browser_args`
**Why**: Upstream bug — GPU flags kill WebGL, a major anti-bot signal
**Upstream sync**: PR upstream when ready, then delta drops to 0

### Dockerfile
**Lines modified**: 1 line added (`RUN playwright install chrome`)
**Why**: Install real Chrome binary (vs bundled Chromium with distinct TLS fingerprint)

### .pre-commit-config.yaml
**What changed**: Exclude patterns for ruff/mypy (upstream files with pre-existing issues)

---

## NOT Modified (moved to wrapper in 2026-04-14 restructure)

- `deploy/docker/server.py` — was 3 lines for auth, now 0 (auth in wrapper)
- `deploy/docker/api.py` — was ~12 lines for config merge, now 4 (merge replaced by `set_defaults()`)

---

## When Syncing with Upstream

```bash
git fetch upstream
git merge upstream/develop
```

Expected: **near-zero conflicts** since server.py is unmodified and api.py
has only 4 lines in a result-processing section.

If conflicts occur, check:
1. `api.py` patchright retry lines (~line 670)
2. `browser_adapter.py` stealth 2.x port
3. `browser_manager.py` GPU flag gating

---

## Summary

**Upstream file modifications**: 4 lines in api.py + 1 word in supervisord.conf + stealth bugfixes
**Aitosoft-only files**: `aitosoft_entry.py`, `simple_token_auth.py`, `aitosoft_patchright_fallback.py`
**All other work**: `azure-deployment/`, `test-aitosoft/`, `.devcontainer/`, `tasks/`

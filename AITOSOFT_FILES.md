# Aitosoft Files Reference

Quick reference for what's ours vs upstream. **Read this before making changes.**
Current as of the v0.9.2 upgrade (2026-07-16).

---

## Integration Architecture

We use a **wrapper entry point** pattern. Gunicorn loads `aitosoft_entry:app`
instead of `server:app`. The wrapper sets `BrowserConfig` class defaults from
config.yml, relaxes two untrusted-boundary rules for our single trusted client
(MAS), then imports upstream's app.

```
gunicorn → aitosoft_entry:app
             ├─ BrowserConfig.set_defaults(**config.yml)
             ├─ untrusted-boundary relaxations (headers allowed, timeout cap 180s)
             └─ from server import app  (upstream; AuthGateMiddleware included)
```

Auth is upstream's `AuthGateMiddleware` (v0.9.0+): `Authorization: Bearer
$CRAWL4AI_API_TOKEN`, constant-time, fail-closed. Our old
`simple_token_auth.py` was deleted in the v0.9.2 upgrade.

---

## 100% Aitosoft Code (Safe to Modify)

### Documentation
- `CLAUDE.md` - Claude Code guidance (entry point for new sessions)
- `AITOSOFT_CHANGES.md` - Change tracking and current state (authoritative log)
- `DEPLOYMENT_INFO.md` - Production deployment info (endpoint, token, examples)
- `AITOSOFT_FILES.md` - This file
- `TESTING.md`, `TEST_SITES_REGISTRY.md`, `OVERNIGHT_PLAYBOOK.md`

### Wrapper + Aitosoft Modules (in deploy/docker/)
- `aitosoft_entry.py` - Wrapper entry point (applies defaults + relaxations, imports app)
- `aitosoft_trust.py` - Trusted-client relaxations of the untrusted-config boundary
  (importable without the server — used by test_mas_contract.py)
- `aitosoft_static_mode.py` - `render_mode: "static"` implementation (httpx + html2text)
- `aitosoft_patchright_fallback.py` - Second-tier retry via patchright for blocked crawls

### Deployment
- `azure-deployment/` - Deploy scripts, batch-scale.sh, alert setup, guides

### Testing
- `test-aitosoft/` - All files (our test suite)

### Development Environment
- `.devcontainer/` - All files (our dev container setup)
- `tasks/` - Task tracking
- `.pre-commit-config.yaml` - Ours. Hooks are scoped to Aitosoft files ONLY
  (top-level `files:` pattern). NEVER widen it to upstream code — formatter
  drift on upstream files poisons every merge.

---

## Modified Upstream Files

### deploy/docker/api.py (~25 lines)
`render_mode` param + static-mode short-circuit (after SSRF validation);
patchright retry wrapped inside upstream's wall-clock deadline;
`render_mode: "full"` tagging of results.

### deploy/docker/server.py (~30 lines)
Static branch in `/crawl` (before stream check and all-failures→500 rewrite);
lifespan shutdown closes static httpx client + patchright singleton.

### deploy/docker/schemas.py (~15 lines)
`CrawlRequest.render_mode: Literal["full","static"] = "full"`.

### deploy/docker/crawler_pool.py (~300 lines)
MAX_PAGES enforcement + overflow browser keys; BUSY_SINCE stuck-slot
force-close in janitor. File is unchanged upstream since 0.8.6, so this
carries no merge risk.

### deploy/docker/config.yml
Deployment config (always ours): stealth browser kwargs, real-Chrome channel,
`limits.wall_clock_s: 180`, `pool.max_pages: 5`, `stuck_busy_timeout_sec: 600`,
`memory_threshold_percent: 85`.

### deploy/docker/supervisord.conf
1 word: gunicorn target `aitosoft_entry:app`.

### crawl4ai/browser_manager.py (~10 lines)
`_build_browser_args`: GPU flags gated on `enable_stealth` (keeps WebGL in
stealth mode). Still broken upstream — PR-worthy.

### Dockerfile (~10 lines)
`RUN playwright install chrome` + copy `chrome-*` cache to appuser home.

---

## Dropped in v0.9.2 upgrade (upstream superseded)

- `crawl4ai/browser_adapter.py` stealth 2.x port → upstream fixed (#1960)
- api.py 180s `asyncio.wait_for` patch → upstream `limits.wall_clock_s`
- `simple_token_auth.py` (deleted) → upstream `AuthGateMiddleware`

---

## When Syncing with Upstream

```bash
git fetch upstream
git merge upstream/develop
```

Expected: near-zero conflicts. If conflicts occur, check the files listed
above; `git diff upstream/develop HEAD -- crawl4ai/ deploy/ Dockerfile`
should show ONLY the modifications documented here. If it shows more,
someone reformatted upstream files — fix that before merging anything.

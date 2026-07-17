# Upgrade to upstream v0.9.2

**Status:** Done (2026-07-17)
**Priority:** High — crawler is 117 commits / 5 releases behind upstream
**Owner:** Claude (lead developer), commissioned by Tero

## Goal

Bring the fork from v0.8.6 (last sync 2026-04-14) to upstream v0.9.2
(`upstream/develop` == `v0.9.2` tag as of 2026-07-16), preserving all
Aitosoft behavior, then simplify/harden where clearly beneficial.
Deploy to Azure production after Tier 1 regression passes.

## Key discovery (affects merge strategy)

Commit `055d4ce` ("Normalize upstream whitespace / EOF / formatter drift")
ran a formatter across ~90 upstream files. The apparent 11.5k-line delta vs
merge-base is ~97% formatter noise. **Real** Aitosoft changes to
upstream-tracked files are only:

| File | Real change |
|------|-------------|
| `deploy/docker/api.py` | patchright retry hook, 180s `asyncio.wait_for` + 504, static-mode short-circuit + `render_mode` tagging |
| `deploy/docker/server.py` | static-mode branch in `/crawl`, lifespan closes static httpx client |
| `deploy/docker/schemas.py` | `CrawlRequest.render_mode: Literal["full","static"]` |
| `deploy/docker/crawler_pool.py` | MAX_PAGES enforcement + overflow keys, BUSY_SINCE stuck-slot janitor |
| `deploy/docker/config.yml` | stealth browser kwargs (deployment config) |
| `deploy/docker/supervisord.conf` | gunicorn entry `aitosoft_entry:app` |
| `crawl4ai/browser_adapter.py` | playwright-stealth 2.x API port |
| `crawl4ai/browser_manager.py` | GPU flags gated on enable_stealth |
| `Dockerfile` | `RUN playwright install chrome` |
| `.pre-commit-config.yaml` | exclude upstream files from hooks |

Aitosoft-only files (no upstream counterpart): `deploy/docker/aitosoft_entry.py`,
`simple_token_auth.py`, `aitosoft_patchright_fallback.py`, `tasks/`,
`test-aitosoft/`, `azure-deployment/`, top-level AITOSOFT_* docs, `.devcontainer/`.

## Plan

1. ✅ Inventory real patches vs formatter noise (per-file diffs in scratchpad)
2. ⏳ Research upstream 0.8.6→0.9.2 changes (agents): docker layer + core + changelog
3. Merge `upstream/develop` on branch `upgrade/v0.9.2`:
   - resolution policy: take upstream wholesale everywhere (washes out
     formatter noise → future merges stay clean), keep Aitosoft-only files
   - re-apply the real patches above, adapted to 0.9.2 code; DROP any patch
     upstream has fixed itself
4. `pip install -e .`, run server locally, verify: health, auth wrapper,
   static mode, config.yml defaults reaching requests
5. Tier 1 regression against local server (site-safety rules apply)
6. Update docs: AITOSOFT_CHANGES.md, CLAUDE.md, AITOSOFT_FILES.md
7. Build image via `az acr build`, deploy with manual `az containerapp update`
   (preserve MAS token), verify prod health + Tier 1 against prod
8. Improvements along the way (candidates, evaluate after merge):
   - prevent future formatter drift (pre-commit excludes for upstream files)
   - delete junk upstream files if gone upstream (`adaptive_crawler copy.py`,
     `async_crawler_strategy.back.py`)
   - doc-cleanup task items where they intersect

## Progress

- 2026-07-16: Project started. Distance measured: 117 commits behind,
  upstream/develop == v0.9.2. Formatter-noise discovery documented above.
  Research agents dispatched.
- 2026-07-16: Merge complete on `upgrade/v0.9.2`. Upstream tree taken
  wholesale; real patches re-applied (see AITOSOFT_CHANGES.md v0.9.2 entry).
  Dropped: browser_adapter stealth port (upstream #1960), api.py timeout
  patch (→ `limits.wall_clock_s: 180`), simple_token_auth.py (→ upstream
  AuthGateMiddleware). New: aitosoft_static_mode.py module,
  trusted-client boundary relaxations in aitosoft_entry.py, pre-commit
  scoped to Aitosoft files.
- 2026-07-16: Local verification PASSED: server boots, auth 401/401/200,
  MAS-shaped full crawl OK (headers + 90s timeout accepted), static mode OK,
  Tier 1 regression 4/4 (reports/v0.9.2-local2-regression-tier1.md).
- 2026-07-16: Boundary made tolerant (falsy forbidden fields dropped;
  magic/simulate_user/override_navigator allowed for trusted client).
- 2026-07-16: Doc cleanup completed alongside (TESTING.md rewritten,
  registry fixed, 5 obsolete docs deleted).
- 2026-07-16 ~12:23 UTC: **DEPLOYED** — image `crawl4ai-service:0.9.2`,
  revision `crawl4ai-service--0000025`, deployed during a scaled-to-zero
  window. Prod smoke: health 0.9.2 / auth 401 / MAS-shaped crawl / static
  mode / js_code-400 / caverna.fi spot check — all PASS.

## Remaining

- [x] MAS compat confirmation received 2026-07-16: full field audit, test
  batch on v0.9.2 all green ("no breakage found; next WAA batch clear").
  Their open question — is `prefetch: true` explicitly allowed? — answered:
  YES, it's in UPSTREAM's own UNTRUSTED_FIELD_ALLOWLIST (async_configs.py
  "misc safe knobs" line, alongside stream/method), not slipping through
  and not even dependent on our relaxations. remove_overlay_elements and
  process_iframes are also upstream-allowed (not dropped).
- [x] MAS's exact field enumeration pinned as an offline regression test:
  `test-aitosoft/test_mas_contract.py` (7 tests). Relaxations refactored
  into `aitosoft_trust.py` so the test imports them without the server.
  (The refactor shipped in the `0.9.2-render-gate` image on 2026-07-17.)
- [x] Closed 2026-07-17: prod moved to `0.9.2-render-gate` before the first
  WAA batch ran, so "watch the first batch" is now tracked by the successor
  task `capacity-scaling-redesign.md` (its open watch-batch item).

## Learnings

- `git diff -w --stat` + per-file `git log` is the fast way to separate
  formatter noise from real fork changes.

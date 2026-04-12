# Documentation Cleanup

**Status:** Open
**Priority:** Medium — prevents future Claude sessions from working off stale info
**Blocked by:** Nothing

## Goal

Consolidate and update documentation. Current state: 13 files, heavy
redundancy, 5 are obsolete, 4 are stale. Only AITOSOFT_CHANGES.md is
fully accurate. All docs are written by Claude for future Claude sessions.

## Plan

### Delete (content absorbed into other docs or fully obsolete)
- `azure-deployment/DEPLOYMENT_GUIDE.md` — old North Europe infra
- `azure-deployment/V0.8.0_UPGRADE_SUMMARY.md` — v0.8.0 upgrade notes
- `test-aitosoft/TESTING_RESULTS.md` — talgraf.fi reliability study (site blocked)
- `test-aitosoft/README.md` — stub with broken link
- `test-aitosoft/TESTING_GUIDE.md` — pre-stealth config guide, superseded

### Update CLAUDE.md
- Add 5 files to "Aitosoft Modifications": Dockerfile, browser_adapter.py,
  browser_manager.py, aitosoft_browser_merge.py, aitosoft_patchright_fallback.py
- Move api.py from "100% Upstream" to "Aitosoft Modifications"
- Fix Tier 1 list: add caverna.fi, note all 4 current sites
- Add tasks/ to "100% Aitosoft Code" section

### Update AITOSOFT_FILES.md
- Same inventory additions as CLAUDE.md
- Update line count from "42" to ~150+

### Update DEPLOYMENT_INFO.md
- Image tag `:0.8.6` → `:0.8.6-stealth-v5` (3 places)

### Update TEST_SITES_REGISTRY.md
- Rewrite Tier 1: caverna.fi, accountor.com, solwers.com, jpond.fi
- Move retired sites (talgraf, vahtivuori, monidor) to explicit "Retired" section

### Update TESTING.md
- Fix Tier 1 site references throughout
- Update config examples to reference "optimal" config with stealth

### Low priority
- `azure-deployment/SIMPLE_AUTH_DEPLOY.md` — fix infra refs
- `azure-deployment/TOKEN_ROTATION_GUIDE.md` — fix infra refs

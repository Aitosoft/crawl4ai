# Merge Upstream Develop (Security Fixes)

**Status:** Done (2026-04-14)
**Priority:** High — 2 security fixes at CVSS 9.8

## Goal

Merge `upstream/develop` into our `main` while restructuring our integration
to minimize future merge conflicts.

## What Was Done

### Architecture restructure (before merge)
Created `deploy/docker/aitosoft_entry.py` wrapper entry point that:
1. Sets `BrowserConfig.set_defaults()` from config.yml (replaces `aitosoft_browser_merge.py`)
2. Imports upstream `server.py` app unmodified
3. Adds `SimpleTokenAuthMiddleware` (moved out of server.py)

This reduced upstream file modifications from 5 files to 1:
- server.py: 0 lines changed (was 3)
- api.py: 4 lines (patchright retry only, was ~12)
- browser_adapter.py / browser_manager.py: unchanged (PR upstream separately)
- Dockerfile: 1 line (additive, chrome install)

### Merge
Merged 8 upstream commits from `upstream/develop`:
- `e326da9` fix(security): complete AST sandbox escape remediation (CVSS 9.8)
- `2fc39cb` fix(security): remove eval() from computed fields, harden config deserializer
- `8995c1b` feat: expose arun_many config-list support in Docker API
- `ec560f1` fix: default LLMExtractionStrategy extraction_type to schema
- `7e7533e` fix: validate markdown_generator type in CrawlerRunConfig
- `3d02d75` merge PR
- `bcbccbe` docs: update version references
- Plus a chunking fix cherry-picked through the merge

Conflicts resolved in api.py (trivial: added `crawler_configs` param,
took `effective_config`). server.py taken entirely from upstream.

## Remaining Work (all closed — boxes updated 2026-07-17)
- [x] Update AITOSOFT_CHANGES.md with restructure + merge notes
- [x] Update CLAUDE.md architecture section
- [x] Build + deploy new image (0.8.6, then 0.8.6-leak-fix 2026-04-14)
- [x] Run Tier 1 regression on deployed image
- [x] PR browser_adapter.py stealth 2.x fix upstream — OBSOLETE, upstream
      fixed it themselves (#1960); our patch dropped in the v0.9.2 upgrade
- [x] PR browser_manager.py GPU flag gating upstream — still pending, now
      tracked in tasks/file-upstream-prs.md

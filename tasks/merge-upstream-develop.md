# Merge Upstream Develop (Security Fixes)

**Status:** Open
**Priority:** High — 2 security fixes at CVSS 9.8
**Blocked by:** Nothing

## Goal

Merge `upstream/develop` into our `main`. Upstream develop is 5 commits
ahead of upstream/main with 2 critical security patches:

- `e326da9` fix(security): complete AST sandbox escape remediation (CVSS 9.8)
- `2fc39cb` fix(security): remove eval() from computed fields, harden config deserializer

These patch the config deserializer — adjacent to our `aitosoft_browser_merge.py`
which also touches config dict handling. Low conflict risk but worth checking.

Other commits (non-security):
- `8995c1b` feat: expose arun_many config-list support in Docker API
- `ec560f1` fix: default LLMExtractionStrategy extraction_type to schema
- `3d02d75` merge PR

## Plan

1. `git merge upstream/develop` — expect conflicts in deploy/docker/ files
2. Check AITOSOFT_CHANGES.md conflict points (our stealth edits vs their changes)
3. Run Tier 1 regression after merge
4. Build + deploy new image
5. Update AITOSOFT_CHANGES.md with merge notes

## Conflict risk areas

- `deploy/docker/api.py` — we added merge_browser_config + patchright calls;
  they added arun_many config-list support. Different code paths, likely clean.
- `crawl4ai/async_configs.py` — they fixed CrawlerRunConfig validation; we
  didn't touch this file. Clean.
- Config deserializer hardening might change `from_serializable_dict` behavior
  which our `BrowserConfig.load()` calls rely on. Test carefully.

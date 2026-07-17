# File Upstream PR: GPU flag gating in _build_browser_args

**Status:** Open
**Priority:** Low — our fork carries the fix; the PR is a good-citizen contribution
**Blocked by:** Nothing

## Goal

File one PR to `unclecode/crawl4ai` (target branch `develop`) for the GPU
flag bug we carry as a fork patch in `crawl4ai/browser_manager.py`:

- `_build_browser_args` hardcodes `--disable-gpu` unconditionally, while its
  sibling `build_browser_flags` correctly gates the GPU flags on
  `enable_stealth`.
- Fix: apply the same conditional in both places.
- Impact: WebGL is killed in stealth mode — one of the loudest anti-bot
  signals. Confirmed still present in upstream v0.9.2 (2026-07-16).

Once merged upstream, drop our patch from `browser_manager.py` and remove
the row from the CLAUDE.md / AITOSOFT_FILES.md modification tables.

## History

This task originally planned 4 PRs (2026-04-11). Triage after the v0.9.2
upgrade (2026-07-16) reduced it to this one:

- Stealth 2.x API port — obsolete, upstream fixed it themselves (PR #1960).
- navigator.webdriver init_script — never implemented in our fork; skip.
- config.yml merge into requests — moot; `BrowserConfig.set_defaults()`
  solves it wrapper-side and upstream's untrusted boundary makes server-side
  merging undesirable.

Full details of the retired PR plans: git history of this file (pre-2026-07-17).

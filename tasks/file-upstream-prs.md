# File Upstream PRs

**Status:** four filed, all awaiting upstream review. **A fifth is written and
deliberately unfiled** — see below.

**The fifth: the consent snippet deletes documents.** `remove_consent_popups.js`
(and, in the same family, `remove_overlay_elements.js`) is fixed on our fork as
of 2026-08-06 and both files were byte-identical to upstream before that. This
is the strongest submission we hold — stronger than #2114 — because the Enfold
WordPress theme is sold in the hundreds of thousands and the failure is a
deleted `documentElement` at HTTP 500, plus two silent variants that return a
green result with content missing.

**File it after MAS's segment 2, not before.** "This deletes documents on Enfold
sites, here are N occurrences in a production sweep" beats a synthetic
reproduction, the counter that produces N ships in the same image, and upstream
`develop` moves slowly enough (see the cadence note below) that waiting costs
nothing. Evidence and the four failure shapes:
`tasks/done/consent-scripts-delete-the-page.md`.

| PR | Branch | Filed | Fork patch |
|---|---|---|---|
| [#2085](https://github.com/unclecode/crawl4ai/pull/2085) GPU flag gating in `_build_browser_args` | `fix/gpu-flags-stealth-gating` | 2026-07-17 | `crawl4ai/browser_manager.py` |
| [#2112](https://github.com/unclecode/crawl4ai/pull/2112) block detection behind a redirect chain | `fix/antibot-redirect-status` | 2026-07-30 | `crawl4ai/antibot_detector.py`, `crawl4ai/async_webcrawler.py` |
| [#2113](https://github.com/unclecode/crawl4ai/pull/2113) bound the Playwright calls with no protocol timeout | `fix/bound-untimed-render-calls` | 2026-07-30 | `crawl4ai/browser_adapter.py`, `crawl4ai/async_crawler_strategy.py`, `crawl4ai/async_configs.py`, `crawl4ai/async_webcrawler.py` |
| [#2114](https://github.com/unclecode/crawl4ai/pull/2114) a nested `<noscript>` discards the entire page body | `fix/noscript-swallows-body` | 2026-07-30 | `crawl4ai/content_scraping_strategy.py` |

**On each merge:** drop the corresponding fork patch (it will conflict-or-noop
at the next `git merge upstream/develop`), remove the row from the CLAUDE.md /
AITOSOFT_FILES.md modification tables, and delete the branch. Move this file to
`tasks/done/` only when all four have landed or been closed.

**#2114 is the strongest of the four** and is the one to watch for a signal on
whether this maintainer engages at all: silent whole-page data loss, a six-line
reproduction, no existing `<noscript>` handling anywhere in the file to argue
about, and a 39-line diff. If it sits as long as #2085 did, stop filing and
carry the patches — the fork-maintenance cost is lower than the writing cost.

Our fork's version of the fix is not identical to the PR: `test-aitosoft/`
carries the same cases in our own suite, since we do not depend on upstream
accepting the test layout.

**Review cadence, measured 2026-07-30:** 101 open PRs vs 22 open issues; small
self-evident `fix(docker):` PRs merge in 1-5 days, core-crawler behavioural
changes sit for months (#1923 open since 2026-04-16). #2085 had zero engagement
after 13 days. No CI runs on PRs — `.github/workflows/main.yml` is Discord
notifications only — so the PR body must show the commands and pass counts.
CodeRabbit auto-review is disabled for PRs targeting `develop`.

**Known textual conflict:** #2112 touches the same three `is_blocked` call sites
as the open community PR #2088 (`check_blocked` opt-out). Orthogonal in intent;
flagged in the PR body with an offer to rebase.

---

## Detail: #2085 — GPU flag gating

**PR:** https://github.com/unclecode/crawl4ai/pull/2085 (`fix/gpu-flags-stealth-gating`
→ `unclecode/crawl4ai:develop`, from commit `e63cbcc` on the Aitosoft fork)
**Priority:** Low — our fork carries the fix; the PR is a good-citizen contribution
**Blocked by:** Upstream review

**On merge:** drop the fork patch from `crawl4ai/browser_manager.py` (it will
conflict-or-noop at the next `git merge upstream/develop`), remove the row from
the CLAUDE.md / AITOSOFT_FILES.md modification tables, and delete the
`fix/gpu-flags-stealth-gating` branch.

### Goal

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

### History

This task originally planned 4 PRs (2026-04-11). Triage after the v0.9.2
upgrade (2026-07-16) reduced it to this one:

- Stealth 2.x API port — obsolete, upstream fixed it themselves (PR #1960).
- navigator.webdriver init_script — never implemented in our fork; skip.
- config.yml merge into requests — moot; `BrowserConfig.set_defaults()`
  solves it wrapper-side and upstream's untrusted boundary makes server-side
  merging undesirable.

Full details of the retired PR plans: git history of this file (pre-2026-07-17).

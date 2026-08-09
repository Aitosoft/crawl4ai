# File Upstream PRs

**Status:** four filed, all awaiting upstream review. **A fifth is written and
deliberately unfiled**, and three more candidates now exist — see below.

**The seventh, and it is the cleanest we have: an image `desc` can be the whole
page.** Shipped on our fork 2026-08-09 in `crawl4ai/content_scraping_strategy.py`
(`MEDIA_DESCRIPTION_MAX_CHARS`). `find_closest_parent_with_useful_text` walks up
from an `<img>` and returns an ancestor's *entire subtree text*; image containers
have no words, so on a grid layout it stops at whatever container also holds the
page prose, and `add_variant` copies that into every srcset variant. Production:
**231,708,619 bytes of `media` from one page, 1,104 of 1,160 entries carrying the
same 154,798-char string**, four times, at HTTP 200 `success: true`.

Three things make it unusually arguable, and none of them need our corpus:

- **The same document yields `desc: None` on minified markup and the whole page
  on pretty-printed markup** — the stop condition is a conjunction of `.text`
  (the direct text node, so indentation whitespace is truthy) and
  `text_content()` (the whole subtree). Payload differing by 52× on whitespace
  alone is a bug by inspection.
- **No comparable extractor manufactures an image description by walking the DOM
  upward.** Firecrawl, Scrapy, trafilatura, readability, unstructured and
  html2text all use the `alt` attribute or nothing.
- **Upstream's own documented contract calls `desc` "a snippet of nearby text or
  a short description", and its own example value is elided with an ellipsis.**
  The bug is visible in the documentation.

Prior art for the constant is upstream's own
`preprocess_html_for_schema(attr_value_threshold=200)` — though be honest in the PR that
200 is that function's *signature default* and both in-tree callers override the sibling
`text_threshold` to 500, so it is precedent for bounding an over-long value, not for this
exact number. Blast radius verified
zero: upstream's tests assert only `src`/`alt`/`type`/`score`.
**Argue it as "`desc` is now bounded", not "media entries are now bounded"** —
`alt` and `media.tables` are still unbounded. `alt` is linear in the document;
**`media.tables` is superlinear in an unvalidated `colspan`** (`row_data.extend([text] * colspan)`), which is a separate upstream defect.
Evidence: `tasks/done/media-desc-duplicates-the-page-per-image.md`.

**The eighth, small and honest: a Windows workaround makes `channel="chromium"`
unreachable everywhere.** `crawl4ai/browser_manager.py:1123-1128` drops the
`channel` kwarg whenever `chrome_channel == "chromium"` — a documented config
value — so Playwright silently launches `chromium_headless_shell` instead of the
full build on every platform. The two binaries differ in ways that change crawl
outcomes: the shell has no PDF viewer, so an inline `application/pdf` raises
`Download is starting` on one and renders a 174-byte viewer shell at HTTP 200 on
the other. Fix is `sys.platform == "win32"` on that condition. Inert for us
(production sends `chrome_channel: chrome`), so this one is charity, not need —
but it is the reason our own browser suite has never run production's browser.

**Not a PR — an upstream security report:** `PDFContentScrapingStrategy` is in
`UNTRUSTED_ALLOWED_TYPES` and `scraping_strategy` is in
`UNTRUSTED_FIELD_ALLOWLIST["CrawlerRunConfig"]` (`async_configs.py:194`, `:238`),
so an untrusted request body can select it — and its `_get_pdf_path` does a
blocking `requests.get(url, stream=True, timeout=(20, 600))` **on the event
loop**, bypassing `validate_url_destination` and the pinning egress proxy. That
is an SSRF path through upstream's own untrusted-config boundary. **Latent for
us** — our single client is trusted and token-gated — and the one-line local
tightening is to drop it from the allowed types in `aitosoft_trust.py`. Not done,
because it is not live and this repo is trying to ship only what is needed;
recorded here so it outlives the corrections list it was found in.

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

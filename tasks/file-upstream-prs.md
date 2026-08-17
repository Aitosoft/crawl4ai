# File Upstream PRs

**Status:** four filed, all awaiting upstream review. **A fifth is written and
deliberately unfiled**, and three more candidates now exist — see below.

---

## ⚡ 2026-08-17: why this is now a maintenance task, not a good-citizenship one

**Read this before deciding what to file.** Three things changed and they point in different
directions.

**1. The divergence is growing and it is concentrated where it hurts.** Our fork is **+4,696 / −193
lines across 25 files**. About **2,143 of those are our own `aitosoft_*.py` files and cost nothing** —
upstream will never touch them. The other **~2,375 sit on 17 files upstream also owns**:
`crawler_pool.py` +605, `api.py` +429, `antibot_detector.py` +371, `async_crawler_strategy.py` +267,
`remove_consent_popups.js` +168, `server.py` +104. **Upstream currently has 7 commits we lack and
three of them edit `api.py`, `server.py` and `supervisord.conf`** — solving the same problem class
our `aitosoft_failure_class.py` solves (`fix(docker): preserve failed crawl results`). The next
`git merge upstream/develop` conflicts precisely where our most complex logic lives.

**So a merged PR deletes our divergence permanently, and an unfiled one is a merge conflict every
release, forever.** That is the argument. It is about our own maintenance cost, not about being
good open-source citizens, and it should be weighed that way.

**2. Our own stop condition has fired, and it argues for filing FEWER, better PRs.** This file says:
*"if #2114 sits as long as #2085 did, stop filing and carry the patches."* Measured 2026-08-17:
upstream has **116 open PRs** (101 on 2026-07-30 — the backlog grew 15 in 18 days), **5 commits on
`develop` in all of August** against 42 in July and 86 in March, and **zero maintainer engagement on
any of our four** in 18–31 days. #2114's only response is a favourable peer review from another
contributor.

The conclusion is not "stop entirely" — it is that **the marginal PR is worth little and the two
that carry their own evidence are worth a lot.** Those are the **`desc` cap** (seventh, below) and
the **consent snippet** (fifth), because a maintainer can verify both without our corpus. Everything
else on this list should wait until one of those lands and tells us whether the channel is open.

**3. The consent PR should argue a different fix than the one we built — and this is the most
useful thing the 2026-08-17 research found.**

We planned to argue the root collision. That is correct, and it is well supported: the adblocker
ecosystem hit this identical failure in 2021 (`uBlockOrigin/uBlock-issues#1692` — sites blanked
because `body` carried a consent class matched by a generic filter), fixed it at the engine level in
uBO v1.37.3b15, and **still carries ~845 hand-written `:not(html)` / `:not(body)` guards** across
Fanboy's and AdGuard's annoyance lists, verified live on EasyList master. That is a decade of
institutional evidence that generic-substring-matches-root is a *chronic* hazard, and it needs
neither repo's corpus.

**But it points past our fix.** Every maintained system in this space **hides rather than removes**:

- **DuckDuckGo's `autoconsent`** — ~300 CMP rule files, commits daily, the de-facto standard — has
  **no `remove()` action in its rule syntax at all.** Its actions are exists / visible / wait /
  click / **hide** / remove-class / set-style / eval.
- EasyList's own written policy, uBO, AdGuard and Ghostery all inject `display:none`.

**crawl4ai's snippet is more dangerous than any adblocker not because its selectors are worse but
because its action is.** So the strongest submission is **"the generic tier should hide, not
remove"**, with the structural guard as defence in depth — which is what we already do internally
(our 20 generic selectors observe instead of removing), and which makes the root-collision question
*moot* rather than merely survivable. A maintainer is far more likely to take a change that matches
what the entire field converged on than a novel guard.

**Pre-empt one objection in the PR body:** uBO's stricter follow-up (`7c8aec2`, 2022-01-12) was
**reverted** (`5178b91`, 2022-02-16). A reviewer who knows that history will raise it. The revert
was of an attempt to rewrite arbitrary user CSS into `:is()`/`:not()` wrappers; ours is a
node-identity check immediately before `.remove()`. Different mechanism, far smaller blast radius.

**And the honest tension, which the PR must address rather than dodge:** hiding is sufficient for
`innerText` and **insufficient for a DOM extractor** — `cleaned_html` goes through lxml, so
`display:none` leaves the banner text in the output. That is a real cost and it may be why upstream
chose `.remove()` in the first place. The defensible synthesis is probably *remove only inside a
structural guard, hide otherwise*. Work it out before filing; do not hand a reviewer an obvious hole.

**⚠️ Time pressure, new:** upstream **PR #2139** (filed 2026-08-13, unreviewed) modifies **both**
`remove_consent_popups.js` and `remove_overlay_elements.js` — for an unrelated defect, a CSP
`sandbox` directive disabling script timers so the snippet's unconditional `await new
Promise(setTimeout)` never resolves (GitHub raw: 31 s → 1.3 s; HuggingFace raw: hung >130 s →
1.5 s). **It will conflict with our fifth and sixth candidates.** It is unreviewed so we can
plausibly land first, but reference it — and note it independently found a *second* latent defect in
that file, which supports our framing that the snippet has never been audited.

**Also worth knowing before filing anything in `crawl4ai/`:** several problems we hold are already
being fixed upstream. **PDF → 174-byte shell → tier-3 "blocked" → 500** is issue #2135 with two
competing PRs (#2137, #2138); **`pypdf` missing from the image** is #2127 + PR #2130; **the
`base_config` `None`/`""` merge trap** is #2121 + PR #2122; **cgroup v2 `memory.max == "max"`** is
#2123 + PR #2132 (**we inherit that bug verbatim at `deploy/docker/utils.py:487`** — `int()` raises
on the `"max"` sentinel, the bare `except` swallows it, and the function silently returns *host*
memory percent; harmless in ACA where the limit is set, but it means **every offline test of the
memory guard has been measuring the host**); and **the 30 s `wait_for_selector("body")` that
`ignore_body_visibility: True` then discards** is #2129 + PR #2131. **Take theirs. Build none of
these.**

---

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

~~**File it after MAS's segment 2, not before.**~~ **THAT GATE HAS FIRED — it is
fileable now, and it is the last open cross-repo step.** Segment 2 ran
2026-08-06 and three workloads have since supplied N: **27 roots on 3 companies**
(segment 2), **266 declined removals of which 103 were structural roots on 19
domains** (segment 5), **124 declined with 56 % hitting a `<script>` or `<style>`
element** (batch 1) — that last figure strengthens the root-collision argument
rather than the data-loss one, which is the argument to lead with. MAS also
measured the other side: **95 matched containers, 0 containing any contact data**,
so do **not** argue "this destroys banner data" — argue the root collision, which
needs neither repo's corpus. Evidence and the four failure shapes:
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

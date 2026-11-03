# Upstream PRs: what to file, what to close, what to carry

**Status (2026-11-03):** four PRs filed, all open, **zero maintainer response in 3–3.5 months**.
Upstream's open-PR backlog is **249**, against 116 on 2026-08-17. **Do this after
`upgrade-upstream-v0.9.5.md` ships.** The merge changes what each patch looks like, and three of
the candidates below have to be rebased onto it anyway.
**Size:** M of judgement and writing. The code exists.

---

## Why this matters: maintenance, not good citizenship

Every line we carry in an upstream-owned file conflicts at every sync. The v0.9.5 merge conflicts in
7 of the 20 upstream files we modify, and upstream touched 17 of them (`AITOSOFT_FILES.md`). **A merged
PR deletes a patch permanently; an unfiled one costs us at every release.** Weigh each candidate by
the merge cost it removes, against the cost of writing it.

**But the channel is narrow.** Our stop rule was "if #2114 sits as long as #2085 did, stop filing and
carry the patches", and it fired in August. Since then upstream merged a *community* PR (#2284,
2026-10-12) that fixes the same `<noscript>` defect as our #2114, while ours sat unreviewed. So small
outside fixes do land; ours just haven't been looked at. **File fewer, better PRs: ones a maintainer
can verify from the PR alone, without our corpus or our context.** Two candidates qualify (below).

## Filed

| PR | Branch | Fork patch | State 2026-11-03 | Action |
|---|---|---|---|---|
| [#2085](https://github.com/unclecode/crawl4ai/pull/2085) GPU flags gated on `enable_stealth` in `_build_browser_args` | `fix/gpu-flags-stealth-gating` | `crawl4ai/browser_manager.py` | open, no response | Still applies cleanly to develop. Leave it. Upstream already gates the sibling `ManagedBrowser.build_browser_flags`, which is the PR's argument. |
| [#2112](https://github.com/unclecode/crawl4ai/pull/2112) block detection behind a redirect chain | `fix/antibot-redirect-status` | `antibot_detector.py`, `async_webcrawler.py` | open, no response | Needs a rebase (`async_webcrawler.py`, `placeholder_html` hunk). Only rebase if a maintainer engages. Textual overlap with community PR #2088 is flagged in the body. |
| [#2113](https://github.com/unclecode/crawl4ai/pull/2113) bound Playwright calls that carry no protocol timeout | `fix/bound-untimed-render-calls` | `browser_adapter.py`, `async_crawler_strategy.py`, `async_configs.py`, `async_webcrawler.py` | open, no response | Needs a rebase (`async_crawler_strategy.py`, overlay-wait hunk). Same rule. |
| [#2114](https://github.com/unclecode/crawl4ai/pull/2114) nested `<noscript>` discards the page body | `fix/noscript-swallows-body` | `content_scraping_strategy.py` | open; body loss superseded by upstream #2284 (in v0.9.5) | **Leave it open until upstream's #2416 fix lands.** Upstream's replacement loses text after a balanced `<noscript>` (#2416, acknowledged in ~11 places), and ours doesn't. So our approach still carries something theirs lacks. When #2416 is fixed, close #2114 with a comment pointing at both, and delete the branch. |

**When a PR merges, or we drop a patch:** delete the patch, delete its entry in `AITOSOFT_FILES.md`
§1, and delete the branch. Move this file to `tasks/done/` when nothing on it is worth filing.

## Worth filing: the two that carry their own evidence

### The consent snippet deletes documents (`remove_consent_popups.js`)

Fixed on our fork 2026-08-06. The file was byte-identical to upstream before that, and **upstream
still calls `el.remove()` unguarded** on whatever a generic selector matches (checked at
`cd61be1`).
- Enfold, sold in the hundreds of thousands, puts `av-cookies-no-cookie-consent` on `<html>`. The
  result is a deleted `documentElement` → a 15-byte capture → 500.
- Two variants are silent and return a green result with content missing.
- Evidence and the four failure shapes are in `tasks/done/consent-scripts-delete-the-page.md`.

**Argue "the generic tier should hide, not remove". Don't argue for our structural guard alone.**
Every maintained consent system hides:
- DuckDuckGo's `autoconsent` (~300 rule files, commits daily) has **no `remove()` action** in its
  rule syntax: its actions are exists / visible / wait / click / hide / remove-class / set-style /
  eval;
- EasyList's written policy, uBO, AdGuard and Ghostery all inject `display:none`.

uBlock and EasyList hit our exact bug in 2021 (`uBlockOrigin/uBlock-issues#1692`: `body` carried a
consent class that a generic filter matched). They fixed it at engine level in uBO v1.37.3b15, and
still carry ~845 hand-written `:not(html)` / `:not(body)` guards across Fanboy's and AdGuard's lists
(verified on EasyList master, 2026-08-17). Hiding makes the root-collision question moot rather than
merely survivable. The structural guard stays as defence in depth.

- **The objection to pre-empt:** uBO's stricter follow-up (`7c8aec2`, 2022-01-12) was reverted
  (`5178b91`, 2022-02-16). That was a rewrite of arbitrary user CSS into `:is()`/`:not()`; ours is a
  node-identity check before `.remove()`.
- **The tension the PR must address, not dodge:** hiding is enough for `innerText` but not for a DOM
  extractor. `cleaned_html` goes through lxml, so `display:none` leaves banner text in the output.
  That may be why upstream chose `.remove()`. The defensible synthesis is probably *remove only
  inside a structural guard, hide otherwise*. Work it out before filing.
- **Don't argue "this destroys banner data".** MAS measured 95 matched containers with 0 contact data.
  Argue the root collision, which needs neither repo's corpus.
- **The numbers to cite** (our `CONSENT DECLINED` counter):
  - segment 2: 27 roots on 3 companies;
  - segment 5: 266 declined removals, 103 of them structural roots on 19 domains;
  - batch 1: 124 declined, 56 % of them on a `<script>` or `<style>` element. That figure
    strengthens the root-collision argument rather than the data-loss one.
- **Rebase onto `b536bf5` (#2139, merged 2026-08-17)**, which made the in-page waits conditional in
  the same file. After the v0.9.5 merge our copy already contains it.

### An image's `desc` can be the whole page (`content_scraping_strategy.py`)

`find_closest_parent_with_useful_text` walks up from an `<img>` and returns an ancestor's *entire
subtree text*, and `add_variant` copies it into every srcset variant. Production: **231,708,619
bytes of `media` from one page**, 1,104 of 1,160 entries carrying the same 154,798-char string, at
HTTP 200 `success: true`. Fixed on our fork 2026-08-09 (`MEDIA_DESCRIPTION_MAX_CHARS = 200`);
upstream is still uncapped at `cd61be1`. Why it's arguable without our corpus:
- **The same document gives `desc: None` minified and the whole page pretty-printed.** The stop
  condition ANDs `.text` (indentation whitespace is truthy) with `text_content()` (the whole
  subtree). A payload that changes 52× on whitespace alone is a bug by inspection.
- **No comparable extractor builds an image description by walking the DOM upward.** Firecrawl,
  Scrapy, trafilatura, readability, unstructured and html2text use `alt` or nothing.
- **Upstream's own docs** call `desc` "a snippet of nearby text", with an elided example value.
- **Prior art for 200:** upstream's `preprocess_html_for_schema(attr_value_threshold=200)`. Be
  honest that it's that function's signature default, and that both in-tree callers override the
  sibling threshold to 500.
- **Blast radius:** upstream's tests assert only `src`/`alt`/`type`/`score`.
- **Scope the claim:** argue "`desc` is now bounded", not "media entries are bounded". `alt` and
  `media.tables` are still unbounded. Upstream `ee1a295` clamps `colspan` in body rows, but header
  rows still use bare `int()`.

Evidence: `tasks/done/media-desc-duplicates-the-page-per-image.md`.

## Not worth filing, and why

- **The overlay snippet (`remove_overlay_elements.js`).** Upstream `a574fbc` (v0.9.3) added an
  equivalent `isDocumentStructure` guard. What's left of ours is the `rgba` alpha fix
  (`getComputedStyle().backgroundColor` is `rgba(0,0,0,0)` by default, so `.includes("rgba")` is
  always true). A one-line PR could carry it, but the flag deletes content even with the fix, and MAS
  sends it `false`. Low value either way.
- **The `chromium`-channel Windows workaround.** Upstream fixed it in `a1bd6c8` (on develop, after
  v0.9.5).
- **The PDF SSRF through `PDFContentScrapingStrategy`.** Upstream fixed it in v0.9.3 (GHSA-q5rj /
  GHSA-v2rm / GHSA-xpp7).
- **`egress_proxy.py` (off-loop resolve, 15 s connect, close-on-`http://`).** Upstream rewrote the
  file for proxy chaining, and its open PR #2428 (maintainer-tested 2026-10-22) moves the resolve off
  the loop in its own way. Carry ours until #2428 lands, then drop what it covers.
- **The dead-domain → `origin_unreachable` at 200 split** (`api.py`) doesn't port upstream as-is. It
  answers NXDOMAIN with 200 and a policy refusal with 400, which is a DNS oracle for an untrusted
  caller. That's fine for our one trusted client, and wrong as a general default.
- **Problems we hold that upstream is already handling.** Take theirs and build nothing:
  - `pypdf` in the image (#2130, merged);
  - PDF placeholders read as blocks (#2138, merged);
  - the configurable body-visibility wait (#2131, merged);
  - cgroup v2 `memory.max == "max"` (#2132, open; we inherit it verbatim in our `utils.py` memory
    reading);
  - the `base_config` `None`/`""` trap (issue #2121 open; PR #2122 closed unmerged 2026-10-11).

## How upstream reviews, for whoever writes the PR body

- **CI doesn't run on PRs** (`main.yml` is Discord notifications only), so the body must show the
  commands and pass counts.
- **CodeRabbit is off** for PRs targeting `develop`.
- **Small self-evident `fix(docker):` PRs from the maintainers' side merge within days, while
  core-crawler behaviour changes sit for months** (measured 2026-07-30). Our four sit in the second
  group.

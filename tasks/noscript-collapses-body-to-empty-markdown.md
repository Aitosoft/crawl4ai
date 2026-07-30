# A nested `<noscript>` silently discards the entire page body

**Status:** Open — ready to implement. Fully diagnosed, offline-reproducible,
one-line fix, no external input needed.
**Priority:** HIGHEST of the remaining batch, jointly with the Q2 classification
work. 406 pages across 70 hosts in MAS's corpus, silent, reproducing identically
3½ months apart. This is the fifth root cause and the only one MAS's reply could
not explain.
**Effort:** S (fix) + S (fixture tests). **Risk:** low.
**Evidence:** measured 2026-07-30 against prod rev 0000030 + offline repro;
MAS's `empty_*` classification in `tmp/crawl4ai-affected-hosts.txt`.

## Symptom

Full mode returns **HTTP 200, `success: true`, and markdown of exactly one
character** (`"\n"`) for pages with several kilobytes of real server-rendered
prose. MAS calls this the `empty_*` family: **406 stored pages across 70 hosts**,
of which 34 hosts have *every* page empty. It reproduced byte-identically on
`nordicinterim.fi` and `kuljetuspolar.fi` on 2026-04-17 and 2026-07-30;
`vaskisepat.fi` recovered on its own between those dates.

Measured on the reference case, `https://www.kiertopakkaus.fi/`:

| Path | `html` | `cleaned_html` | `raw_markdown` |
|---|---|---|---|
| full mode (MAS V14) | 312,628 B | **97 B** | **1 B** (`"\n"`) |
| full mode, `remove_consent_popups` off | 312,826 B | — | **1 B** |
| static mode | — | — | **9,261 B** ✅ |

`cleaned_html` is literally `<html><head><title>Etusivu - Kiertopakkaus</title></head></html>`
— **the whole `<body>` is gone.** The markdown generator is innocent; it
faithfully renders nothing.

## Root cause

The page contains a **nested `<noscript>`**, emitted by a WordPress lazy-load
plugin wrapping the Google Tag Manager block:

```html
<noscript><iframe data-lazyloaded="1" src="about:blank" data-src="…GTM…"></iframe>
  <noscript><iframe src="…GTM…"></iframe></noscript>
<!-- the OUTER </noscript> is never emitted -->
<a class="skip-link" href="#content">Siirry sisältöön</a>
<div class="hfeed site" id="page">… the entire page …
```

`<noscript>` cannot nest — with scripting enabled its content is raw text, so
the parser never sees the inner tag as an element and the outer element is left
unclosed. When libxml2 re-parses Playwright's serialised DOM, **everything from
the skip-link onward is swallowed into the unclosed `<noscript>` and dropped.**

Confirmed by excision, offline, on the captured DOM:

| Input | `cleaned_html` |
|---|---|
| baseline | 97 B |
| cut *only* the nested-noscript region | **47,310 B** |
| strip all `<noscript>` tags | **51,795 B** |
| strip `<script>` only | 66 B (no help) |

`lxml` sees 2 body children; BeautifulSoup sees 4 with 6,222 chars of text —
which matches MAS's "6,138 characters of genuine Finnish prose" almost exactly.

`grep noscript crawl4ai/content_scraping_strategy.py crawl4ai/utils.py` returns
**nothing**: crawl4ai has no `<noscript>` handling at all. Our own
`aitosoft_static_mode._strip_hidden_decoys` already decomposes `noscript` — which
is precisely why static mode returns 9,261 chars and full mode returns 1.

### Minimal reproduction (use this as the fixture — no live site needed)

```python
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
MIN = '''<html><head><title>T</title></head><body>
<noscript><iframe src="about:blank"></iframe><noscript><iframe src="about:blank"></iframe></noscript>
<h1>Yhteystiedot</h1><p>Puhelin 010 123 4567, sahkoposti info@example.fi</p>
<div><p>Toinen kappale oikeaa sisaltoa.</p></div>
</body></html>'''
LXMLWebScrapingStrategy().scrap('https://x/', MIN, word_count_threshold=1).cleaned_html
# nested:            42 B  -> '<html><head><title>T</title></head></html>'
# single noscript:  187 B  (well-formed noscript is harmless)
# no noscript:      188 B
```

## Fix

Strip `<noscript>` elements before the scraping strategy parses. Rationale for
removal rather than repair: **we render with JavaScript enabled**, so by
definition `<noscript>` content is not what a user sees, and its JS-rendered
equivalent is already in the DOM. Dropping it loses nothing and removes the
malformed-nesting class of failure entirely. This is the same decision our
static path already made.

Implementation notes for whoever picks this up:

- A regex over the raw HTML (`</?noscript[^>]*>` removed, keeping inner content,
  **or** the whole element removed) is the pragmatic fix, because the whole
  problem is that a *parser* cannot handle the markup — so the repair must
  happen before parsing. Prefer removing the tags and keeping inner content
  only if you can show it does not reintroduce duplicate `<img>` noise; removing
  the whole element matched static mode's behaviour and is the safer default.
- Put it where both scraping strategies inherit it (they produced identical
  97-byte output, so there is a shared path — find it rather than patching two
  places).
- Do **not** special-case "nested" noscript. A well-formed single noscript is
  harmless today, but the failure is a parser-level swallow and other malformed
  shapes will exist. Handle the tag, not the nesting.

## Also: file upstream

Clean, self-contained, with a 6-line reproduction and an obvious test. Third PR
in the series — follow `tasks/file-upstream-prs.md`. Expect it to be a strong
one: silent whole-page data loss with a minimal repro is the most compelling
kind of upstream bug report.

## Verification

- Offline fixture tests from the minimal repro above: nested noscript must yield
  the full body; single noscript unchanged; no noscript unchanged.
- Regression: assert a page whose *only* content is inside `<noscript>` still
  behaves sanely (it should be empty — that is correct, since JS was enabled).
- Tier 1 regression 4/4. None of them exhibit this, so a no-op there is the check.
- **Do not re-test `kiertopakkaus.fi` live** — it took 4 requests during the
  investigation. The captured DOM is the fixture; regenerate only if needed.

## Expected impact

MAS should re-scrape all 70 `empty_*` hosts after this deploys. On this evidence
the fix converts them from 1 character to full content. Worth telling them the
expected recovery so they can measure it rather than take our word.
